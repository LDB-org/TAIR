# Complete bound-action tasks after mixed-batch dtype repair

Exclusive rerun: five repeats each of workers default 6 and 8, all starting from 4. Ten matched task triples. Independent AST equality and argparse behavior checks preserve explicit overrides. Source read, finite action binding, cold tokenization, inference, application and validation are included in specialized task times. Candidates include fixed values 2/4/6/8/10 and NONE; none is selected locally from the expected answer. Both bound arms share candidate order per pair.

The runner explicitly owns reading, validation and DONE. Only edit selection is delegated to the model. This prompt clarification follows pilot B, where one classifier selected NONE. B is retained and not pooled. This selected, very small fixture establishes neither coverage nor general coding quality.

| Arm | Correct | Mean task s | Median task s | Inference calls total | Input tokens | Generated tokens | Controls |
|---|---:|---:|---:|---:|---:|---:|---:|
| native | 10/10 | 3.631 | 3.645 | 30 | 51531 | 2291 | 0 |
| generate | 10/10 | 1.049 | 1.030 | 10 | 3347 | 390 | 0 |
| classify | 10/10 | 1.984 | 1.973 | 10 | 3367 | 0 | 10 |

| Bound arm | Mean preparation s | Mean service s | Mean initial queue s | Mean task minus initial queue s |
|---|---:|---:|---:|---:|
| generate | 0.273 | 0.460 | 0.000 | 1.049 |
| classify | 1.547 | 0.151 | 0.000 | 1.984 |

Observed native/classify mean task ratio: 1.830x. Observed generate/classify model service ratio: 3.054x.

Service = scheduled-to-first plus first-to-last output; excludes initial queue but includes later scheduling. Task-minus-queue is arithmetic subtraction of that initial queue only, not an isolated deployment latency prediction. Classification pays six extra sequential remote label-tokenization calls, cold on each task, deliberately included. Native has no comparable per-stage server metrics in this harness.

The native comparison changes orchestration (general Pi read/edit/reply versus specialized single request and deterministic reply). Native startup is included; specialized Python import/interpreter startup is excluded. Model, patched server and task oracle are shared, but prompts/tool catalogs differ. Competing proxy and CyberEdge services were frozen throughout this rerun; one-second load monitoring and per-request queue metrics are retained separately. Ten pairs on a selected fixture do not establish general workload performance. The generate/classify comparison better isolates representation, yet includes their different preparation costs.

No retries, failed samples or outliers were removed. All-classification requests are audited for sampler bypass. Runtime maintenance evidence lives in ../bound-action-task-20260918-maintenance/. Run A records the original engine failure; run B records post-fix semantic rejection. Both remain preserved.

## Isolation verification

52 one-second snapshots: peak running 1.0, peak waiting 0.0, monitor errors 0. These are sampled observations, not proof of no subsecond waits. Both bound arms expose mean initial queue below 0.04 ms. Competing proxy and CyberEdge remain frozen; final running/waiting counts are both zero. See ../bound-action-task-20260918-exclusive-monitor/.
