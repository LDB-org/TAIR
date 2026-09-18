# Matched edit-level schema and learned JIT experiment

54/54 edits passed the identical configured AST plus behavior oracle: three task
kinds, three repeats, three arms, two rounds. Every second round restores the
original source at the same path while retaining only runtime state. There is no
Agent planning/reply in this benchmark. Timing is bridge.run including HTTP,
preparation, model work, backup/apply and project verification, excluding fixture
restore and final metrics append. No warmup exclusions or retries.

| Edit | Schema+JIT cold | Schema+JIT warm | Schema-only warm | Generation warm |
|---|---:|---:|---:|---:|
| Float default | .785124 s | .043967 s | .668310 s | 1.173420 s |
| Help string | .705603 s | .044310 s | .614885 s | 1.159718 s |
| Add alias | 1.097651 s | .045635 s | .991617 s | .981050 s |

All entries are arithmetic means of three samples. Warm JIT hits 9/9 edits;
all nine make zero HTTP calls, generate zero argument tokens, and emit zero model
classification controls. Cold property edits classify and execute local templates;
cold alias edits skip schema classification, generate a typed action, validate it
and admit it. Schema-only aliases continue generating in both rounds. Thus the
alias test verifies actual first-round generated-action admission and second-round
reuse, rather than merely exercising a prewritten preset.

Compared with schema-only in the same second round, warm replay is about 15.2x,
13.9x and 21.7x faster for these edit boundaries. These are not full-Agent ratios;
see ../schema-jit-agent-20260918-b/REPORT.md, which shows no overall advantage over
native Pi on the mixed task set. Absolute warm time includes Python subprocess
project verification, explaining its difference from the Agent tool's syntax-only
internal edit timing.

The enum/codebook is not serialized into classification prompts. Exact memoization
uses task text, path and source hash, then revalidates typed operations, result hash
and project checks. Three-sample development fixtures do not establish semantic
routing quality or scaling to arbitrary tasks. Raw traces, learned books and
sampler audit are retained. Competing services remained frozen; no restart occurred.
