# Schema action development experiment

2026-09-18. Client-only opt-in change; no engine restart or server patch.
Executable codebook stays local. Schema enum compiles to two single-token IDs
(default=14979, generate=77772); prompt includes source/task and classification
question, with no codebook or enum table. Model /model, existing experimental
vLLM direct candidate-logit endpoint through localhost SSH tunnel.

Initial probe failed to select default changes. Revised property question selects
default correctly for two supported cases, but also for unrelated logging with
very low absolute candidate mass. Final implementation adds candidate mass >= .1
alongside conditional probability >= .95, margin >= 3, and conservative local
binding. This is development prompt tuning, not held-out classifier validation.
Probe files retain unsuccessful outputs; their first line is label diagnostics.

18 live edits: three task forms, three repeats, two interleaved arms. All exact
source oracles passed. Supported cases: generator mean .953703 s vs schema .599493 s
(1.59x; 37.1% less wall time). Six schema hits generated zero argument tokens,
used six classification controls, and reduced input 2919 to 507 tokens.
Unsupported wording: .922787 s vs 1.546178 s (67.6% slower), with classification
and generation both charged. Combined deliberately chosen 2:1 case mix: .943397 s
vs .915055 s (3.0% less time). No general-agent speedup conclusion follows.

Timing is bridge.run wall time including preparation, HTTP, classification,
fallback, local validation/backup/apply, excluding final metrics-file append.
Source reset and test-oracle comparison are outside this boundary. Label cache
starts empty and is revision-keyed; raw rows retain cold/warm traces. There was
no warmup exclusion. Generator baseline is the existing compact-edit path with
codebook disabled, NOT vanilla vLLM or a full native Pi agent run. Code correctness
oracle is exact resulting source, independent of response schema validity.

Both competing services remained frozen, restart count zero, and final running/
waiting metrics zero (server-after.txt). No continuous queue monitor was collected
for this run; these snapshots alone do not prove every request had zero queue.
All code snapshots and original failed probes are retained. State/cache and
modified fixture projects lived under a temporary directory outside the archive.
