# plan 与子调用的 token 预算

此前客户端和服务端把整个 plan 限制为 2048 个生成 token。新协议将两层分开：

- 每个子工具的**参数对象**：2048 token。
- 最多八个子工具，整个 plan 的生成上限：8 × 2048 + 1024 = **17408 token**。
- 1024 是 plan/工具名/JSON 结构开销余量，不是额外的子工具额度。
- 这是最大预算，不强制生成到上限；旧普通工具请求默认仍保持 2048。

客户端仅在 `/v1/openjev/capabilities` 宣告支持时发送 `plan_budget=true` 与新总预算。
旧服务返回 404 时继续兼容运行，但界面明确警告“仍是整个 plan 2048”，日志记录
`plan_budget_mode=legacy_plan_2048`，不冒充优化已生效。其他网络或认证错误不吞掉。

服务端生成完整 JSON、校验 schema 后，以**当前服务 tokenizer 对每个参数对象的
紧凑 JSON 编码**独立计数。支持 first/rest、steps 及回复对象三种布局，超额会在
返回可执行调用前拒绝。缓存内容在计数后展开：复用引用只计算生成的路径参数，
不把未生成的缓存源码记入生成预算。

这个子调用计数不等同于生成流的逐 token 分摊：JSON 外壳、空白与 BPE 边界可能
不同。`generated_argument_tokens` 仍记录实际输出 token；`plan_budget.argument_tokens`
单独记录校验口径。错误响应保留已消耗的生成 token 和分类控制，客户端照常计账。

当前是**完整生成后拒绝超额参数**，不是在子调用第 2049 个 token 时自动暂停、
截断并续写。不能因此保证超额请求不浪费生成计算，也不会执行不完整子调用。
引擎内部多阶段生成/逐子调用停止属于进一步工作。

## 验证与上线状态

本地 419 项测试通过（FastAPI/httpx 路由测试在本次隔离环境中实际运行），覆盖
总量超过 2048、每项合规的两子调用与八子调用；单项超额拒绝；精确边界、Unicode、
缓存引用、旧协议兼容与失败 token 计账。路由测试使用替身 engine 和计数 tokenizer，
不是 GPU 实验。

真实 GPU 验收入口：`benchmarks/benchmark_plan_budget.py --url URL --out NEW_DIRECTORY`。
它要求新服务能力，强制输出两个各不超过 2048、总量超过 2048 的文本参数，检查
真实 tokenizer 计数和 same_engine_session。此测试验证预算，不用于任务质量或提速结论。

当前远端运行模块 SHA-256：
`62a2833c1eca3bfef5c9fc23330589064f77bb832d828306fa0c5a837ff6679f`。
已对比 classify/classify_v2/resumed/paused 四个内核函数，AST 未改动。
需要更新 API 模块并重新启动当前 vLLM 容器才能启用；本次准备阶段未重启服务。
