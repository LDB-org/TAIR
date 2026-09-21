# 服务能力协商缓存

2026-09-20。已实现 PIJIT_CAPABILITIES_CACHE=1，并完成六题三组、共 18 次真实 GPU 运行。确实消除了重复能力查询，但这轮完整任务总时间没有净改善，因此暂不默认启用。

## 实现与边界

Pi 进程在内存中保存服务能力信息，如每子工具预算、plan 总预算和 prefix cache 支持情况。有效期从实际查询开始算 30 秒，命中不续期。没有保存模型输出或工具结果，也不触碰用户码表。

客户端按服务地址、模型和凭据绑定缓存，另校验会话；键只在内存中使用。session_start 清空缓存；chat 请求报错后清空，下次重新查询。Python bridge 再次校验地址、模型、会话与时间；过期、未来时间、格式不合法或未开启缓存时查询实际服务。旧服务的 404 仍表示不支持扩展预算，401 等错误继续抛出。缓存不会免除推理端点自身的预算、schema 或身份检查。

服务若在缓存有效期内改变能力，可能先在该次请求中返回原生错误；缓存随错误失效。没有添加静默生成重试，也不宣称能无感处理任意服务热切换。默认关闭，后续需扩大验证。

测试覆盖不续期、过期、地址/模型/会话不匹配、凭据绑定键改变、时钟倒退、畸形快照、401、复制隔离。真实 Pi 加受控 bridge 的集成测试确认第二次 chat 带入快照，模拟 HTTP 500 后的重试不再带旧快照。另直接比较缓存与未缓存时传给模型的消息、分类提示、各分支 schema、生成指令和预算，保持一致。

## 真实实验

yuesheng 6×RTX 5090，既有 DeepSeek-V4-Flash-Vision-Exp，TP2/PP3；Pi 0.85.1。六题为 jsonl_base、jsonl_changed、unique_base、totals_base、repair_failure、normalize_labels。三组随机交错，每题每组一次。

两条 plan 都采用原恢复路由，关闭条件回复和码表复用；使用独立空测试表保留学习、本地 tokenizer、会话 prefix cache 和相同预算。只有新组启用服务能力缓存。所有七种工具可用。运行中逐条核对缓存、恢复、复用开关。计时包含启动、推理、工具、错误恢复和最终回复；独立 oracle 在计时之外。没有重启服务或修改用户默认配置。

| 指标 | 朴素多工具 | plan 未缓存能力 | plan 缓存能力 |
| --- | ---: | ---: | ---: |
| 完整通过 | 6/6 | 6/6 | 6/6 |
| 完整耗时 | 52.93 秒 | 50.17 秒 | 50.65 秒 |
| 模型请求 | 21 | 14 | 15 |
| 生成 token | 5160 | 3512 | 3786 |
| 分类控制记录 | 0 | 14 | 15 |
| 工具错误，含要求的初始失败检查 | 1 | 1 | 2 |
| 能力 GET | 不适用 | 14 | 6 |
| 能力缓存命中 | 不适用 | 0 | 9 |
| 能力协商阶段累计耗时 | 不适用 | 3.269 秒 | 1.313 秒 |

全部 usage 完整、没有超时；归档产物已独立复验。完整通过还检查正常结束、末次工具未遗留失败、修复题首次运行要求的检查以及检查文件未被修改。

缓存组 15 次 chat 只有六次真正查询服务，九次命中合计耗时约 65 微秒。相比未缓存组，观察到的能力协商阶段累计耗时少约 1.96 秒。两组模型轨迹并不完全相同，因此这个差额也含请求数及网络耗时波动；可以确定的是九次请求实际绕过了 GET，而不是推测命中。

完整时间反而多约 0.49 秒。缓存组 totals_base 多了一次工具错误恢复，整组生成 token 也多 274，抵消了辅助查询节省。不能只展示查询阶段、忽略这些任务成本，也不能把不同生成长度带来的时间差归给缓存。

本轮证实了缓存执行链和具体通信开销的减少，没有证明稳定的端到端加速率。它也没有解决动态码表的内容适用性问题。下一步需要更大规模、重复交错的完整任务对照，再决定是否默认启用。

## 使用与复现

实验开关：PIJIT_CAPABILITIES_CACHE=1。旧行为保持默认。

```sh
PATH=/tmp/tair-pi-0.85.1/node_modules/.bin:$PATH /tmp/tair-test-venv-20260918/bin/python benchmarks/benchmark_expanded_reuse.py \
  --out results/experiments/capabilities-cache-NEW --continuation \
  --tasks jsonl_base jsonl_changed unique_base totals_base repair_failure normalize_labels \
  --local-tokenizer /Users/zacharyzcr/.cache/tair/tokenizer-dsv4-20260920 \
  --prefix-cache --capabilities-ablation --empty-book
```

484 项测试通过，含固定 Pi 的集成测试。原始证据保存在 results/experiments/capabilities-cache-ablation-20260920-a/，包含冻结源码和校验和。

[完整汇总](CAPABILITIES_CACHE_EVALUATION.json) · [能力查询阶段统计](CAPABILITIES_CACHE_STAGES.json)
