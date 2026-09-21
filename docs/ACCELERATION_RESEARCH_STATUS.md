# TAIR 加速研究总览与下一步实验

更新：2026-09-21。本文汇总本仓库实验与本轮 GitHub 调研。外部项目只做了文档和公开实现说明审阅，未安装或在我们的模型上实测；链接指向可变分支，不是固定版本复现。下面的接入建议是我们的工程判断。

## 当前结论

TAIR 已验证部分任务中减少生成和模型调用的可行性，尚未证明通用、稳定的端到端加速。Plan、分类选择、内容复用、引擎推测解码解决不同开销，不能合并计算收益。

当前 Plan 对外提供一个工具，内部组织 Pi 工具操作；动态码表保存生成内容和任务信息，经检索、模型选择后绑定参数。工具执行成功、JSON 合法或候选被选中，都不等于内容满足新需求。当前静态 Plan 尚不能通用地将前一步工具结果作为后一步参数并在执行器中处理分支。

本次整理不部署引擎补丁、不启用实验开关、不修改用户码表。源码中的保留改动不代表远程服务已经更新。

## 本地实验已经说明什么

| 证据 | 结果与边界 |
| --- | --- |
| [完整 Agent 四组比较](FIRST_TOOL_REUSE_EVALUATION.md) | 每组 8 个任务、共 32 次运行。Native 8/8、70.645 秒、7081 生成 tokens；general Plan + reuse 8/8、65.842 秒、4672 tokens。观察到 6.8% 时间和 34.0% 生成量下降，仅覆盖两个编写的任务族。 |
| 同一实验的 4 个重复任务 | Native 32.897 秒、3273 tokens；general Plan + reuse 23.299 秒、1336 tokens。实际复用的首次内容全部正确，但时间差包含不同验证和修复轨迹。 |
| 同一实验的新约束 | 5 次实际内容复用中 4 次首次正确、1 次错误；最终 8/8 包含修复。Ordinary Plan + reuse 只有 6/8，存在两次超时，不能省略这一组。 |
| [精确任务契约审计](EXACT_CONTRACT_REUSE_AUDIT.md) | 严格全文相等会同时拒绝 4 次正确复用和 1 次错误复用；使用已知测试路径做归一化不能当作通用需求解析器。未引入这一运行时门禁。 |
| [复用内容修改组件](REUSE_ADAPTATION_COMPONENT.md) | 增加精确编辑分支后没有实际采用该分支，未证明补丁复用收益；运行时实验已撤回。 |
| [紧凑差异提示](COMPACT_REUSE_DELTA_EVALUATION.md) | 两组均 2/5 正确；减少输入没有解决新约束下的错误复用，未推广为默认提示。 |
| [单候选直通](SINGLE_BRANCH_DIRECT.md) | 固定输出探针更快，但开放内容出现质量退化；改变续写边界也影响结果。直通运行时改动已撤回，不能归因为分类具有额外语义能力。 |
| [生成长尾审计](LENGTH_FAILURE_BRANCH_AUDIT.md) | 历史请求达到 17408 tokens；现有证据不足以确定输出长尾根因。增加诊断和避免明确长度失败后的重复请求，不等于根因已修复。 |

四组比较环境为 Pi 0.85.1、DeepSeek-V4-Flash-Vision-Exp、TP2/PP3、六张 RTX 5090、并发 1，使用独立实验码表。Native 是同一服务上的原生 Pi 工具路径，不是独立未修改 vLLM 的内核对照。精确制品、请求和统计口径以链接报告及冻结目录为准。

保留的局部工程改动包括 [payload guard 每请求准备一次](PAYLOAD_GUARD_PREPARATION.md)、[SQLite 源码按需批量读取](BOOK_SOURCE_LOADING.md)、[长度失败的重试处理](GENERATION_LENGTH_RETRY.md) 和 [生成诊断](GENERATION_DIAGNOSTICS.md)。CPU 微基准收益不能直接转为 Agent 秒级加速。[流式参数预算](STREAM_PLAN_BUDGET.md) 仍为默认关闭的实验，未部署。

## GitHub 上值得借鉴的机制

### 1. 可执行 Plan：减少模型往返

[Cloudflare Code Mode](https://github.com/cloudflare/agents/tree/main/packages/codemode) 将工具包装为一个代码执行工具，从 Schema 生成类型描述，模型用代码表达工具调用、结果引用和条件逻辑。[smolagents](https://github.com/huggingface/smolagents) 的 CodeAgent 也用代码组合多个工具。Cloudflare 明确将该包标记为实验性。

对 TAIR 的建议：保持公开工具只有 `plan`，先增加有类型的结果引用，再评估受限条件与循环。工具结果在执行器内传递；能够用确定程序处理的中间步骤不必重新请求模型。未知结果需要语义理解时仍回到模型。计划生成错误不会因为代码可执行而消失，执行器需保留工具权限、错误传播和资源限制。

这是待实现方案，不是现有 Plan 已有的能力；不要求直接替换 Pi 或迁移到 Cloudflare。

### 2. DAG 调度：减少逐步规划与串行等待

[LLMCompiler](https://github.com/SqueezeAILab/LLMCompiler)（MIT）分解工具任务、表达依赖，并调度独立调用；支持流式计划调度。可借鉴依赖解析和结果引用，不必引入整个框架。

应分别测量少了多少模型请求、多少工具等待；并行执行本身不代表生成 tokens 减少。有状态的写操作保持依赖顺序，失败后不能假设已经执行的操作会自动回滚。

### 3. 检索式推测解码：减少串行解码工作

[vLLM Suffix Decoding](https://github.com/vllm-project/vllm/blob/main/docs/features/speculative_decoding/suffix.md) 可从提示词及历史生成中匹配草稿，并动态选择推测长度；相关依赖是 [ArcticInference](https://github.com/snowflakedb/ArcticInference)。[SAM-Decoding](https://github.com/hyx1999/SAM-Decoding) 使用后缀自动机从已有文本提出草稿，也是值得比较的研究实现。

建议实验：码表提供草稿 Token，目标模型批量验证，接受一致部分并在分歧处继续生成。与“分类选中后直接展开整段缓存”相比，这将接受决定放到目标模型的解码验证中。标准 Suffix 的历史缓存不自动等于 TAIR 的持久化 SQLite 码表；注入候选、缓存生命周期和 tokenizer 对齐都需要验证或适配。

它通常不减少最终输出 Token 数，也不减少外层 Agent 请求数，而是减少串行解码迭代。标准推测采样的无损性质针对目标分布，不是任务语义正确性；实际浮点数值和执行批次仍可能影响输出，见 [vLLM 保证及限制](https://github.com/vllm-project/vllm/blob/main/docs/features/speculative_decoding/README.md#lossless-guarantees-of-speculative-decoding)。不能承诺每个负载加速。

这是社区已有技术，不计作 TAIR 新发明。公开 main 分支支持不代表我们当前模型、部署版本、自定义分类续写和结构化解码组合已经兼容。本轮未验证该组合，也未确认 SAM-Decoding 的代码再分发许可；借入代码前需核对具体版本的许可。

### 4. 内容引用与补丁：真正减少输出 Token，但适用性仍是难点

输出内容 ID、参数或小补丁，由运行时恢复大段内容，能减少模型实际生成的文本。文件哈希、类型检查和唯一补丁匹配能检查应用条件，不能证明任意新需求与旧内容语义等价。此前失败实验应作为负例保留，不能仅换一种提示再宣称解决。

SFT 可作为后续协议遵循和选择策略实验；当前没有证据证明必须训练，也没有证据证明训练能保证通用复用正确。优先建立明确执行协议、负例和未见任务测试集。

## 下一轮实验设计（尚未运行）

优先级：结果引用 Plan → 检索式推测解码兼容性与收益 → 有明确前置条件的直接复用。先做只读结果引用任务，再扩展写入，避免一次混入多个机制。

主要对照组：

1. 同模型和服务配置上的 Native Pi。
2. 当前 TAIR Plan，固定动态复用开关。
3. 仅增加结果引用的 Plan。
4. 第 3 组加检索式推测解码；隔离服务验证，不能直接替换生产。

另做 Native + 同一推测解码配置，区分 vLLM 自身收益与 TAIR 增量。直接内容复用单独开关消融，避免将草稿验证和整段复用混为一个命中率。

覆盖冷启动、完全重复、参数变化、需求变化、源码变化、未见任务族和错误恢复。每组独立码表，固定模型/引擎提交、采样、并发、工具权限与完成条件，交错重复运行并保留失败。

必须同时报告：

- 首次行为正确率、最终正确率、完整任务闭环与超时。
- 模型请求数及重试、生成 Token、分类控制记录、逻辑输入 Token。
- 草稿数、接受 Token、接受率及解码迭代数；与内容复用命中分开。
- 端到端耗时、预填充/解码/工具/验证/修复区间及完整耗时分布。
- 冷启动和暖态分别统计，计入检索、校验、未命中及失败回退成本。

只有在相同质量要求下跨任务稳定降低总耗时，才考虑默认启用。外部论文的加速倍数不替代本项目测量。

## 资料入口

- [较早的动作码表与 Agent replay 调研](AGENT_REUSE_RESEARCH.md)：历史研究背景。
- [Pi 集成文档](../integrations/pijit/README.md)：当前开关、使用与实验报告索引。
- [冻结实验目录](../results/experiments/)：原始证据，禁止覆盖，包括失败实验。
- 仓库验证：`pytest -q` 与 `python benchmarks/verify_archive.py`；这些检查不替代 GPU 性能实验。
