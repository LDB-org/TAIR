# 条件回复与最新结果恢复的复测

2026-09-20。Pi 0.85.1、DeepSeek-V4-Flash-Vision-Exp、yuesheng 6×RTX 5090，
TP2/PP3。三个任务分别是 JSON 状态修改、失败修复、CSV 汇总，每题交错串行运行
朴素、普通 plan、条件回复 plan，共九次。两个 plan 组禁用复用但持续学习，使用独立
空表、本地 tokenizer、session prefix cache；执行提示、复用核对、模板和能力缓存关闭。
每任务上限 150 秒，无测试器重试，未改动用户码表或重启服务。

## 结果

| 三任务合计 | 朴素 | 普通 plan | 条件回复 plan |
| --- | ---: | ---: | ---: |
| 产物正确且正常结束 | 3/3 | 3/3 | 3/3 |
| 同时满足显式执行顺序 | 3/3 | 2/3 | 3/3 |
| 完整耗时（秒） | 28.34 | 25.66 | 27.07 |
| 生成 token | 2620 | 1396 | 1489 |
| 逻辑输入 token | 35498 | 31069 | 36302 |
| 模型请求 | 13 | 9 | 9 |
| 分类控制记录 | 0 | 9 | 9 |
| 工具错误 | 1 | 0 | 2 |

时间包含启动、准备、推理、工具、恢复和回复，共享隧道与独立验收另计。无超时，usage
完整，九个归档产物独立复验通过。普通 plan 修复任务先 read，未遵守先运行指定检查的
要求；不能把这一组标记为完整任务全部通过。三组均未修改验收检查文件。

条件回复组修复任务 9.94 秒、4 次请求完成；上一轮同一组 150.09 秒超时，至少记录
61 次请求，虽然文件修好却反复读取和检查。两个 manifest 的源码哈希、任务、调度和
其他配置一致，仅 recovery_latest 不同。模型轨迹仍存在波动，本次单次对照不能证明
一般性速度提升或彻底消除循环。

关键诊断：本轮四次 planned_reply_skip 均为 missing_completion_metadata，零次 offer、
零次预生成回复交付。因此观察到的是恢复路径变化后的完成改善，不能归因于条件回复
省掉最后一轮请求。码表复用关闭，本轮也不能证明热表收益。

## 有限默认调整

仅当显式启用 PIJIT_PLAN_SUCCESS_REPLY=1 且没有指定 PIJIT_RECOVERY_LATEST 时，
使用最新结果恢复。显式设置 PIJIT_RECOVERY_LATEST=0 仍保留历史整轮恢复策略。
普通 plan 行为不变，两个实验功能整体仍默认关闭。成功读取不证明失败检查已经修复，
仍需模型解释结果并完成验证。没有放宽回复交付条件或删掉历史失败信息。

四个新增参数化用例验证功能关闭、条件回复开启、显式禁用恢复策略和独立启用恢复策略。
全套 513 项测试通过；归档检查通过，覆盖 2853 个导入实验文件与 63074 条原始校验项。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/reply-latest-recovery-NEW --continuation \
  --tasks edit_state_base repair_failure csv_totals \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --success-reply-ablation --recovery-latest --empty-book
```

[独立汇总及顺序审计](REPLY_LATEST_RECOVERY_EVALUATION.json) ·
[原始记录](../results/experiments/reply-latest-recovery-20260920-a/) ·
[上一轮失败诊断](REPLY_DIAGNOSTICS_EVALUATION.md)
