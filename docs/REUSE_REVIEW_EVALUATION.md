# 同次生成中的内容复用核对实验

2026-09-20。默认关闭的 `PIJIT_REUSE_REVIEW=1` 扩展内容候选的 reuse_write 参数：
先输出最多 320 字符的 requirement_check，指出当前关键要求与保存内容是否一致；
随后 use_cached_content=true 使用原内容，或 false 并携带完整 content，在同一步生成
替代内容。解码后仍是普通 write，不向 Agent 工具传递核对元数据。false 不记录为命中。
外层 plan 格式、八个子工具上限和 2048 参数预算不变，不增加模型请求。

普通工具分支仍然可用，模板协议没有增加该核对。模型自述不是语义验证器，即使字段
符合 schema，也不能保证兼容性判断正确。新增单元测试覆盖缓存使用、同次替代生成、
元数据剥离和缺失决策字段拒绝。

## 真实运行与未覆盖之处

Pi 0.85.1，DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3，串行任务。
两组 plan 使用本地 tokenizer、session prefix cache、独立空表持续学习；模板、执行提示、
能力缓存、条件回复均关闭。四个既有开发任务：JavaScript 首次/重复，SQL NULL 语义首次/
变更。每题交错运行朴素、原 plan、核对 plan，共 12 次，无测试器重试。

| 指标 | 朴素 | 原 plan＋码表 | 核对 plan＋码表 |
| --- | ---: | ---: | ---: |
| 正确完成 | 4/4 | 4/4 | 4/4 |
| 完整任务耗时 | 40.28 s | 24.93 s | 23.22 s |
| 生成 token | 3904 | 1360 | 1255 |
| 逻辑输入 token | 49173 | 29644 | 29624 |
| 模型请求 | 18 | 8 | 8 |
| 分类控制 | 0 | 8 | 8 |
| 实际复用 | 0 | 0 | 0 |

时间含启动、准备、推理、工具和回复；不含共享隧道与独立验收。所有 usage 完整，无
工具错误、无超时；12 个保存产物复验一致。每个 plan 组新增 4 条内容，证明学习仍工作。

关键限制：两组四次行动都选择 tool:write，四次收尾选择 general。重复和变更任务虽有
候选，模型没有选择 reuse_content。核对参数因而从未实际生成，这轮不能证明新增核对
有效，不能将原 plan 与核对组的耗时差异归因于核对步骤。减少 token 和时间是本轮完整
plan 路径的观测结果，不是码表命中加速。也不能用零误复用夸大为语义问题已解决。

选项保持默认关闭。下一步需要分别测量分类选择和选中候选后的生成决策；若采用指定
分支的组件测试，必须与自然选择的完整 Agent 结果分开报告。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/reuse-review-ablation-NEW --fresh \
  --tasks unique_base unique_repeat nullable_base nullable_changed \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --reuse-review-ablation --empty-book
```

[独立汇总](REUSE_REVIEW_EVALUATION.json) · [原始记录](../results/experiments/reuse-review-ablation-20260920-a/)
