# 指定候选后的复用核对组件测试与验收更正

2026-09-20。DeepSeek-V4-Flash-Vision-Exp，yuesheng 6×RTX 5090，TP2/PP3。
使用现有融合分类/生成接口，但分类只有一个候选，专门检验选中候选后的生成决策。
没有运行 Pi Agent，没有自然候选竞争，没有自动学习；只允许单个 write，之后独立运行
SQL 验收。候选内仍允许直接生成普通 write 或返回文本，未强迫实际复用。

两类既有开发任务，各有适用和变更约束两个条件，对比原协议与核对协议，共 8 次请求。
候选源自归档且通过原验收的 SQL，任务/候选/源码在推理前冻结，顺序交替，无重试。
每次只有一次融合模型请求、一个分类控制记录；全部 usage 完整。

| 条件 | 原协议 | 核对协议 |
| --- | --- | --- |
| 汇总原要求 | 正确复用；22 token，0.87 s | 正确复用；72 token，1.38 s |
| 汇总只保留正数 | 错误复用；23 token，0.70 s | 拒绝旧内容，生成正确替代；121 token，1.50 s |
| NULL 分组原要求 | 正确复用；21 token，0.65 s | 正确复用；82 token，1.17 s |
| 排除全 NULL 分组 | 错误复用；22 token，0.80 s | 拒绝旧内容，但替代 SQL 错误排除了正数；122 token，1.56 s |

时间是组件请求准备和推理时间，不是完整 Agent 耗时。生成 token 不含分类控制。
正常复用多了 50/61 个生成 token、约 0.51/0.52 秒。核对组识别了两项不兼容，但其中
一次重新生成仍错误；加强验收后原协议 2/4、核对协议 3/4。不能把拒绝旧缓存等同于
完成正确任务。样本小且针对已知失败，选项继续默认关闭。

## 本轮发现并修复的验收缺口

原 nullable oracle 只有零、负数和全 NULL 分组，没有正数分组。模型生成的
`HAVING SUM(value) <= 0` 因而可能错误通过。已增加一个同时含正数与 NULL 的分组，
并新增四项测试，验证 base/changed 两种规则下正确查询通过、错误排除正数的查询失败。
用户原要求未改变，这属于补全验收覆盖，不是事后改变任务。

原始 component report 记录核对组 4/4，这是旧 oracle 的结果，保留原字节。
派生汇总新增 expanded_oracle_passed 和审计详情，修正为 3/4。
另对 56 个历史完整 Agent 的 nullable 保存产物追加同样验收，发现两个新增失败：

- execution-guidance-expanded-20260920-a：native 从 6/6 更正为 5/6；原 plan 5/6、提示组 6/6 不变。
- recovery-scope-ablation-20260920-a：native 从 21/21 更正为 20/21；两条 plan 仍为 21/21。

上述两个报告已添加更正，不能继续使用原先“双方全部正确”的比较前提。耗时不修改，
原始实验文件全部保留。这也不意味着其他未覆盖边界已得到证明。

502 项测试通过。归档校验通过（2853 个导入文件，62268 个原始校验条目）。

```sh
python benchmarks/probe_reuse_review.py --out results/experiments/reuse-review-component-NEW \
  --tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920
```

当前复现会使用加强后的 oracle，不能期望复现旧 oracle 的通过数。

[组件汇总及追加验收](REUSE_REVIEW_COMPONENT.json) · [56 个历史产物审计](NULLABLE_ORACLE_AUDIT.json) · [原始记录](../results/experiments/reuse-review-component-20260920-a/)
