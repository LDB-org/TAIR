# Yuesheng 引擎每请求计时

2026-09-18，在用户授权后为既有模型启用计时。保留同一镜像 digest、模型挂载、TP2×PP3、KV FP8、4 条并发序列、1024 token 调度预算、priority 调度和端口。启动参数移除 `--disable-log-stats`，增加 `--enable-per-request-metrics`。前端协议保持单请求分类与生成。

## 维护与恢复

- 原容器保留为 `vllm-deepseek-v4-sm120-situ-before-metrics-20260918`，不删除。
- 配置备份在远端 `/opt/openjev-toolcall/maintenance/metrics-20260918/original-inspect.json`，目录为 0700、文件为 0600。原始 inspect 可能含环境凭据，不复制进仓库。
- 新容器沿用正式名称 `vllm-deepseek-v4-sm120-situ`；切换时暂停健康看门狗，真实推理验收后恢复。
- 初次重启遇到 DeepGEMM 的 `Corrupted JIT cache directory`。现场确认 `/tmp/vllm-prof-cache-pr41834/vllm/deep_gemm/cache` 内 162 个目录全部为空；将整个 cache 重命名为 `cache.quarantine-20260918-metrics`，保留原件，重建 cache 后重新加载。没有删除权重。
- 因内核缓存重新生成，本次与先前实验不是仅改变 metrics 开关的严格性能 A/B。当前 JSON 与 fused 的同轮比较仍使用同一运行实例。

协议服务版本为 `/opt/openjev-toolcall/releases/20260918-protocol3`，新增记录上游 `metrics`，不改变协议生成规则。默认 `hybrid_fused`。

## 计时解释

现场 vLLM `build_per_request_timing_metrics` 的定义：

- `queue_time_ms = scheduled_ts - queued_ts`：从进入引擎队列到调度的时间。
- `time_to_first_token_ms = first_token_ts - scheduled_ts`：**不含上述队列时间**，从调度到首 token。
- `generation_time_ms = last_token_ts - first_token_ts`：首 token 到末 token。
- `mean_itl_ms`：后续 token 的平均间隔。

客户端总耗时减去前三项之和记为 `unaccounted_ms`，其中可能包含入队前处理、协议序列化及 HTTP 开销；不把它直接称为 grammar 编译时间。引擎排队时间也不能在没有进一步事件跟踪时全部归因于并发容量。

原 SSE 测量记录的是客户端首次收到 content 的时刻，不等同于引擎 `time_to_first_token_ms`；此次以引擎原生时间戳进一步定位。

## 验证方法

13 条固定用例（含真实 PNG）各两轮，JSON 与 fused 顺序交错。每次请求前采集 running/waiting/KV usage gauge，逐条保存客户端时间及引擎 metrics，保留所有失败与慢请求。额外检查原生 metrics 是否完整，所有 fused 调用是否仍只提交一次请求。

```sh
python3 benchmarks/test_remote_toolcall.py \
  --cases benchmarks/data/schema-toolcall-heldout12.jsonl \
  --modes json hybrid_fused --repeats 2 \
  --engine-metrics-url http://127.0.0.1:8000/metrics \
  --out /tmp/openjev-metrics-new-run
python3 benchmarks/summarize_engine_metrics.py \
  --rows /tmp/openjev-metrics-new-run/rows.jsonl \
  --out /tmp/openjev-metrics-new-run/engine-summary.json
```

本地 43 项 pytest、原 raw SHA256 校验和 69 项发布声明校验通过。新实验独立归档，不修改 Phase 1 结论。

## 结果

模型真实推理验收于 2026-09-17 20:15:20 UTC 通过，看门狗已恢复。协议服务、模型容器均正常；原容器处于停止状态作为回滚副本。

52 次调用均返回完整原生计时。13 个不同用例各测两轮，双方精确匹配、Schema 合法均为 26/26。JSON 输出 702 token，fused 输出 208 token。

以下全部为每请求**均值**，单位秒：

| 分项 | JSON | fused |
|---|---:|---:|
| 客户端总耗时 | 7.839 | 7.895 |
| 引擎排队 | 5.507 | 6.762 |
| 调度到首 token | 0.583 | 0.155 |
| 首 token 到末 token | 1.006 | 0.450 |
| 未被上述三项覆盖 | 0.744 | 0.527 |

fused 排队约占总耗时的 **85.7%**，是本批数据的主要延迟来源。请求前 gauge 快照中，JSON 26/26 次、fused 24/26 次显示 4 条运行序列，达到配置上限；快照中的 KV 使用率约 2.3%～23.9%，未显示 KV 池已满。快照不是本请求整个生命周期的连续记录，也不能据此保证提高并发不会增加激活显存压力。

用中位数看典型情况：

| 分项 | JSON | fused |
|---|---:|---:|
| 调度到首 token | 155.6 ms | 157.4 ms |
| 首 token 到末 token | 292.0 ms | 85.2 ms |
| 调度到末 token | 458.2 ms | 235.4 ms |
| 每 token 间隔 | 10.51 ms | 10.87 ms |
| 未覆盖耗时 | 162.2 ms | 162.1 ms |

中位数不可直接相加。上述数据支持：生成更少 token 缩短了典型输出阶段；两种模式的典型首 token 前执行时间及单 token 间隔接近，没有证据表明每一步 grammar 处理构成秒级稳定开销。端到端收益被共享服务的队列等待覆盖。

不能忽略尾延迟：JSON 的 h11 第一轮生成区间达到 18.465 s，fused 的图片第一轮生成区间达到 9.649 s。`generation_time_ms` 是墙钟区间，也可能包含运行期间的停顿，不等于纯 GPU kernel 时间。两条均完整保留，未作为异常值剔除。首条 JSON 另有 11.142 s 的调度至首 token 区间和约 7.101 s 的未覆盖耗时；本轮包含重建缓存后的早期请求，不能用它代表稳态 prefill。

因此当前明确的优化方向是共享调度与请求等待；若继续优化，需要在可控负载下评估运行槽位、prefill 与 decode 的调度，以及入队前/输出端剩余开销。不能仅根据低 KV 使用率直接提高并发，也不能用本次平均值将所有尾延迟归因于同一个原因。

额外验收：截断拒绝、非法 mode、grammar 强制分类 3/3 通过；真实 SSE 回复 `STREAM_OK`、正常结束及 metrics 均通过。

逐行记录、原生汇总、现场配置和源码快照：`results/experiments/yuesheng-20260918-engine-metrics/`。所有实验文件独立建立 SHA256 清单。
