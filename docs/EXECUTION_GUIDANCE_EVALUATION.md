# 同次 plan 请求中的执行前提提示

2026-09-20。新增默认关闭的 `PIJIT_PLAN_EXECUTION_GUIDANCE=1`：在原有系统提示中要求
准备检查所需资源、考虑工作目录和相对路径解析、正确处理 shell 引号；已知前提可以与
检查放入同一 plan，未知状态先检查。保留用户操作顺序和全部必要检查，不允许压制错误
或放宽断言。不增加模型请求、不增加工具、不编码题目答案。

## 真实对照

Pi 0.85.1，DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3。
JavaScript 去重和 SQLite 汇总各含首次、重复、变更约束；每题交错运行朴素、原 plan＋
码表、提示 plan＋码表三组，共 18 次。两条 plan 除提示外配置相同，各自使用独立空表，
后续保留学习。使用本地 tokenizer、session prefix cache，模板/条件回复/能力缓存关闭。
输出总限 17408，plan 每子工具参数限 2048。任务 150 秒上限，无测试器重试。
完整时间包含启动、准备、推理、工具、错误恢复及回复；共享隧道和独立 oracle 除外。

| 指标 | 朴素 | 原 plan＋码表 | 提示 plan＋码表 |
| --- | ---: | ---: | ---: |
| 完成且独立验收通过 | 6/6 | 5/6 | 6/6 |
| 完整耗时 | 44.77 s | 186.09 s | 39.06 s |
| 生成 token | 4233 | ≥2571 | 2032 |
| 逻辑输入 token | 51776 | ≥50025 | 55384 |
| 已记录模型请求 | 20 | ≥12 | 14 |
| 已记录分类控制 | 0 | ≥12 | 14 |
| 工具层报告错误 | 0 | 1 | 1 |
| 正确复用任务数 | 0 | 1 | 1 |

提示组对朴素本轮少 12.7% 总时间、52.0% 生成 token；4/6 项更快，配对相对节省中位数
18.3%。所有保存产物经独立复验。任务来自既有开发集，每题每组只运行一次，不是独立
泛化基准，不能承诺生产收益。提示只改变输入，生成路径及随后积累的码表内容也随之变化。

## 超时与实际限制

原 plan 的 totals_changed 错误复用旧 SQL，检查输出包含缺表错误，但后续 shell 命令
返回成功，工具层未报告失败。之后一次 assistant 请求未在 150 秒内结束，usage 不完整；
产物也未通过 oracle。表中的 token、请求和分类控制均只是已记录下限。不能将该超时
归因于某个已证实的引擎问题，也不能用这个长尾制造稳定的大倍数收益。
超时后等待约 3.40 秒，确认后端 running=waiting=0 才运行下一项。
仅作事后敏感性分析，同时排除三组 totals_changed 后：朴素 37.82 s，原 plan 35.91 s，
提示 plan 29.17 s；主结果仍保留所有任务。

提示组 SQL 首次任务先建表再运行查询，避开缺表错误；但使用 bash 写文件，绕过当前
只观察 write 的学习路径，SQL 重复任务因此未命中。其 JavaScript 重复任务正确命中。
提示组 totals_changed 仍出现缺表错误，之后恢复成功。因此该提示未消灭前提错误，
也未解决语义误命中、shell 成功掩盖中间失败或 bash 写入无法自动入表的问题。

默认保持关闭。下一步应扩大并重复受控对照，同时单独解决写入观察范围，不把提示
当作确定性执行保障。本轮无服务重启、无用户码表清空。

## 验证与复现

489 项测试通过；归档校验通过：2853 个导入文件、61590 个原始校验条目。
实验记录实际 `execution_guidance_enabled` 并逐请求校验组别，源码在推理前冻结，
完成时复核未改变。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/execution-guidance-ablation-NEW \
  --tasks unique_base unique_repeat unique_changed totals_base totals_repeat totals_changed \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --execution-ablation --empty-book
```

[独立汇总](EXECUTION_GUIDANCE_EVALUATION.json) · [原始证据](../results/experiments/execution-guidance-ablation-20260920-a/)
