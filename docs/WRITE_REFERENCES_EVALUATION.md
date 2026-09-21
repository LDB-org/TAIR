# 普通 write 分支中的短内容引用

2026-09-20。新增默认关闭的 PIJIT_WRITE_REFERENCES=1。原协议只有分类选中复用分支时
才能使用码表；普通 write、其他首工具后的 write、通用 plan 都不能引用已有内容。
现在这些位置的 write.content 可为普通字符串或 {"stored": N}，N 绑定当前候选目录中的
非模板条目。桥接先验证 wire schema，展开原始文本后再验证普通工具 schema，交由 Pi 执行。
未知索引、负数、布尔值和额外字段被拒绝；关闭开关时对象引用不可用。可在同一 plan 中
引用多个候选。没有放宽文件状态检查、最终内容学习或成功判定。

这条路径保留既有分类内核，不增加模型调用，但短引用本身由模型生成，不是第二个分类
内核。它移除协议上的复用障碍，不保证候选语义正确，也不等于提高了分类准确率。

## 两轮完整 Agent 对照

Pi 0.85.1，DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3。
JavaScript 首次/重复、SQLite NULL 聚合首次/需求变化四任务，每题三组交错串行执行；
独立重复两轮，共 24 次。两轮 manifest 哈希完全相同，源码、任务和调度相同。
两组 plan 均从独立空表开始，组内持续学习，使用本地 tokenizer 和 session prefix cache。
条件回复、执行提示、复用核对、模板、能力缓存关闭；朴素启用原生多工具。
两组输出总限 17408，plan 每子工具参数限 2048；每任务 150 秒，无测试器重试。

| 四任务合计 | 朴素 A / B | 原 plan A / B | 短引用 plan A / B |
| --- | ---: | ---: | ---: |
| 正确并正常结束 | 4/4 / 4/4 | 4/4 / 4/4 | 4/4 / 4/4 |
| 总耗时（秒） | 42.52 / 38.42 | 25.04 / 37.11 | 22.83 / 22.74 |
| 生成 token | 4085 / 3671 | 1398 / 2462 | 1139 / 1203 |
| 逻辑输入 token | 55577 / 51734 | 30171 / 43070 | 30786 / 30801 |
| 模型请求 | 20 / 19 | 8 / 12 | 8 / 8 |
| 分类控制记录 | 0 / 0 | 8 / 12 | 8 / 8 |
| 工具错误 | 1 / 1 | 0 / 3 | 0 / 0 |
| 完成且实际复用的任务 | 0 / 0 | 1 / 0 | 1 / 1 |

耗时包含启动、准备、推理、工具、恢复和最终回复，共享隧道与独立 oracle 另计。
无超时，usage 完整，24 个保存产物独立复验通过。SQL oracle 包括正数和、零、负数、
全 NULL 以及空表，不能通过错误删掉正数分组蒙混过关。

## 哪部分机制真正生效

短引用组两轮 JavaScript 重复任务都分类为 tool:write，随后展开码表内容，重新执行检查，
最终产物正确；其耗时分别 5.10 / 5.35 秒，生成 token 249 / 241，均两次模型请求。
原 plan A 轮通过旧 reuse_content 分支成功复用，5.50 秒、266 token、两次请求。
因此新路径确实被模型采用，但 A 轮差值不足以证明它必然比旧复用路径快。
两轮 SQL 需求变化均生成新文本，没有错误沿用旧查询。

B 轮原 plan 首次及重复任务均发生 shell 引号错误，随后恢复完成。失败 plan 中已经
成功的 write 没有入表，之后只补跑检查也没有补录，所以重复任务首次决策仍为 empty_book。
这是独立的入表时机缺口，不能归为分类失败。B 轮的较大时间差包含工具错误和恢复成本，
不能全部归功于短引用。空表阶段也存在生成长度差异，不能解释为缓存加速。

本实验只有两个任务家族、两轮自编任务，没有禁用复用对照臂；能证明协议路径可用及
此次端到端结果，不能隔离码表净收益或证明任意任务通用加速。开关继续默认关闭。

## 验证与复现

521 项测试通过，包含首 write、后续 write、通用分支的多条目展开、禁止修改原始 wire、
非法引用拒绝、默认关闭和完整生成回退。没有重启服务或清空用户码表。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/write-references-ablation-NEW --fresh \
  --tasks unique_base unique_repeat nullable_base nullable_changed \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --write-references-ablation --empty-book
```

[第一轮汇总](WRITE_REFERENCES_EVALUATION.json) · [第二轮汇总](WRITE_REFERENCES_EVALUATION_B.json)

[第一轮原始记录](../results/experiments/write-references-ablation-20260920-a/) ·
[第二轮原始记录](../results/experiments/write-references-ablation-20260920-b/)
