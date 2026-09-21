# 具体文件上下文与整任务描述分离

2026-09-21。修正内容码表的信息表达：新条目的执行证据保存 observed_paths，候选显示
实际观察到的工作区相对路径；旧 contract 字段明确显示为整个历史用户任务，不再称为
这份文件的行为契约。提示检查源码的导出、行为和依赖，不能把辅助脚本自动当成目标实现。

同一次入表的相同内容合并路径；源码、contract、条目 ID 算法、SQLite 列及检索逻辑
不变。元数据保存在原字符串 evidence 中，旧证据字符串仍可读，未记录路径时不猜测。
路径用于上下文，不限制新目标位置；未新增硬编码语言、文件名过滤或额外模型调用。
这不是为文件自动赋予经过验证的“实现/测试”角色，更不是语义兼容性证明。

## 真实复测

Pi 0.85.1，DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3。
与 warm-reuse-ablation-20260921-a 的任务、调度、预算和开关一致，仅 bridge.py 与
工具计划模块源码变化。两个家族各首次一次、重复三次、需求变化一次，共十任务，三组
交错串行，30 次完整 Agent。每任务重置文件，各组从独立空表持续学习；没有改用户码表。

两组 plan 都启用短引用、恢复补录、本地 tokenizer、session prefix cache，只有是否
允许复用不同；禁用组也学习。其他实验开关关闭。总输出限 17408、子工具参数限 2048，
任务限时 150 秒，无测试器重试。每次新 Pi 进程的启动、准备、推理、工具、恢复、回复
均计入，共享隧道和独立 oracle 另计。

| 十任务合计 | 朴素 | plan 禁用复用 | plan 开启复用 |
| --- | ---: | ---: | ---: |
| 正确并正常结束 | 10/10 | 10/10 | 9/10 |
| 完整耗时（秒） | 92.63 | 93.62 | 95.60 |
| 生成 token | 9399 | 6594 | 7140 |
| 逻辑输入 token | 85884 | 99993 | 111339 |
| 模型请求 | 32 | 29 | 24 |
| 分类控制记录 | 0 | 29 | 24 |
| 工具错误 | 0 | 1 | 3 |

无超时，usage 完整；30 个最终产物独立复验与原结果一致。复用组少请求但仍较慢且质量
下降，不能称作整体加速。不同轮的生成和规划轨迹有波动，不能将跨轮差值全部归因于
文件上下文；同轮禁用复用对照也没有展现 plan 稳定优于朴素。

## 覆盖到的改善和仍然失败的部分

JavaScript 首次任务再次发生 shell 引号错误，恢复时创建 test_unique.mjs。因此本次
码表也确实同时存在辅助测试与实现内容，分别记录 test_unique.mjs 和 unique_base.mjs。
三个重复任务均选中实现，独立审计引用内容也通过，未重现上轮误选测试脚本的问题。
这是一次针对既有混淆的正向观察，不能据三次选择证明该类错误已被彻底消除。

Python 首次重复仍重新生成，后两次正确引用，其中一次先读取文件，导致三次请求。
六次重复最终全部正确；复用组 44.79 秒、2911 生成 token，禁用组 56.58 秒、3905 token。
不能用这个较快子集覆盖总体质量问题。

unique_changed 仍错误复用大小写敏感实现，忽略新增大小写不敏感要求，工具成功且正常
回复，但独立验收失败。引用内容单独在临时副本运行 oracle 也失败，确认语义误命中仍在。
jsonl_changed 没有复用旧内容，但生成与修复过程中有两次工具错误，共 27.17 秒；单纯
改候选信息没有解决生成质量与恢复成本。

共六次引用的独立审计为五次正确、一次需求变化错误。元数据另从隔离实验状态只读导出，
ID 与源码哈希逐项和冻结 final-book 对齐，见汇总的 observed_entry_evidence；不修改归档。

## 验证与后续

541 项测试通过，新增覆盖实现与辅助文件路径分离、相同内容多路径合并、绝对路径转
工作区相对路径、旧证据兼容及候选描述。归档校验通过。

保留这项事实表达修正，但不能把它当作语义误复用的修复或新的提速结论。下一步主要
验收点仍是需求变化后不能错误复用；还需要减少正确任务中的冗余读取、检查生成和恢复。
短引用及恢复补录实验开关继续默认关闭，未推送。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/artifact-context-ablation-NEW \
  --tasks jsonl_base jsonl_repeat jsonl_changed unique_base unique_repeat unique_changed \
  --repeat-count 3 --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --warm-reuse-ablation --empty-book
```

[汇总、文件元数据与引用审计](ARTIFACT_CONTEXT_EVALUATION.json) ·
[冻结记录](../results/experiments/artifact-context-ablation-20260921-a/) ·
[前轮对照](WARM_REUSE_EVALUATION.md)
