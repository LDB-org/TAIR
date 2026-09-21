# 相同任务文字、不同文件状态下的 edit 学习验证

2026-09-20。新增三个预先冻结的 JSON 修改任务，提示完全相同：读取 service.json，
仅把 service.port 改成 8443，保留其他所有值。首次和重复的初始文件完全相同；第三次
初始文件更换 Unicode 标签、数组、布尔值、其他端口，并加入未知 retention 字段。
oracle 比较完整 JSON 对象，新回归测试证明旧文件内容在第三次验收中会失败。

## 方法和结果

Pi 0.85.1，DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3。
每项交错运行朴素多工具、plan 禁用复用、plan 开启码表，共九次串行完整 Agent 运行。
两个 plan 组各从独立空表开始，组内持续学习，均使用最终 write/edit 内容入表、本地
tokenizer、session prefix cache；执行提示、复用核对、模板、能力缓存及条件回复关闭。
输出总限 17408，plan 每子工具参数限 2048，无测试器重试。

| 指标 | 朴素 | plan 禁用复用 | plan 开启码表 |
| --- | ---: | ---: | ---: |
| 正确完成 | 3/3 | 3/3 | 3/3 |
| 完整耗时 | 31.09 s | 20.22 s | 20.27 s |
| 生成 token | 2764 | 776 | 729 |
| 逻辑输入 token | 48693 | 31133 | 33001 |
| 模型请求 | 18 | 9 | 9 |
| 分类控制 | 0 | 9 | 9 |
| 实际复用 | 0 | 0 | 0 |

完整耗时包括启动、准备、推理、工具、回复；共享隧道和独立验收不计入。
无工具错误、无超时，usage 全部完整。九个保存产物独立复验全部通过，其他配置字段未
被覆盖。三组第一项实际工具都是 read；两个 plan 组随后均执行 edit 和 bash 验证。
朴素组通过 bash 修改文件，不能把没有原生 edit 事件误判为没有完成修改。

plan 禁用复用本轮比朴素少约 35.0% 总时间，请求减半；开启码表约 34.8%，但对禁用组
没有额外净收益。本实验是三个同家族开发任务，每题每组一次，不能承诺通用收益。

## 学习与候选处理

两个 plan 组首次和状态变化后的成功 edit 各新增一条完整内容，日志均为 new_edit_content；
正常重复的相同内容去重，不再新增。即使禁止复用，学习仍然工作。已验证 edit 学习在
真实 Agent 中生效，但没有获得实际复用收益。

开启组在第三项读过当前文件后，分类选中了旧内容候选，但同次续写放弃原样复用，
生成普通 edit，保留了当前文件的新字段。说明“分类选中”不是“已经执行缓存”，已有
退回生成路径在此例有效。一次成功拒绝不能证明此前 SQL 语义误命中已解决。

提示相同并不表示任务执行环境相同；仅凭任务文本相等不能直接重放完整文件。
本轮没有为提高命中率而绕过当前文件读取，也没有改变运行时默认开关。

506 项测试通过；归档校验 62623 条和 2853 个导入文件通过。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/edit-state-ablation-NEW --continuation \
  --tasks edit_state_base edit_state_repeat edit_state_changed \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --ablation --empty-book
```

[完整汇总和执行顺序](EDIT_STATE_EVALUATION.json) · [原始记录](../results/experiments/edit-state-ablation-20260920-a/)
