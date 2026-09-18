# Experiment index

Start with these reports. Their request-level records, errors, generated workspaces
and source snapshots live in `results/experiments/`. The archive includes failed
and superseded runs; not every directory supports a headline claim.

| Question | Report | Evidence |
| --- | --- | --- |
| Can direct classification and argument generation share KV? | [Direct engine experiment](DEEPSEEK_DIRECT_ENGINE_EXPERIMENT.md) | [Engine run](../results/experiments/pi-deepseek-direct-engine-20260918-a/) |
| Does removing a wrapper help long output? | [Long-output experiment](DEEPSEEK_LONG_OUTPUT_EXPERIMENT.md) | [Long-output run](../results/experiments/pi-deepseek-long-20260918-a/) |
| Can compact edits and engine classification combine? | [Combined experiment](DEEPSEEK_COMBINED_STRUCTURAL_EXPERIMENT.md) | [Combined run](../results/experiments/pi-combined-structural-20260918-a/) |
| Can a bounded edit be entirely classified? | [Finite classification probe](ALL_CLASSIFICATION_PROBE.md) | [Classification run](../results/experiments/pi-all-classification-20260918-a/), [prompt ablation](../results/experiments/pi-operation-prompt-20260918-a/) |
| Where did the large token reduction come from? | [Compact protocol optimization](PI_COMPACT_STRUCTURAL_OPTIMIZATION.md) | [Scoped typed run](../results/experiments/pi-scoped-typed-20260918-a/) |
| What happened with all Pi tool candidates? | [All-tools experiment](PI_ALL_TOOLS_ENGINE_EXPERIMENT.md) | [Engine run](../results/experiments/pi-all-tools-engine-20260918-a/), [native run](../results/experiments/pi-all-tools-native-20260918-a/) |
| What is the concurrency evidence? | [Concurrency experiment](PI_ENGINE_CONCURRENCY_EXPERIMENT.md) | [Concurrency run](../results/experiments/pi-concurrency-20260918-a/) |
| Did protocol training improve behavior? | [Training v1](PROTOCOL_SFT_EXPERIMENT.md), [v2](PROTOCOL_SFT_V2_EXPERIMENT.md) | [Archived training and comparison records](../results/experiments/) |

## Dynamic codebook follow-up

[JIT-style admission, reuse and fallback](JIT_CODEBOOK_PROBE.md) tests an initially empty codebook on ten sequential tasks. It demonstrates one generated-template reuse, but no aggregate speedup; confidence-only gating produces false accepts.

## Reading the numbers

Generated tokens, internal classification control IDs and injected input tokens
are separate quantities. First-attempt totals include incorrect answers. Totals
with fallback must include failed attempts and retries. Schema validity, exact
arguments, behavior tests, task completion and final correctness are different
acceptance criteria.

Latency records have different boundaries: queue wait, initial prefill, decode,
API/SSH round trips, deterministic application and behavior tests. The shared
server experiments do not establish stable throughput. The finite classification
probe's queue-excluded interval is not GPU-kernel time or a same-quality speedup.

## Archive and migration

All experimental evidence was copied byte for byte. The migration verifier checks
both imported-file hashes and existing checksum manifests, including legacy root-
relative manifests. Live runners were adjusted to accept environment-specific
host/package configuration; their original versions remain in frozen snapshots.

The archived reports retain their original language and historical commands.
[The current reproduction guide](REPRODUCE.md) supersedes those commands for local
paths and host configuration. Their recorded measurements are unchanged. Some
reports mention upstream-wide test totals from the original OpenJev checkout;
those totals are historical and do not describe this standalone repository.

## Historical reports

- [Finite whole-edit classification probe](ALL_CLASSIFICATION_PROBE.md)

- [DeepSeek: direct classification plus compact structural edits](DEEPSEEK_COMBINED_STRUCTURAL_EXPERIMENT.md)

- [DeepSeek: direct tool classification inside vLLM](DEEPSEEK_DIRECT_ENGINE_EXPERIMENT.md)

- [DeepSeek long-output experiment](DEEPSEEK_LONG_OUTPUT_EXPERIMENT.md)

- [Pi 全部内置工具的引擎侧协议实验](PI_ALL_TOOLS_ENGINE_EXPERIMENT.md)

- [操作适用性约束实验（2026-09-18）](PI_APPLICABILITY_EXPERIMENT.md)

- [结构操作协议：压缩提示与有类型参数](PI_COMPACT_STRUCTURAL_OPTIMIZATION.md)

- [Pi 工具：直接 logits 分类后生成参数](PI_DIRECT_LOGITS_EXPERIMENT.md)

- [Pi 引擎协议：原始参数正文与并发实验](PI_ENGINE_CONCURRENCY_EXPERIMENT.md)

- [Pi 编程任务 token 与耗时对照](PI_ENGINE_TOOLCALL_COMPARISON.md)

- [Pi 工具协议下沉与真实编程任务](PI_ENGINE_TOOLCALL_EXPERIMENT.md)

- [多区域引用编辑实验](PI_MULTI_REGION_EDIT_EXPERIMENT.md)

- [工具名选择协议实验](PI_NAMED_PROTOCOL_EXPERIMENT.md)

- [区域引用与原生 Pi edit 对照](PI_REGION_EDIT_EXPERIMENT.md)

- [冻结多区域协议的新任务筛查](PI_REGION_HOLDOUT_EXPERIMENT.md)

- [显式层级的多行编辑协议](PI_REGION_LINE_PROTOCOL.md)

- [有限结构操作＋表达式生成实验](PI_STRUCTURAL_EDIT_EXPERIMENT.md)

- [Protocol SFT experiment v1](PROTOCOL_SFT_EXPERIMENT.md)

- [Protocol SFT v2: diverse payload generalization](PROTOCOL_SFT_V2_EXPERIMENT.md)

- [Schema-directed tool-call experiment](SCHEMA_TOOLCALL_EXPERIMENT.md)

- [Schema-directed classification and generation: prior-art check](SCHEMA_TOOLCALL_RELATED_WORK.md)

- [Yuesheng 引擎每请求计时](YUESHENG_ENGINE_METRICS.md)

- [Yuesheng 单请求分类与生成实验](YUESHENG_FUSED_PROTOCOL.md)

- [Yuesheng DeepSeek 协议服务实验](YUESHENG_PROTOCOL_DEPLOYMENT.md)
