# Pi 编程任务 token 与耗时对照

2026-09-18。结论：上一轮输入 17,359、输出 3,674、合计 **21,033 tokens**，完整任务 **81.189 秒**。
补充两次每模式的真实 Agent 对照后，尚未验证稳定的端到端加速。相同工具参数和正文重编码后，
纯工具结构的输出 token 减少约 **6.0%～7.3%**，不能沿用短参数实验约 70% 的降幅。

## 原始运行的用量

来源：`results/experiments/pi-scanner-20260918-run1/inference.jsonl` 中 vLLM 返回的 usage。

| 轮次 | 工具 | prompt tokens | completion tokens |
|---|---|---:|---:|
| 1 | read | 1260 | 14 |
| 2 | bash | 1337 | 28 |
| 3 | write | 1448 | 1392 |
| 4 | write | 2870 | 2067 |
| 5 | bash | 4968 | 19 |
| 6 | reply_user | 5476 | 154 |
| 合计 | | **17359** | **3674** |

prompt tokens 按六次请求累计，包括再次提交的历史，不是独立新文本数量。
API 的 prompt_tokens_details 为 null，因此无法从本次记录给出缓存命中、计费或实际重复 prefill 的精确量。
这不是 Codex 本身本轮会话的 token 用量。

## 对照方法

目录：`results/experiments/pi-scanner-compare-20260918-b/`。顺序为 native1、engine1、engine2、native2。
模型、Pi 版本、工具 Schema、任务文本、温度 0、每请求输出上限 4096、thinking 关闭、执行隔离和
30 秒工具期限相同。每次使用新 workspace、新 cache salt，同次任务内复用 salt。
每组都在真实 Pi loop 中自行选择工具、编写程序及测试并执行，通过 reply_user 结束。

- native：vLLM 原生 tools API、`tool_choice=auto`、`parallel_tool_calls=false`、现有 DeepSeek V4 parser。
- engine：vLLM regex 约束分类/位置参数/原始正文，推理主机适配器构造对象。
- 两边共用非流式 SSH stdio 传输；对照的是工具协议，不是 Pi 默认 SSE provider 的完整性能。
- 原生回复里的说明文字被如实保留。原生两次均不是全工具输出；engine 两次均为全工具输出。
- 没有隔离其他 GPU 业务或改变 scheduler。输出程序、测试数量、工具路径可能不同；不能视为等量计算微基准。

前置探针 `pi-scanner-compare-20260918-a/native1` 使用了过严的“出现任何说明文字即终止”规则，
首轮返回说明文字和有效 write 调用后被适配器拒绝，未派发、未完成任务。
其 43.36 秒 / 输入 1284 / 输出 2922 的记录保留，但不作为完成任务的性能样本。
正式对照放行并记录原生说明文字，避免用人为中止代替原生任务性能。

## 实际结果

| 运行 | 模型轮次 | 输入 tokens | 输出 tokens | 合计 tokens | 全任务耗时 | 排队合计 | 生成间隔合计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| native1 | 6 | 21413 | 4060 | 25473 | 132.51 s | 66.13 s | 49.94 s |
| engine1 | 6 | 18480 | 3750 | 22230 | 94.40 s | 26.02 s | 56.26 s |
| engine2 | 6 | 16978 | 3561 | 20539 | 111.75 s | 56.94 s | 42.93 s |
| native2 | 8 | 33371 | 4283 | 37654 | 105.39 s | 41.79 s | 48.74 s |

四份程序全部通过同一份独立验收（每份 17 个检查项，其中一项重跑模型自身 unittest）。
模型自身测试数分别为 21、13、19、21，均实际通过；它们不是完全相同的生成内容或测试工作量。

| 每模式两次的均值 | native | engine |
|---|---:|---:|
| 全任务耗时 | 118.95 s | 103.08 s |
| 引擎排队合计 | 53.96 s | 41.48 s |
| 调度至末 token 合计 | 50.62 s | 50.73 s |
| 首末 token 生成间隔合计 | 49.34 s | 49.59 s |
| 输出 tokens | 4171.5 | 3655.5 |
| 输入+输出 tokens | 31563.5 | 21384.5 |

均值上全任务耗时减少 **13.35%**，耗时比 native/engine 为 **1.154**，仅为本批观察值。
第一组 engine 比 native 少用约 28.8% 时间，第二组反而多用约 6.0%。平均生成间隔没有缩短，
平均排队差约 12.48 秒，解释了约 15.87 秒任务耗时差中的大部分。
生成间隔是引擎首末 token 之间的墙钟时间，可能包含调度停顿，不是纯 GPU kernel 时间。
输入和总 token 的差异还受轮次数、工具结果、生成程序和历史长度影响，不能全部归因于协议。

## 相同内容重编码

使用实际 native 返回的 token IDs，经同一模型 `/detokenize` 还原；再 `/tokenize` 后与原 IDs 全部一致。
把实际工具名、参数值、代码和最终答复保持不变，经本协议重新编码并 tokenize，不重新生成内容。
本实验每个 native 回合恰好一个工具调用；compact 编码计数额外加一个实际使用的 EOS token（ID 1）。
这只是编码长度核验，不是 compact 反事实运行耗时。

| 同内容轨迹 | native 实际输出 | 去掉说明文字后的 native 工具帧 | compact+EOS | 含说明文字的节省 | 纯结构节省 |
|---|---:|---:|---:|---:|---:|
| native1 | 4060 | 3983 | 3743 | 7.81% | 6.03% |
| native2 | 4283 | 4193 | 3886 | 9.27% | 7.32% |

原生输出确实使用 `<｜DSML｜tool_calls>` 等标记，代码正文已经可以原样生成。
我们的方案主要省工具/参数标签，以及通过全工具协议省掉旁白；代码正文仍必须生成。
证据：`same-values-tokenization.json`、native1 的 `structure-only-tokenization.json` 与
`first-write-detokenized.json`。不能声称所有原生工具输出都要逐字符做 JSON 转义。

## 复现与证据

沿用 [Pi 实验](PI_ENGINE_TOOLCALL_EXPERIMENT.md) 的 runner，分别追加 `--mode native` 或 `--mode engine`，
每次指定新的输出目录。每次完成后运行：

```sh
python benchmarks/accept_pi_scanner.py <run-directory>
python benchmarks/reencode_pi_calls.py <native-run-directory>
python benchmarks/summarize_pi_comparison.py <comparison-root> --output comparison-v2.json
```

所有输出 create-only。`comparison-v2.json` 为最终汇总；首次生成的 `comparison.json` 数值相同，
但嵌套 `engine_seconds` 的字段名误留 `_ms` 后缀，保留原件并在 v2 修正字段名，没有改计时值。
源文件快照、实际 Pi 文件哈希、逐请求 usage/metrics/token IDs、工具事件和独立验收均随证据保存。
原始 six-turn 运行及 Phase 1 证据未覆盖。仓库 48 项 pytest、raw SHA256、69 项 published claim 校验通过。
