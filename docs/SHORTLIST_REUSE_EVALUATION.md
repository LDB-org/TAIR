# 候选筛选修复后的真实 Agent 对照

2026-09-20。Pi 0.85.1，yuesheng 6×RTX 5090，既有 DeepSeek-V4-Flash-Vision-Exp
服务（TP2/PP3）。串行执行，两类自编任务：JavaScript 字符串去重、SQLite 分组汇总。
每类按首次、重复、变更约束顺序运行，每题交错运行三个组，共 18 次。
两条 plan 路径使用本地 tokenizer、session prefix cache；模板、能力缓存、条件回复关闭。
生成上限 17408，plan 每子工具参数限 2048。独立空码表在本组任务之间持续积累，
未清空用户码表，未重启服务。总耗时包含 Agent 启动、请求准备、模型请求、工具执行、
所有错误恢复及最后回复；共享隧道建立和独立 oracle 验收不计入任务时间。

| 指标 | 朴素多工具 | plan 禁用复用 | plan 开启码表 |
| --- | ---: | ---: | ---: |
| 完成且独立验收通过 | 6/6 | 6/6 | 6/6 |
| 完整耗时 | 44.56 s | 53.53 s | 50.11 s |
| 生成 token | 4070 | 3484 | 2758 |
| 逻辑输入 token | 51503 | 58999 | 66276 |
| 模型请求 | 20 | 16 | 17 |
| 分类控制记录 | 0 | 16 | 17 |
| 工具错误 | 0 | 4 | 3 |

18 个保存产物全部独立复验，结果与原始 oracle 一致；全部 usage 完整，无超时。
开启码表比同一 plan 禁用复用少 6.4% 总时间，但仍比朴素慢约 12.5%。该总量差异包含
生成轨迹和错误恢复的差异，不能归因于检索修复；本轮没有运行旧版检索的对照。

## 重复与变更

两项重复任务均实际正确复用。JavaScript 重复任务从禁用复用的 6.15 s / 370 token
降到 5.11 s / 230 token。SQL 重复任务从 6.93 s / 449 token 增到 9.83 s / 470 token：
复用内容正确，但模型运行查询时尚未建立 events 表，错误恢复增加了两次模型请求。
两项重复合计：禁用复用 13.09 s / 819 token，开启码表 14.93 s / 700 token。
因此不能把两次正确命中写成稳定热任务加速。

两项约束变更均未复用旧内容，生成结果通过验收。样本只有两项，且是既有开发任务，
不能据此认定此前自然语言误命中已解决。任务也没有专门构造重复候选挤占，因此没有
证明新检索顺序是这次命中或拒绝复用的原因。

## 错误恢复的证据

plan 禁用复用的 JavaScript 首次任务先出现 shell 引号错误，随后将测试脚本写到 /tmp，
相对 import 指向了错误目录，并重复失败一次；最终完成，三次错误全部计入耗时。
开启码表的 SQL 首次和重复任务均出现未建表的查询错误。内容复用只省掉文件生成，
无法自动修复后续模型生成的测试命令。下一步需要检验通用的执行前提提示能否减少
这类错误，且不引入额外模型调用或省略必要验证；不能按某道题硬编码命令。

源码、任务及运行配置在推理前冻结，结束时校验源码未变化；原始记录含失败步骤。
本轮只有实验和报告新增，运行时源码沿用已通过 489 项测试的版本。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/shortlist-reuse-ablation-NEW \
  --tasks unique_base unique_repeat unique_changed totals_base totals_repeat totals_changed \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --ablation --empty-book
```

[独立汇总](SHORTLIST_REUSE_EVALUATION.json) · [原始记录](../results/experiments/shortlist-reuse-ablation-20260920-a/)
