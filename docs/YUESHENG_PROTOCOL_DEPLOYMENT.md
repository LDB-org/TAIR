# Yuesheng DeepSeek 协议服务实验

> 本文保留 protocol1 三请求版本的历史记录。后续已升级为 [单请求版本](YUESHENG_FUSED_PROTOCOL.md)，并[启用引擎原生计时](YUESHENG_ENGINE_METRICS.md)。

2026-09-18 部署。实验服务复用既有 DeepSeek-V4-Flash-Vision-Exp，未修改模型、训练权重、原服务路由或 vLLM scheduler。

## 部署

- 主机：SSH alias `rs-yuesheng-gpu-vps`，现场 hostname `yuesheng-gpu`。
- systemd：`openjev-toolcall.service`，已启用开机启动。
- 程序：`/opt/openjev-toolcall/current/toolcall_service.py`。
- 当前 release：`/opt/openjev-toolcall/releases/20260918-protocol1`。
- 服务：`http://127.0.0.1:18185`，只监听本机；上游 `http://127.0.0.1:8000`，model `/model`。
- 单个协议请求运行中，额外请求返回 429；不执行真实工具。
- 模型：6×RTX5090，TP2×PP3，共享正在运行的推理服务，无新权重进程。
- vLLM：`0.28.1rc1.dev137+g5ab628dd1`；镜像 digest、配置和 tokenizer 哈希见实验 environment.json。未独立确认权重来源 revision，不能把目录名当作上游 revision。

访问示例（在服务器本机）：

```sh
curl -sS http://127.0.0.1:18185/v1/toolcall \
  -H 'Content-Type: application/json' \
  -d '{"request":"Urgent: reply with exactly: 已停止任务。","mode":"hybrid_fields"}'
```

从本地访问可用 `ssh -L 18185:127.0.0.1:18185 rs-yuesheng-gpu-vps` 建立隧道。

停止本次新增服务：`sudo systemctl disable --now openjev-toolcall.service`。原有 vLLM 服务不受该命令影响。

## 协议与边界

固定 schema：`name ∈ {reply_user, search_docs}`、`arguments.priority ∈ {normal, urgent}`、`arguments.content` 为非空字符串。

`hybrid_fields` 分三次上游请求：限定 A/B token 选择工具，限定 A/B token 选择优先级，再生成原始 content。A/B 的 tokenizer IDs 经现场验证为 35/36。分类使用现有 LM head 的候选 token 约束，没有增加独立分类头，也没有对 DeepSeek 做协议微调。对象键名、层次及 JSON escaping 由服务代码构造。自然语言回答也包装为 `reply_user`。这仍是协议适配服务，并非融合成一次引擎内部推理请求。

输出截断、空值、无效分类或上游异常不会产生可派发的 call。成功返回 `call` 和序列化的 `wire`；调试字段 `candidate` 不可当作可执行调用。结构有效不保证工具选择、参数含义或执行权限正确，本实验也不执行任何业务工具。

`json` 对照模式直接请求完整 JSON，随后解析、校验。它是普通 JSON 提示对照，**不是 XGrammar/SGLang 约束解码对照**。

每次完整调用使用独立 cache salt，hybrid 的三个阶段共享该 salt；跨阶段仍会重新请求并渲染 chat history，不代表 native KV 连续解码。三次排队和 prefill 可抵消减少 decode token 的收益。

## 验证方法

`benchmarks/test_remote_toolcall.py` 顺序交错调用两种模式，使用已有的 12 条固定文本用例，加一张程序生成的左红右蓝 PNG，要求识图回答 RED。记录每次请求、原始模型响应、token 数、完成原因、精确匹配及延迟。无重试、无剔除失败样本。图片记录在 cases.json 中。

这是共享负载下每用例一次的小样本验收，不是隔离吞吐或 p95 性能结论。限流为一个协议调用，未进行并发压力测试。不能用此结果声称已经完成 DeepSeek 协议训练或全 schema 支持。

本地验证：34 项 pytest 通过；既有 raw SHA256 校验通过；69 项 published claims 校验通过。

复现实验（输出目录必须全新）：

```sh
python3 benchmarks/test_remote_toolcall.py \
  --url http://127.0.0.1:18185 \
  --cases benchmarks/data/schema-toolcall-heldout12.jsonl \
  --out /tmp/openjev-new-run
```

逐行证据位于 `results/experiments/yuesheng-20260918/`；远端原始目录是 `/opt/openjev-toolcall/results/20260918-run1`。这批实验单独归档，不修改 Phase 1 的发布结论和 raw evidence。

## 本次结果

| 指标 | 完整 JSON 提示 | hybrid_fields |
|---|---:|---:|
| 用例数 | 13 | 13 |
| 完整精确匹配 | 13/13 | 11/13 |
| Schema 合法且完整 | 13/13 | 13/13 |
| completion tokens 总计 | 345 | 104 |
| 平均端到端延迟 | 6.70 s | 32.65 s |
| 中位端到端延迟 | 4.41 s | 19.28 s |

hybrid 输出 token 减少 69.9%，但本次平均延迟为对照的 4.87 倍。共享负载下三个阶段分别提交，包含多次排队、prefill 与协议开销；这些数据不能单独分离各项开销，也不证明融合进引擎后仍然慢。

两条失败：h09 要求原样回复 `{"name":"search_docs"}`，内容正确但工具误判为 search_docs；h11 内容正确但 urgent 被判为 normal。其他工具/priority 选择正确，13 条 content 均精确一致。真实 PNG 图片用例两种模式都正确返回 RED。

结论：零样本 DeepSeek 实验验证了候选选择、自由内容生成、程序序列化及图片输入链路可工作；没有验证等质量加速。不能将 Schema 合法解释成语义安全、权限安全或工具选择正确。减少 decode token 的潜力已经可见，当前协议服务的实际延迟反而更高。引擎内部单请求阶段切换、协议训练与隔离负载性能实验仍未完成。

额外现场检查 3/3 通过（`20260918-run1/safety.json`）：非法 mode 返回 400；强制 content 仅生成 1 token 时返回 422，`call`/`wire` 均为 null；即使提示明确要求输出 C，上游限定 A/B 后仍只能输出候选字母。最后复验服务 active/enabled、远端源码哈希与本地一致；原模型容器启动时间仍为 2026-09-06，未重启。

所有 26 条性能/正确性记录已回收，wire 反序列化与 call 一致，实验文件 SHA256 校验通过。安全检查单独记录，不计入上述性能表。
