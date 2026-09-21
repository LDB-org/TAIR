# 恢复路由的独立扩大消融

> 后续验收更正：新增正数分组验收后，native 的 nullable_changed SQL 未通过，
> native 正确完成数应为 20/21；原 plan 和新恢复路径仍为 21/21。
> 下文 21/21 是原始验收口径，不能继续用于双方全部正确的性能结论。原始数据不改动，
> 详见 [补充审计](NULLABLE_ORACLE_AUDIT.json)。

2026-09-20。三组各 21 题，共 63 次完整 Agent 运行，独立复验归档产物。结论：本轮普通 plan 有同质量的净收益，但仅改变恢复路由没有进一步加速，暂不默认启用。

## 方法

yuesheng 既有 6×RTX 5090、DeepSeek-V4-Flash-Vision-Exp、TP2/PP3；Pi 0.85.1。任务覆盖新文件、JavaScript/Python、重复任务、变更约束、既有配置编辑、错误修复和新增鲁棒性要求。它们是已有开发回归集，不是外部 held-out benchmark。

三组为原生多工具、原恢复策略的通用 plan、最新结果恢复策略的同一 plan。两条 plan 都关闭条件回复、内容复用与模板复用，但在独立空测试表中保留学习。没有清空用户码表。原路由在本用户轮次曾有工具错误时持续强制恢复；新路由仅在最新工具结果失败时强制恢复，保留完整历史及未解决错误提醒。

每题每组一次，随机交错顺序；相关任务顺序不变。所有七种原生工具可用。两条 plan 使用相同本地 tokenizer、会话 prefix cache、每子工具 2048 / 总计 17408 预算。计时包含启动、推理、全部工具、失败恢复和最终回复；独立 oracle 在计时之外。没有重试整个任务，没有修改冻结后的运行源码。逐次 trace 核对复用、条件回复及恢复范围，防止开关被启动链覆盖。

## 完整结果

| 指标 | 朴素多工具 | 原恢复路由 plan | 最新结果恢复 plan |
| --- | ---: | ---: | ---: |
| 完整通过 | 21/21 | 21/21 | 21/21 |
| 总耗时 | 217.20 秒 | 186.02 秒 | 199.20 秒 |
| 模型请求 | 86 | 51 | 54 |
| 生成 token | 21154 | 13168 | 14016 |
| 分类控制记录 | 0 | 51 | 54 |
| 逻辑输入 token | 238010 | 180738 | 194692 |
| 工具错误，含要求的初始失败检查 | 2 | 4 | 8 |

全部 usage 完整，无超时。完整通过包括产物正确、正常结束、没有遗留的末次工具失败，以及修复题要求的先检查流程；三组的 check_calc.py 均保持未修改，首次操作确实是运行该检查。

原 plan 相对朴素总耗时少 14.36%，生成 token 少约 37.75%，请求少约 40.7%。逐题 15/21 更快，配对耗时降幅中位数约 9.53%。这些是整个 plan 协议和实际执行轨迹的净效果，不能拆成分类内核的独立贡献。

最新结果路由相对原 plan 总耗时多 7.09%，仅 10/21 项更快，配对耗时中位数慢约 1.96%。两组发生不同的生成和检查轨迹，不能把所有额外错误都归因于恢复路由；但此次结果确实不支持把新路由宣传为净加速。

长尾敏感性：朴素 nullable_changed 为 25.01 秒。仅作事后分析、同时排除该题的对应两组后，原 plan 为 177.61 秒对朴素 192.19 秒，仍少约 7.59%；新路由为 192.22 秒，基本持平。主表保留全部 21 题，不能拿剔除结果替代正式分母。

## 修复场景

修复题原路由 9.25 秒 / 4 次请求，新路由 9.61 秒 / 4 次请求，都正确结束。上轮条件回复实验中出现过原路由 150 秒 / 80 次请求的循环，本轮关闭条件回复后未复现。恢复状态修正有明确的控制流意义，但不能把那个极端样本推广成普遍加速效果。

因此 PIJIT_RECOVERY_LATEST 继续保持实验开关；PIJIT_PLAN_SUCCESS_REPLY 也不启用。本轮关闭码表是独立消融，不是把动态码表从最终产品目标中删除，更不代表其错误复用问题已解决。

## 客户端开销的后续定位

上一轮 G 中，普通 plan 的 Python run 耗时 49.98 秒，扣除推理 HTTP 42.54 秒和生成准备 2.43 秒，仍有约 5.01 秒尚未细分。这包括服务能力查询、检索、解码验证等，不能全算成网络或进程启动成本。

本轮增加 capability_negotiation 与 plan_decoding 分阶段计时，并在 GPU 对照结束后进行了独立微测量。该探针仅查询服务能力、重放本地解码，不发送推理请求或执行工具：

- 5 次 capability GET，中位数 **222.6 ms**，全部确认当前预算协议可用。
- 用真实 Pi 七工具 schema 和归档 plan 解码，首次 **68.2 ms**；后续 5 次中位数 **11.8 ms**。首次包含按需导入，不能只用 warm 数字代表每次新 Python 进程。

能力查询目前每次 chat 都重复，因此是一个有实测依据的下步优化点。微测量尚未实现缓存、也不是端到端加速证据；不能直接宣称已省下 5 秒。需要继续测试会话内复用协商结果及其失效边界。

[主汇总](RECOVERY_SCOPE_ABLATION.json) · [逐题比较及敏感性分析](RECOVERY_SCOPE_PAIRED.json) · [旧轮次客户端时间拆分](PLAN_CLIENT_OVERHEAD_PROFILE.json) · [微测量原始记录](../results/experiments/plan-client-profile-20260920-a/report.json)

GPU 原始证据：results/experiments/recovery-scope-ablation-20260920-a/；微测量：results/experiments/plan-client-profile-20260920-a/。均保存源码、输入与校验和。

复现：

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/recovery-scope-NEW --continuation --fresh \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --recovery-ablation --empty-book
```

微测量使用 benchmarks/profile_plan_client.py，传入独立 --out、固定 Pi 包路径 --pi-root；默认 5 个样本，模型推理请求数为 0。本轮没有重启服务或改动用户默认设置。

最终检查：472 项测试通过；归档校验通过，60697 条原始校验记录保持一致。服务只读复核 health=200、running=waiting=0。
