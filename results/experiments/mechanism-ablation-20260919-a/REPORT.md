# Mechanism ablation: current implementation

Six synthetic development task families, shared backend. Native is an ordinary tools API reference on the patched server, not a single-factor edge. The base is compact-tool Agent with codebook and optional optimizations disabled, but parallel preparation enabled. Serial edge measures removal of parallel preparation. Schema/JIT and direct classification are tested separately at edit/service boundaries. Single-factor effects are conditional on the specified parent; they are not additive.

## Full Agent: all attempts

| Arm | Basic/audited passed | Tasks | Total s | p95 s | Requests | Timeouts | Usage complete |
|---|---:|---:|---:|---:|---:|---:|---|
| native | 12/12 | 12 | 164.533 | 19.689 | 98 | 0 | True |
| base | 9/9 | 12 | 132.087 | 16.611 | 71 | 0 | True |
| serial | 10/10 | 12 | 151.574 | 17.691 | 70 | 0 | True |
| labels | 10/10 | 12 | 125.245 | 14.176 | 69 | 0 | True |
| continuation | 10/10 | 12 | 126.393 | 16.457 | 72 | 0 | True |
| codebook | 10/10 | 12 | 135.715 | 18.739 | 73 | 0 | True |
| routing | 10/10 | 12 | 123.807 | 15.591 | 66 | 0 | True |
| directory | 10/10 | 12 | 126.455 | 14.628 | 66 | 0 | True |
| batch | 10/10 | 12 | 106.986 | 12.544 | 44 | 0 | True |
| context | 10/10 | 12 | 95.079 | 9.724 | 41 | 0 | True |

## One-factor edges

Negative savings mean a slowdown. Serial is the treatment that DISABLES preparation overlap; swap before/after and recompute the percentage denominator when discussing enabling parallel preparation. Counts are lower bounds whenever usage is incomplete. Fast failed tasks are not equivalent completed work.

| Parent → treatment | Before s | After s | Saved s | Saved % | Audited passes before/after |
|---|---:|---:|---:|---:|---:|
| base → serial | 132.087 | 151.574 | -19.488 | -14.8% | 9/10 |
| base → labels | 132.087 | 125.245 | 6.842 | 5.2% | 9/10 |
| labels → continuation | 125.245 | 126.393 | -1.147 | -0.9% | 10/10 |
| base → codebook | 132.087 | 135.715 | -3.629 | -2.7% | 9/10 |
| codebook → routing | 135.715 | 123.807 | 11.908 | 8.8% | 10/10 |
| base → directory | 132.087 | 126.455 | 5.632 | 4.3% | 9/10 |
| base → batch | 132.087 | 106.986 | 25.100 | 19.0% | 9/10 |
| batch → context | 106.986 | 95.079 | 11.907 | 11.1% | 10/10 |

## Mutually successful pairs (selected subsets)

These omit failed tasks and are NOT a substitute for the complete outcomes above. Different edges can contain different pairs. They show whether a lower total merely reflects faster failures.

| Parent → treatment | Successful pairs | Before s | After s | Saved s | Saved % |
|---|---:|---:|---:|---:|---:|
| base → serial | 9 | 89.846 | 107.389 | -17.542 | -19.5% |
| base → labels | 9 | 89.846 | 87.119 | 2.728 | 3.0% |
| labels → continuation | 10 | 100.781 | 104.020 | -3.239 | -3.2% |
| base → codebook | 9 | 89.846 | 95.054 | -5.208 | -5.8% |
| codebook → routing | 10 | 111.872 | 100.950 | 10.923 | 9.8% |
| base → directory | 9 | 89.846 | 87.470 | 2.376 | 2.6% |
| base → batch | 9 | 89.846 | 69.864 | 19.982 | 22.2% |
| batch → context | 10 | 82.523 | 79.459 | 3.064 | 3.7% |

## Mechanism activation

| Arm | Codebook hits | Local routes | Label hits | Continuation hits | Directory redirects | Plans | Tokenize requests | Preparation s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.000 |
| base | 0 | 0 | 0 | 0 | 0 | 0 | 923 | 33.046 |
| serial | 0 | 0 | 0 | 0 | 0 | 0 | 910 | 52.293 |
| labels | 0 | 0 | 63 | 0 | 0 | 0 | 519 | 29.306 |
| continuation | 0 | 0 | 66 | 65 | 0 | 0 | 199 | 26.612 |
| codebook | 1 | 0 | 0 | 0 | 0 | 0 | 939 | 33.246 |
| routing | 2 | 4 | 0 | 0 | 0 | 0 | 838 | 32.192 |
| directory | 0 | 0 | 0 | 0 | 2 | 0 | 858 | 31.903 |
| batch | 0 | 0 | 0 | 0 | 0 | 30 | 236 | 18.241 |
| context | 0 | 0 | 0 | 0 | 0 | 26 | 229 | 15.731 |

## Edit-level controls

| Experiment | Arm | Passed/tasks | Total s | Generated tokens | Controls | Input tokens |
|---|---|---:|---:|---:|---:|---:|
| edits | native | 21/21 | 26.5574 | 2172 | 0 | 8106 |
| edits | compact_generate | 21/21 | 24.6168 | 210 | 21 | 10146 |
| edits | optimized | 21/21 | 17.6415 | 60 | 21 | 5121 |
| replay | generate | 18/18 | 19.9623 | 222 | 18 | 8868 |
| replay | schema_only | 18/18 | 14.9622 | 66 | 18 | 4032 |
| replay | schema_jit | 18/18 | 7.7185 | 33 | 9 | 2016 |

Cold and warm replay details, ideal-classification service/HTTP times, per-case and per-round Agent deltas, mutually successful subsets, and failures are in analysis.json. The ideal study excludes recorded offline preparation and two separately preserved warmups; full-Agent/edit studies exclude no warmup or formal failed attempt. These boundaries must not be combined.

The repaired context grammar is used throughout. Single-factor configuration checks passed before the run. Behavior oracles are outside Agent workspaces; original test integrity is checked. Summary-task requested tests receive an additional post-run mutation review, preserving original raw results.

No model service restart or patch installation. Shared backend, one cold/warm pair per Agent family; observed deltas do not establish a stable speedup. Compare cold/warm and family variation before attributing an overall delta to a mechanism. Entire plans are generated and are not codebook entries.
