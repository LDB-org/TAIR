# Yuesheng 单请求分类与生成实验

> 后续已启用引擎原生计时，详见 [每请求计时与瓶颈定位](YUESHENG_ENGINE_METRICS.md)。本文保留 protocol2 原始实验记录。

2026-09-18，将先前三次上游请求改为一次连续解码。服务默认 mode 为 `hybrid_fused`，继续监听 `127.0.0.1:18185`。版本目录 `/opt/openjev-toolcall/releases/20260918-protocol2`，systemd unit 为 `openjev-toolcall.service`。仅重启了本项目协议服务，原 DeepSeek 容器保持运行。

## 实现

vLLM 接受 `structured_outputs.regex = "[ABCD]\\n[\\s\\S]+"`，在引擎解码循环内维护 grammar 状态并限制下一 token 的候选范围。类别选择、分隔换行与 content 在同一个上游请求、同一段自回归序列中生成，不再为每个字段重新提交 chat history。

- A：reply_user + normal
- B：reply_user + urgent
- C：search_docs + normal
- D：search_docs + urgent

首字符是有限分类结果，随后固定一个换行，其余全部作为 content 原样保留。宿主程序使用固定索引和固定映射构造对象，再用 JSON serializer 处理转义。内容内的引号、反斜杠、换行或 JSON 文本不改变对象层次。回答仍是 reply_user 调用；服务不执行业务工具。

这使用现有 LM head 与 vLLM 的 grammar 能力，没有新增独立分类头，没有对 DeepSeek 微调，也没有自定义 vLLM 插件或修改其 scheduler。四个类别是两个有限字段的联合分类，只适用于本次小型固定 schema；不声称笛卡尔积适合任意大型 schema。首个探针的 token IDs 为 `[36, 201, ...]`，对应 B 和换行。

输出必须正常结束、符合帧格式且 content 非空才返回可派发的 call。任何截断或无效帧均不返回 call/wire。Schema 合法仍不代表工具选择、语义或执行权限正确。

保留 `mode=json` 和 `mode=hybrid_fields` 供对照。`/health` 的 `decision_token_ids=[35,36]` 是旧 hybrid_fields 的 A/B 候选字段；fused 使用上面的四类别 grammar。

## 方法

使用与上一轮相同的 12 条固定文本和 1 张左红右蓝图片；两轮交错执行 json 与 hybrid_fused，共 52 次完整调用。第二轮反转每条用例的模式顺序。每条完整调用使用独立 cache salt。未排除任何慢请求或失败请求。先前的单条探针已触发过相同 regex 的请求，因此不将本次测量称为纯冷启动测试。

json 是请求完整 JSON 的普通提示基线，不是 JSON grammar 约束基线。共享机器仍运行其他工作负载，不是隔离性能或吞吐测试。每个 trace 保留 request ID、输出 token IDs、usage、结束原因和原始响应文本。

复现：

```sh
python3 benchmarks/test_remote_toolcall.py \
  --cases benchmarks/data/schema-toolcall-heldout12.jsonl \
  --modes json hybrid_fused --repeats 2 \
  --out /tmp/openjev-fused-new-run
```

恢复前一版：将 `/opt/openjev-toolcall/current` 原子切换到 `releases/20260918-protocol1`，再 `systemctl restart openjev-toolcall.service`；无须重启原模型服务。

本地 42 项 pytest、原 raw SHA256 校验、69 项 published claim 校验通过。实验只追加独立证据，不更改 Phase 1 结论。

## 两轮结果

13 个不同用例各测两次；以下 n=26 不是 26 个不同用例。

| 指标 | 普通完整 JSON | hybrid_fused |
|---|---:|---:|
| 精确匹配 | 26/26 | 26/26 |
| Schema 合法且完整 | 26/26 | 26/26 |
| completion tokens 总计 | 696 | 208 |
| 平均耗时 | 8.08 s | 13.09 s |
| 中位耗时 | 6.84 s | 11.91 s |

输出 token 减少 70.1%，本轮平均耗时却为基线的 1.62 倍。两条原有分类失败用例均通过，图片两轮也通过；不将小样本重复测试解释为泛化正确率保证。

单请求融合已工作，但尚未证明端到端加速。和旧版三请求的 32.65 s 相比数值降低，不过测试时段和负载不同，不能用跨轮数据宣称确定的加速比。

现场源码检查发现，vLLM `v1/core/sched/async_scheduler.py` 将有未返回 token 的 structured output 标为 pending；`v1/engine/core.py:678` 附近在该情况下延迟 sampling，待上一轮输出处理后更新 grammar bitmask。这证明存在同步依赖路径，但未测得它在本次请求中的具体占比，不能据此将全部延迟归咎于 grammar。

当前 regex 在内容生成期间仍然保持 structured-output 请求状态。尚未实现“类别选完后退出 grammar 调度路径”的专用 logits processor。若进一步优化，这与减少 HTTP 请求是两个不同的工程步骤。

## SSE 耗时定位（独立诊断，不混入上表）

两条文本用例分别测普通 JSON、fused grammar，以及去掉 grammar 的同格式生成对照。诊断对照只在脚本中使用，不作为公开服务 mode。记录的是客户端首次收到非空 content 和后续 SSE 的耗时，不是 GPU kernel 或纯 decode 计时；首段包括排队、prefill、约束准备和首个输出，不能进一步拆因。

| 用例/模式 | 首个 content 前 | 首个 content 后 |
|---|---:|---:|
| h01 JSON | 3.149 s | 0.283 s |
| h01 fused grammar | 9.653 s | 0.093 s |
| h01 无 grammar 紧凑协议 | 3.831 s | 0.094 s |
| h11 JSON | 1.121 s | 0.352 s |
| h11 fused grammar | 25.645 s | 0.127 s |
| h11 无 grammar 紧凑协议 | 13.848 s | 0.128 s |

这两条诊断中，紧凑协议的后续输出耗时较短，带/不带 grammar 的后续输出时间接近；端到端延迟主要集中在首个 content 之前。它们不支持“grammar 的逐 token 处理已被证明是主要瓶颈”的断言，也不能排除首次约束准备和调度的影响。下一项有信息量的性能验证应在可控负载下测 TTFT 与输出阶段，而非仅继续压缩输出 token。

额外现场检查 3/3 通过：非法 mode 返回 400；单 token 截断返回 422 且无可派发 call/wire；即使提示要求非法分类 Z，引擎仍输出符合四类别帧的完整结果。证据、源文件快照与哈希在 `results/experiments/yuesheng-20260918-fused/`。
