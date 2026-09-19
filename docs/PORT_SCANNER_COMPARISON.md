# Python 端口扫描工具：朴素与 TAIR 单次真实任务

2026-09-19。在同一个现有 yuesheng 5090 模型服务上，正式运行两次：先朴素 Pi 原生多工具，再开启当前外层优化和安全码表的 TAIR。模型服务未重启或改动。两组使用同一个绝对项目路径，每次恢复为空 scanner.py，独立空状态与码表，同样提示、600 秒任务上限及 8192-token 单次外层回复上限。Pi 与工具运行在本机 macOS，推理经 SSH 发往 GPU。

## 任务

用 Python 标准库编写 scanner.py、README.md 和 unittest 测试。单 IPv4 目标 TCP connect；端口列表/范围、排序去重、有限正超时、1..256 并发线程、文本/JSON 输出、非法参数 exit 2、导入无副作用、Ctrl-C 无 traceback。测试明确限制为自己创建的 127.0.0.1 临时端口，不得扫描外部目标、已有服务或大范围端口。

精确提示、独立验收代码和配置位于 `benchmarks/benchmark_port_scanner.py` 及正式记录 manifest。验收程序不提供给 Agent，也不配置为 TAIR 运行时验证。仅使用自建监听与非监听临时 sockets 验收开放/关闭状态、相邻端口范围、排序去重及 JSON。非法参数和导入测试单独检查。

## 正式结果

| 指标 | 朴素原生多工具 | TAIR |
|---|---:|---:|
| Agent 耗时 | 80.725781 秒 | 204.220186 秒，人工中止 |
| 已记录输出 token | 8,078 | 6,503，未完成 |
| 外层模型请求 | 15 | 12 |
| 已记录输入 token | 141,376 | 94,532 |
| 分类控制记录 | 0 | 0 |
| compact_edit / 码表命中 | 0 / 0 | 0 / 0 |
| 独立基础功能验收 | 通过 | 失败：接受 --timeout inf |
| 额外独立验收时间 | 2.173943 秒 | 0.412202 秒 |
| 结束状态 | 正常回复结束 | 操作者停止 |
| 整体 usage_complete | true | false |

Agent 耗时包括启动、所有模型调用、工具、自测、恢复及回复；不含夹具和 SSH 准备。TAIR 计时截止操作者停止，没有成功结束回复。输出 token 为所有已记录模型回复总和，包含工具参数、生成代码和最终回答，分类控制单列且本轮均为零；并非只统计最后回复。独立验收时间不混入主表 Agent 耗时。

**没有有效的加速比或 token 节省比例：TAIR 本次未完成任务，产物也未通过基础验收。** 从零编写新程序未进入 compact_edit，因此没有动态码表收益可归因。一个样本也不能代表一般编程能力。

## 测试范围违规与中止

- 朴素产物通过预设基础功能 oracle，但自带测试还连接固定本机端口 1 和 80，未完全遵守只访问自己创建的临时端口这一要求。因此不能把基础 oracle 通过当成全部需求合规。
- TAIR 自带测试曾有一个错误预期：把反向端口范围当成合法；Agent 修正后继续测试。
- TAIR 随后为了检查 Ctrl-C，执行了本机 1..65535 端口扫描，并对未授权的 `10.255.255.1` 发起扫描；最后一个命令为单 worker、1..65535 端口、每端口 5 秒超时。发现后立即杀死扫描进程组并终止 Agent，确认扫描进程、Agent 与 SSH 隧道全部退出。原始命令仅保留为证据，未重放。
- 中止后固定 oracle 检出 `--timeout inf` 返回 0，而需求要求 exit 2。原始产物没有手工修复或替换。

这说明提示约束并不等于工具执行边界。此前外层搜索提示未提供网络隔离。未来类似联网工具编写评估需要执行层限制/受控替身；本轮不追加扫描或通过成功重跑掩盖失败。

## 先前预算配置异常

正式对照前误用了小编辑实验的 2048-token 单次上限。朴素组多次输出达到上限，长文件工具参数不完整并反复重试。该次在完成配对前被停止，保存在 `results/experiments/port-scanner-20260919-a/`，标记为无效预算试跑，不能称为成功/完整的性能样本。没有删除或混入正式结果。

随后为两组统一设置 8192，在新的 `port-scanner-20260919-b/` 目录从空项目重新正式运行各一次。给原生跟踪器和 TAIR 原生规划器增加了可配置上限，默认仍为 2048。环境变量分别为 `TAIR_NATIVE_MAX_TOKENS` 和 `PIJIT_PLANNER_MAX_TOKENS`。357 项回归测试通过。

## 文件与复现

- 朴素原始交付：`results/experiments/port-scanner-20260919-b/native_multi/project-after/`
- TAIR 原始未通过交付：`results/experiments/port-scanner-20260919-b/hybrid/project-after/`
- 统计及范围审阅：`PORT_SCANNER_COMPARISON_RESULTS.json`
- 两轮原始轨迹、源码快照、失败原因和 SHA-256 均保留。凭据和模型权重不入库。

```sh
python benchmarks/benchmark_port_scanner.py --url "$URL" \
  --tokenizer-revision "$VERIFIED_REVISION" \
  --out results/experiments/port-scanner-NEW --timeout 600
```

运行器使用普通 shell 工具，提示不是网络隔离。重跑前应先加执行层网络边界；上面的命令描述本轮可复现参数，不意味着现有运行器已解决范围违规。
