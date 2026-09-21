# 恢复补录的在线对照

2026-09-21。Pi 0.85.1，DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3。
三个人工构造的 JSONL 任务：首次、相同行为重复、新增拒绝任意嵌套重复键要求。检查脚本
首次故意失败，第二次检查实际语义，制造可重复的“write 成功、后续 bash 失败、仅补跑检查”
路径。它是定向恢复实验，不代表一般任务的失败分布。

三组为朴素原生工具、短引用 plan、同样短引用 plan 加恢复补录。两组 plan 只改变
PIJIT_RECOVERY_ADMISSION，均从独立空表开始，组内持续学习，启用本地 tokenizer、
session prefix cache 和 write references；其他实验开关关闭，恢复仍是原整轮策略。
三任务各组三次交错串行运行，共九次；输出总限 17408、plan 每子工具参数限 2048；
150 秒任务限，无测试器重试，源码和任务推理前冻结，不修改用户码表或重启服务。

## 结果

| 三任务合计 | 朴素 | plan 补录关闭 | plan 补录开启 |
| --- | ---: | ---: | ---: |
| 正确并正常结束 | 3/3 | 3/3 | 3/3 |
| 完整耗时（秒） | 41.17 | 24.35 | 23.30 |
| 生成 token | 3817 | 1356 | 1177 |
| 逻辑输入 token | 58930 | 32081 | 33458 |
| 模型请求 | 19 | 9 | 9 |
| 分类控制记录 | 0 | 9 | 9 |
| 工具错误（预设一次/任务） | 3 | 3 | 3 |
| 最终内容表条目数 | — | 0 | 3 |

计时包括启动、准备、推理、工具执行、错误恢复和最终回复，共享隧道与独立 oracle
另计。无超时、usage 完整。九个保存产物独立复验全部通过，同时校验检查脚本未修改、
marker 正好记录两次检查；新增要求的重复键语义也通过。

| 单任务 | 补录关闭秒 / token | 补录开启秒 / token |
| --- | ---: | ---: |
| 首次 | 8.18 / 441 | 8.25 / 431 |
| 重复 | 7.63 / 391 | 6.48 / 247 |
| 需求变化 | 8.54 / 524 | 8.58 / 499 |

重复任务观测耗时减少约 15.1%、总生成 token 减少约 36.8%，两组均三次模型请求。
首次和变更任务没有加速；整个三任务合计仅减少约 4.3% 时间。每组每任务一次，不支持
稳定收益的统计结论，也不能将朴素与 plan 的差距全部归给补录。

## 确认实际路径，而非只看候选数

补录开启组首次任务结束时新增 1 条内容，后续重复任务分类为 tool:write，短引用展开
该条目并成功写入。第一份写入 plan 的生成 token 从关闭组 160 降到 49；最终文件与
首次文件字节相同，独立验收通过。新增重复键约束时，已有候选仍被放弃，生成新代码。
补录本地执行约 1.8–2.9 毫秒，没有额外模型请求或桥接进程。

注意：标准整 plan 成功复用计数三组仍为零，因为引用后的 write 虽成功，紧随检查
按实验设计失败。按 request_id 匹配真实 toolResult，completed 前缀明确确认 write
成功，failed_step=1 指向模拟失败检查。单步内容复用与整个 plan 成功复用必须分开；
本实验没有为了提高命中数追补复用奖励。详细汇总附 recovery_path_audit 和源码哈希。

默认继续关闭。当前证据证明恢复补录→后续检索→短引用执行链路在线生效，并在这个
重复任务出现净收益；不能证明普遍正确的语义匹配或任意任务越用越快。

537 项测试通过，包括检查器必须先失败再成功及不能篡改的回归测试。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/recovery-admission-ablation-NEW \
  --tasks recovery_jsonl_base recovery_jsonl_repeat recovery_jsonl_changed \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --recovery-admission-ablation --empty-book
```

[汇总与单步审计](RECOVERY_ADMISSION_EVALUATION.json) ·
[原始记录](../results/experiments/recovery-admission-ablation-20260920-a/) ·
[实现与离线验证](RECOVERY_ADMISSION.md)
