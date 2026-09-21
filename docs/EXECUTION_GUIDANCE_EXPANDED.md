# 执行提示与最终内容入表的扩展验证

> 后续验收更正：增加正数分组后，朴素组 nullable_changed 的 SQL 被发现错误排除了
> 正数分组，正确完成数应为 5/6，而非下表原验收口径的 6/6。原 plan 仍为 5/6，提示组
> 仍为 6/6。耗时原值不变，但不能再把 20.1% 写成双方全部正确时的加速。
> 原始记录保留，详见 [补充审计](NULLABLE_ORACLE_AUDIT.json)。

2026-09-20。沿用 Pi 0.85.1、DeepSeek-V4-Flash-Vision-Exp、yuesheng 6×RTX 5090
TP2/PP3 服务。六项既有自编开发任务：JSON 定点修改、先运行失败检查再修复、CSV 汇总、
Unicode casefold 去重、两种不同 NULL 分组语义的 SQL。三组按任务交错、串行运行，共 18 次。
它们不同于上一轮提示开发使用的去重/汇总任务，但并非独立外部评测集。

两条 plan 均使用最新最终文件内容入表、本地 tokenizer、session prefix cache；只有
提示组开启 `PIJIT_PLAN_EXECUTION_GUIDANCE=1`。两组从各自独立空表开始，组内持续学习。
模板、能力缓存、条件回复关闭；输出总限 17408，plan 子工具参数限 2048。完整耗时包含
启动、准备、模型请求、工具、所有错误恢复及回复；共享隧道与独立验收另计。

| 指标 | 朴素 | 原 plan＋码表 | 提示 plan＋码表 |
| --- | ---: | ---: | ---: |
| 完成且独立验收通过 | 6/6 | 5/6 | 6/6 |
| 完整耗时 | 66.35 s | 46.02 s | 52.99 s |
| 生成 token | 6445 | 2612 | 3196 |
| 逻辑输入 token | 84023 | 57201 | 62372 |
| 模型请求 | 30 | 15 | 16 |
| 分类控制记录 | 0 | 15 | 16 |
| 工具层错误 | 1 | 1 | 2 |

全部 usage 完整，无超时。18 个保存产物独立复验与原始 oracle 一致。失败恢复任务三组
均先执行指定检查、未修改检查文件，随后完成修复；这里的一次初始失败是任务要求。

提示组相对朴素本轮总耗时少 20.1%，生成 token 少 50.4%；但原 plan 少做正确工作导致
更短的 46.02 秒不能作为有效加速。提示组的 Unicode 任务为 10.24 秒，原 plan 7.40 秒，
朴素 7.45 秒，均正确且无工具错误；提示会改变生成轨迹，并不保证每项任务变快。

## 错误复用与恢复

原 plan 在 nullable_changed 实际复用旧 SQL，遗漏 `HAVING COUNT(value) > 0`，
未排除全 NULL 分组。工具层无错误、模型正常结束，但独立验收失败。这重现了自然语言
新约束下的语义误命中，表明此前筛选顺序及最终内容观察修复不足以解决它。

提示组该任务没有复用旧条目，也出现一次检查失败，随后修改查询，最终保存产物含上述
条件并通过独立验收。不能因此认定提示是通用语义守卫，也不能把它称为确定性错误预防。
本轮没有正确复用任务，因而完全不能证明码表热任务加速；收益主要应作为整个 plan
路径的观测结果，而不是动态码表贡献。

## 学习路径

完成日志显示：原 plan 观察到 4 个最终文件内容、新增 3 个条目；提示组观察到 4 个、
新增 4 个条目，均无跳过文件。最终文件观察在真实 Agent 中正常工作，但记录最终字节
并不等于内容正确，既有语义失败依然存在。纯 bash 写入自动学习尚未实现。

提示继续默认关闭，下一步需重复对照和针对语义误命中的独立改进。本轮不修改运行时
源码、不重启服务、不清空用户数据库。运行时沿用已通过 496 项测试的版本；归档校验
通过，2853 个导入文件、61889 个原始校验条目保持一致。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/execution-guidance-expanded-NEW --continuation --fresh \
  --tasks config_1 repair_failure csv_totals normalize_labels nullable_base nullable_changed \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --execution-ablation --empty-book
```

[独立汇总与流程审计](EXECUTION_GUIDANCE_EXPANDED.json) · [原始证据](../results/experiments/execution-guidance-expanded-20260920-a/)
