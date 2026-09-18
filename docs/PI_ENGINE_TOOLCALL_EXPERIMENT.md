# Pi 工具协议下沉与真实编程任务

2026-09-18（Asia/Shanghai），单次真实 Agent 实验通过。

后续 token 核验和原生 Toolcall 两轮对照见 [耗时与用量对照](PI_ENGINE_TOOLCALL_COMPARISON.md)。

## 接入边界

使用本机安装的 `@earendil-works/pi-coding-agent@0.85.1`，对应 npm `gitHead`
`d981de1229ef899957bbe968bc8dcda02a21f477`。上游是
[earendil-works/pi](https://github.com/earendil-works/pi)，原 `badlogic/pi-mono` 已重定向。

直接导入 Pi 的 `runAgentLoop` 和内置 `createReadTool/createBashTool/createEditTool/createWriteTool`。
不重写 Agent loop，不替换为按预设顺序执行的模拟器，不修改用户全局 Pi 配置。
通过 `streamFn` 接入自己的推理传输，再增加一个返回 `terminate: true` 的 `reply_user` 工具。
Pi 每轮收到的 assistant 内容只有 `toolCall`，包括最终答复。

```text
Pi loop / 当前工具 Schema / 完整历史
  → SSH stdio → 推理主机协议适配器
  → 编译工具分类与参数 grammar → vLLM 一次连续解码
  → 完整结束检查 / 值解码 / 固定 Schema 构造调用对象
  → Pi 参数校验 / 本机工具执行 / 结果回流
  → 下一轮，直到 reply_user
```

`deploy/pi_engine_protocol.py` 在 yuesheng-gpu 运行，不执行工具。工具选择与参数结构的约束
实际由 vLLM 的 `structured_outputs.regex` 在解码中执行；调用对象的构造在同机适配器完成。
这不是新增分类头、模型微调、自定义 vLLM 插件，也没有修改引擎源码。
不再经过 Pi 原生 provider 的增量 Toolcall JSON 修补路径；紧凑参数 tuple 仍然需要严格 JSON 解码，
不是“完全没有 parser”。非法、截断、无法编码的结果不会返回可执行 `call`。

## 协议

Schema 从实际 Pi 工具导出，保留字段顺序。有限工具集合对应单字母分类；对象转为固定位置的数组，
嵌套 `edit.edits` 对象同样转为数组；缺失可选参数使用 `null` 占位。
若最后一个字段是必填字符串，则把它移到帧尾原样生成，以避免长代码正文的 JSON 转义。

| 分类 | 工具 | 输出布局示例 |
|---|---|---|
| A | read | `A\n["file.py",null,null]` |
| B | bash | `B\n["python3 -m unittest -v",30]` |
| C | edit | `C\n["file.py",[["old","new"]]]` |
| D | write | `D\n["file.py"]\n` 后接原始文件内容 |
| E | reply_user | `E\n[]\n` 后接原始答复 |

支持本次工具需要的 object、array、string、number、integer、boolean 与可选字段。
未知 Schema 约束拒绝编译，不静默忽略。不是完整 JSON Schema 编译器；此 runner 的历史传输仅验证文本，
没有验证图像、多工具并行、会话持久化与完整 Pi CLI 功能。

## 执行与隔离

模型自行决定工具顺序。`bash` 使用 Pi 原有命令执行实现，并通过 operations 接口包裹 bubblewrap：
私有网络 namespace，仅 loopback；只读系统程序；实验目录为唯一持久可写挂载；清空子进程环境；
每条命令最长 30 秒。文件工具限制在实验 workspace。推理服务器没有获得本机文件或 shell 执行权限。
最多 12 个模型轮次、总截止时间 600 秒，无需启动常驻实验服务，也未重启/调参现有模型容器。

本次使用的 runner 完整快照位于证据目录 `sources/run_scanner.mjs`。运行后当前 runner 又补充了
悬空符号链接的拒绝处理；6 个路径边界检查通过，未将该小修复冒充本次远端运行的原始源码。

## 任务与结果

给模型自然语言要求：生成标准库 TCP connect 扫描器，支持端口列表/范围/去重、超时、并发、JSON 输出，
生成 unittest 并真实执行，最后通过 `reply_user` 报告。没有提供扫描器实现或指定每一步工具调用。

证据目录：`results/experiments/pi-scanner-20260918-run1/`。

| 轮次 | 工具 | 结果 | 包含 SSH 传输的推理耗时 | 输出 tokens |
|---|---|---|---:|---:|
| 1 | read | 文件不存在，错误真实回传 | 2.383 s | 14 |
| 2 | bash | 检查实验目录 | 3.857 s | 28 |
| 3 | write | 创建 port_scanner.py | 18.571 s | 1392 |
| 4 | write | 创建 test_port_scanner.py | 26.426 s | 2067 |
| 5 | bash | 运行 17 项 unittest，全部通过 | 8.980 s | 19 |
| 6 | reply_user | 交付最终中文答复并终止 loop | 19.927 s | 154 |

完整 Agent 用时 **81.189 秒**，输出总计 **3674 tokens**。6/6 模型结果为完整有效帧，全部 assistant 输出为工具调用。
分类 token 分别实测 35、36、38、39，后接换行 token 201。`edit` Schema 已编译并通过嵌套参数单测，
但此次任务没有实际选择 `edit`，不能把它算作远端执行成功。

模型自身 17 项 unittest 实际执行通过；另由独立验收程序启动随机 loopback 监听/非监听端口，检查
1/4/16 workers 下的开关端口、范围和重复值、非法端口/参数、help，并重新运行模型的 unittest。
独立验收 **17 个检查项通过**（其中一项是重跑上述 17 个 unittest，不能合并宣称 34 个独立测试）。
生成文件未经人工修改。验收记录在 `acceptance.json`。

引擎原生计时六轮合计：排队 23.669 s，调度至首 token 1.119 s，首末 token 间隔 41.893 s。
还包含 SSH 启动、请求处理及工具执行等开销；不是纯 GPU 计算时间。
这是共享负载下单任务可行性验证，没有原生 Pi 对照组，不能据此宣称端到端加速或生产正确率。

模型为 `DeepSeek-V4-Flash-Vision-Exp`，served ID `/model`，vLLM
`0.28.1rc1.dev137+g5ab628dd1`，TP2×PP3，6×RTX5090。
镜像 ID：`sha256:c0dec7f60c449fc4089134dcbc2b80462e9d39622fa33dba83dfb0b1d90987dc`。
模型 config SHA256：`6cd841bdd6702f5e2ac34671bc78047ed80817102465525ae2a41c502abbcd75`。
其余环境、Pi 原始实现哈希、请求 metrics、token IDs、工具结果和源码快照均在证据目录。

## 复现

需要已安装 Pi 0.85.1、Node 22.19+、Python3、bubblewrap，以及到授权推理主机的 SSH。
先把 `deploy/pi_engine_protocol.py` 复制到远端一个新实验目录，然后从仓库根目录执行：

```sh
node integrations/pi/run_scanner.mjs \
  --out results/experiments/pi-scanner-NEW-RUN \
  --pi-root "$(npm root -g)/@earendil-works/pi-coding-agent" \
  --host rs-yuesheng-gpu-vps \
  --worker /opt/openjev-toolcall/experiments/pi-20260918-a/pi_engine_protocol.py
```

输出目录必须不存在。`integrations/pi/accept_scanner.py` 应在相同隔离配置中运行，
把生成文件目录只读挂载为 `/work`、验收脚本只读挂载为 `/accept_scanner.py`，在 `/work` 执行
`python3 /accept_scanner.py`。它只扫描 namespace 内自行创建的端口，不扫描主机现有服务。

仓库验证：46 项 pytest、原有 raw SHA256 校验、69 项 published claim 校验全部通过。
本实验不改变 Phase 1 数据或 headline claims。
