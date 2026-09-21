# Action codebooks and Agent replay: research update

For the 2026-09-21 experiments and the Code Mode / retrieval-based speculative decoding review, see [the current research overview](ACCELERATION_RESEARCH_STATUS.md). This document retains the earlier research snapshot.

Checked 2026-09-18. This extends the [schema/field prior-art review](SCHEMA_TOOLCALL_RELATED_WORK.md)
to action reuse and whole-Agent overhead. Papers, official repositories and selected
implementation files were inspected; none of these external systems was installed
or benchmarked. Repository links track mutable branches, not pinned reproductions.
Similarity judgments are our interpretation, not a priority or novelty determination.

## Closest work

| Work | Primary sources | Overlap with TAIR | Material difference |
|---|---|---|---|
| ToolkenGPT (2023) | [Paper](https://arxiv.org/abs/2305.11554), [code](https://github.com/ber666/toolkengpt) | Discrete tool-token selection | Learns tool embeddings with a frozen base model; our current engine path reads existing token logits without training new tool embeddings. |
| ToolGen (2024 preprint; ICLR 2025) | [Paper](https://arxiv.org/abs/2410.03439), [code](https://github.com/Reason-Wang/ToolGen) | Tool identity becomes a token instead of a long textual selection | Expands vocabulary and fine-tunes the model. After selection, the Agent retrieves the selected tool's documentation and generates arguments. |
| AgentRR (2025) | [Paper](https://arxiv.org/abs/2505.17716), [implementation in MobiAgent](https://github.com/IPADS-SAI/MobiAgent/tree/main/agent_rr) | Record, check and replay experience; fall back when reuse is unsuitable | Covers multi-level experience and action sequences. TAIR's current exact JIT binds individual typed edits to task, path and source state. |
| Agent Workflow Memory (2024) | [Paper](https://arxiv.org/abs/2409.07429), [code](https://github.com/zorazrw/agent-workflow-memory) | Offline or online extraction of reusable workflows | Primarily supplies workflows to guide subsequent generation; memory retrieval alone does not establish model-free replay. |
| Voyager (2023) | [Paper](https://arxiv.org/abs/2305.16291), [code](https://github.com/MineDojo/Voyager) | Growing library of reusable executable skills | Focuses on skill acquisition, retrieval and composition, not a guarantee of zero model calls on a skill hit. |
| LLMCompiler (2023 preprint; ICML 2024) | [Paper](https://arxiv.org/abs/2312.04511), [code](https://github.com/SqueezeAILab/LLMCompiler) | Reduces sequential Agent/tool overhead | Plans dependencies and parallelizes eligible calls; this differs from learned action memoization. |
| SGLang (2023 preprint) | [Paper](https://arxiv.org/abs/2312.07104), [code](https://github.com/sgl-project/sglang) | Structured execution and reuse of inference work | RadixAttention reuses KV prefixes. Our client continuation-token cache saves tokenization work, separately from server-side retained KV. |

## What the implementation evidence establishes

In MobiAgent's [action_cache/tree.py](https://github.com/IPADS-SAI/MobiAgent/blob/main/agent_rr/action_cache/tree.py),
`ActionTreeNode.get_cached_action` matches exact task descriptions;
`ActionTreeNodeFuzzy.get_cached_action` uses embedding similarity.
`ActionTree.execute` can reuse a cached action, optionally check the target UI
element, and call `agent.generate` when generation is needed. The tree also
searches for short reusable action paths. This is concrete overlap with guarded
action reuse. Optional UI checks do not prove complete semantic correctness,
and fuzzy lookup still has embedding/reranking costs. The broader AgentRR paper
includes model-assisted experience replay; not every replay mode eliminates inference.

ToolGen's [method, sections 3.2–3.6](https://arxiv.org/html/2410.03439v1)
clarifies a scaling constraint: registering a token does not teach its meaning.
Tool knowledge and query-to-token associations are trained; the selected token
is followed by documentation retrieval and argument generation. TAIR currently
uses meaningful existing labels such as `default`, `help` and `required`, with
source-bound local argument binding. Adding arbitrary action IDs to a schema
only restricts legal output; it does not establish that an unchanged model can
select them correctly. A growing codebook needs an explicit semantic mapping
through binding, retrieval/context or learning, whose cost must be counted.

## Current TAIR evidence and claim boundary

The defensible research target is an evaluated combination of compact typed
actions, engine-side candidate readout, retained-KV continuation and guarded
dynamic reuse. Discrete tool tokens, structured decoding, workflow memory and
record/replay are established directions. Neither renaming masked greedy selection
as classification nor calling memoization JIT establishes novelty.

The opt-in exact replay path in [jit_codebook.py](../deploy/jit_codebook.py)
uses task text (with surrounding whitespace stripped), absolute path and source
hash, then checks the decoded result hash. It is not fuzzy task generalization
or online model training. Local syntax validation is not a behavior oracle;
configured project verification and external experiment oracles have separate
roles. Static schema binding, learned JIT hits, client tokenization-cache hits
and server KV reuse must remain separate metrics.

The [matched outer-Agent experiment](../results/experiments/outer-agent-20260918-a/REPORT.md)
passed 36/36 task attempts across three tasks, two repeats, three arms and two
rounds. Across both rounds, optimized mean time was 10.984 s, previous 12.110 s,
and native 10.652 s: 9.3% less time than the previous path, but still 3.1% slower
than native. Native here is stock Pi on the same patched vLLM, not an independent
unpatched vLLM deployment. Each custom arm hit 12/12 covered second-round JIT
edits; only four of six second-round task attempts used those edits. General
summary repair remained outside this coverage. These denominators do not prove
universal hit rates or a general Agent speedup. Recovery costs remain included.

## Next experiments, not implemented results

1. **Guarded multi-step reuse (AgentRR/AWM comparison).** Compare current atomic
   edit replay with reusable sequences that include explicit preconditions,
   state checks and failure exits. Measure whether this removes outer planning
   calls, not just argument generation. Dependent writes to one file must retain
   their ordering; a failed sequence is not automatically a reversible transaction.
2. **Action coverage and semantic mapping (ToolkenGPT/ToolGen comparison).**
   Separate exact repeated tasks, paraphrases, new parameter values, changed
   source states and unseen action families. Compare local binding, bounded
   retrieval and any future learned mapping. Record candidate count, lookup
   cost, input tokens, wrong selections and rejection/fallback behavior. Larger
   enums alone are not a trained tool vocabulary.
3. **Outer-loop overhead (LLMCompiler/runtime comparison).** Ablate client
   continuation caching, directory guarding and sequence reuse independently.
   Consider parallel execution only for independent work. Keep tokenization,
   queueing, prefill, decode, tools, validation and recovery boundaries explicit.

Use matched native and current TAIR baselines, both cold and warm rounds, fresh
Agent sessions, fixed engine/model revisions and broader held-out tasks. Preserve
failures and changed-state negative cases. Report task success, edit-level and
task-level coverage, total model calls and full latency distributions separately.
An optimized one-token constrained-generation baseline is necessary to isolate
any gain from direct logits readout itself. External papers' speedups are not
TAIR measurements and cannot substitute for these comparisons.
