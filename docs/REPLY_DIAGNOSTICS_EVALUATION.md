# 条件回复未采用的诊断与失败复测

2026-09-20。不改变回复接纳条件，只增加诊断：成功 plan 没有可用条件回复时记录
planned_reply_skip，区分 missing_completion_metadata、model_requested_continuation 和 cancelled；
提交了回复但不能接纳时，planned_reply_offer 增加原因，包括需要解释的工具、截断、非文本、
未预声明输出、预期输出不符或无效元数据。原因字段不记录工具输出正文。

## 真实对照

Pi 0.85.1，DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3。
失败修复、CSV 汇总和 JSON 修改三个既有任务，各运行朴素、plan 禁用复用、同样 plan
开启条件回复三组，共九次交错串行运行。两个 plan 组禁用复用但保留学习，使用本地
tokenizer 和 session prefix cache；执行提示、复用核对、能力缓存关闭，恢复规则为原默认。
每任务 150 秒上限，无测试器重试，使用独立空状态，源码和任务在推理前冻结。

| 指标 | 朴素 | 普通 plan | 条件回复 plan |
| --- | ---: | ---: | ---: |
| 产物正确且正常结束 | 3/3 | 3/3 | 1/3 |
| 再要求显式操作顺序通过 | 2/3 | 2/3 | 1/3 |
| 完整任务耗时 | 31.26 s | 22.87 s | 164.41 s |
| 生成 token | 2892 | 1355 | ≥8528 |
| 逻辑输入 token | 44827 | 27729 | ≥623309 |
| 已记录模型请求 | 16 | 8 | ≥65 |
| 已记录分类控制 | 0 | 8 | ≥64 |

计时包含启动、准备、推理、工具、失败恢复和回复；共享隧道与独立验收另计。条件回复
组有一次超时，usage 不完整，相关计数仅为已记录下限；其余 usage 完整。
九个归档产物独立复验与原 oracle 一致，并另审计操作顺序。不把 2/3 写成全部正确加速。

## 诊断结果

条件回复组成功执行后的日志共 61 次 missing_completion_metadata，没有 offer，没有
prepared reply delivery。不能把 61 次都当作可省请求：其中有读取结果必须回模型解释。
能够确认的是本轮没有现成条件回复被运行时门槛挡住，放宽门槛无法修复本轮未采用问题。

- 修复任务：按要求先执行失败检查，完成修复后不断重复 read＋相同检查，150.09 秒到期。
  已记录 61 次模型请求；最终文件通过 oracle，但任务没有正常结束。失败轨迹完整保留。
- CSV：通过，但没有条件回复，仍需两次模型请求。
- JSON：同一 plan 先 read，再在尚未看到读取结果时运行 bash，将顶层 port 改为 8443，
  没有修改 service.port；自写检查只检查了错误的顶层字段，最终回复还声称正确完成。

朴素修复任务先执行了 ls/echo 再运行指定检查，普通 plan 则先 read 后修复，均未满足
“先运行 python3 check_calc.py”的严格顺序验收。检查文件三组均未修改。

条件回复继续默认关闭。本轮没有证明该机制加速，反而重现了规划与结束决策的退化。
下一步要解决生成协议的实际采用和恢复后的结束决策，不能用更宽松的执行器放行替代。

509 项测试通过，含真实 Pi 适配器对正确/不匹配回执及工具错误的集成验证。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/reply-diagnostics-NEW --continuation \
  --tasks edit_state_base repair_failure csv_totals \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --success-reply-ablation --empty-book
```

[独立汇总及顺序审计](REPLY_DIAGNOSTICS_EVALUATION.json) · [原始记录](../results/experiments/reply-diagnostics-20260920-a/)
