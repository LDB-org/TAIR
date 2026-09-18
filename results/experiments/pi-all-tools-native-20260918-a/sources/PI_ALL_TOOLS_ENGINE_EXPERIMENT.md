# Pi 全部内置工具的引擎侧协议实验

2026-09-18。目标是接入 Pi 的完整内置工具集合，将调用产生与协议处理移到推理侧，保留 Pi 执行器和 Agent loop。
本轮没有使用 Python 编辑 DSL，也没有限制模型只能做预定义的代码修改。

## 实现边界

从本机 `@earendil-works/pi-coding-agent@0.85.1` 实际导出全部 8 个内置工具：
`read`、`bash`、`edit`、`write`、`grep`、`find`、`ls`、`powershell`。
另注册 `reply_user`，用户答复也必须经过调用。
runner 对导出的 `allToolNames` 检查覆盖，若安装版本新增了工具却没有注册，立即报错。

```text
Pi 提供工具 Schema 和消息历史
  → 推理主机编译工具选择及参数 grammar
  → vLLM 约束解码：工具编号 + 参数值
  → 推理主机检查完整性、解码并构造调用对象
  → Pi 分发工具、执行、将结果反馈给下一轮
  → reply_user 交付答复并结束
```

`deploy/pi_engine_protocol.py` 是推理主机上的一次性 stdio 适配器，调用现有 vLLM `/v1/chat/completions`。
工具集合由 Pi 动态传入，协议编译器不按工具名硬编码生成操作。
对象键由引擎侧补齐，嵌套对象使用位置 tuple，必填的最后一个字符串字段可作为原始正文输出。
引擎模式没有 native 回退；测试中的 native 是独立对照运行，不是模型可选分支。

这次扩展 `integrations/pi/run_scanner.mjs`，增加完整工具集合、任务文件、初始 fixture 和轮数参数，
默认扫描器入口仍保留。实际复用了 Pi 的 `runAgentLoop` 和全部内置执行器。

需要准确区分：grammar 由 vLLM 解码后端执行，调用对象在同机适配器构造；不是新增分类头或修改 vLLM 核心。
Harness 不再解析模型 Toolcall 文本，但仍解码传输 JSON、组装 Pi 事件并校验/执行参数。
推理侧仍有严格的帧和 JSON tuple 解码，并非系统完全没有 parser。

## 任务与验收

修复 `catalog.py`：去除名称首尾空白、丢弃空名称、按首次出现顺序去重，保留 JSON CLI。
任务要求逐项使用全部工具；这是有工具覆盖要求的集成测试，不代表无提示情况下的自然工具选择率。
模型自行生成参数、补丁和测试，未提供标准实现或预制调用。

文件工具限制在实验目录；bash/powershell 通过 Pi operations 进入私有网络和文件系统的 bubblewrap。
本机没有 `/usr/bin/pwsh`，因此 PowerShell 仅验收调用到达执行器和错误回传，不能声称成功执行 PowerShell 命令。
工具权限及执行仍归 Harness 所有，推理主机不执行本地工具。

引擎组实际调用顺序：
`read → ls → find → grep → edit → write → bash → read → edit → bash → powershell → reply_user`。
首次 edit 生成了带 `.*def` 的错误源码，第一次 bash 测试失败；模型读取错误文件后再次 edit 并重跑成功。
未人工修改生成文件，12/12 返回帧有效，所有 assistant 消息仅包含 Toolcall。
该错误说明协议合法与代码语义正确是不同的验收项。

独立验收检查 5 组函数输入及 CLI 输出，并重跑模型生成的 6 项 unittest，全部通过。
验收脚本第一版遗漏 `/work` 的导入路径，导致 ModuleNotFoundError；修正验收脚本后重验通过，
没有修改模型产物，初版检查文件保留在证据目录中。

真实 Schema 的本地编码检查覆盖全部 9 个工具、嵌套 edit、可选字段、Unicode、多行正文；
9 组往返一致，36 个非完整结束标记及 4 个非法帧均拒绝。

## 证据与复现

同任务各运行一次的完整成本如下，包含错误、修复和最终回复：

| 指标 | 原生 Toolcall | 引擎协议 |
|---|---:|---:|
| 独立验收 | 通过 | 通过 |
| 模型请求数 | 11 | 12 |
| 输入 tokens | 29588 | 32356 |
| 输出 tokens | 1629 | 834 |
| 总 tokens | 31217 | 33190 |
| 引擎累计生成时间 | 19.864 s | 23.701 s |
| 引擎累计排队时间 | 38.356 s | 62.829 s |
| 完整 Agent 耗时 | 74.071 s | 104.555 s |
| 非预期工具错误 | 0 | 1，已修复 |
| 预期 PowerShell 缺失错误 | 1 | 1 |
| assistant 仅含工具调用 | 否，7 轮伴随普通文本 | 是，12/12 |

输出减少 48.8%，总 tokens 增加 6.3%，没有整体加速。
原生组测试代码、回复长度、普通说明文本和行动顺序与引擎组不同，且引擎组多了错误修复；
这不是同内容、同 token 或同请求数的受控微基准，不能把输出差额全部归因于协议编码。
原生组模型编写的 7 项测试通过，引擎组为 6 项，双方使用相同的额外独立行为检查。

- `results/experiments/pi-all-tools-schema-20260918-a/`：真实 Schema、运行时信息、编码及非法帧检查。
- `results/experiments/pi-all-tools-engine-20260918-a/`：引擎模式完整消息、工具事件、逐次 usage/metrics、生成文件、独立验收。
- `results/experiments/pi-all-tools-native-20260918-a/`：同任务独立原生对照。

每个运行保存执行源码与 Pi 实现哈希，目录使用独立 SHA256SUMS。
推理侧 worker SHA256 为 `2286799e05d763eeda6425f5e69250b269d35796c43b31064fa3e3755b24bcea`，本地与远端一致。
沿用 yuesheng `/model` 服务，temperature=0、max_tokens=4096、thinking=false，每个会话独立 cache salt。
未重启共享服务，也未在本轮重新核验模型权重 revision。

```sh
node integrations/pi/run_scanner.mjs \
  --out results/experiments/NEW-RUN \
  --pi-root /path/to/pi-coding-agent \
  --host rs-yuesheng-gpu-vps \
  --worker /path/to/pi_engine_protocol.py \
  --all-tools true \
  --fixture benchmarks/data/pi-all-tools-fixture \
  --prompt benchmarks/data/pi-all-tools-task.txt \
  --max-turns 20
.venv/bin/python benchmarks/accept_pi_all_tools.py results/experiments/NEW-RUN
```

原生对照额外传 `--mode native`，输出目录必须不同。

## 适用范围

已接入当前安装版本的全部内置工具 Schema，实际成功执行 7 种内置工具及 reply_user，验证 PowerShell 缺失错误的回流。
这不等于完整 Pi CLI 迁移：图像工具结果、并行调用、取消时的流式行为、扩展工具的任意 JSON Schema、
会话持久化与生产并发尚未覆盖。当前每轮一个调用、非流式接收；未知 Schema 约束拒绝编译。
共享负载下单任务运行只能证明这条集成链路可用，不能证明稳定加速或生产正确率。

124 项 pytest、原始 raw SHA256 校验和 69 项 published claims 校验通过。
本轮没有修改原论文主结论、全局 Pi 配置、模型权重或共享推理服务配置。
