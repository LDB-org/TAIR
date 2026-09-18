# Complete bound-action tasks after mixed-batch dtype repair

Follow-up C: two repeats each of workers default 6 and 8, all starting from 4. Four matched task triples. Independent AST equality and argparse behavior checks preserve explicit overrides. Source read, finite action binding, cold tokenization, inference, application and validation are included in specialized task times. Candidates include fixed values 2/4/6/8/10 and NONE; none is selected locally from the expected answer. Both bound arms share candidate order per pair.

The runner explicitly owns reading, validation and DONE. Only edit selection is delegated to the model. This prompt clarification follows pilot B, where one classifier selected NONE. B is retained and not pooled. This selected, very small fixture establishes neither coverage nor general coding quality.

| Arm | Correct | Mean task s | Median task s | Inference calls total | Input tokens | Generated tokens | Controls |
|---|---:|---:|---:|---:|---:|---:|---:|
| native | 4/4 | 30.899 | 27.904 | 12 | 20539 | 867 | 0 |
| generate | 4/4 | 11.255 | 8.032 | 4 | 1338 | 156 | 0 |
| classify | 4/4 | 11.233 | 8.839 | 4 | 1346 | 0 | 4 |

| Bound arm | Mean preparation s | Mean service s | Mean initial queue s | Mean task minus initial queue s |
|---|---:|---:|---:|---:|
| generate | 0.232 | 0.632 | 10.049 | 1.206 |
| classify | 1.401 | 0.156 | 9.314 | 1.920 |

Observed native/classify mean task ratio: 2.751x. Observed generate/classify model service ratio: 4.057x.

Service = scheduled-to-first plus first-to-last output; excludes initial queue but includes later scheduling. Task-minus-queue is arithmetic subtraction of that initial queue only, not an isolated deployment latency prediction. Classification pays six extra sequential remote label-tokenization calls, cold on each task, deliberately included. Native has no comparable per-stage server metrics in this harness.

The native comparison changes orchestration (general Pi read/edit/reply versus specialized single request and deterministic reply). Native startup is included; specialized Python import/interpreter startup is excluded. Model, patched server and task oracle are shared, but prompts/tool catalogs differ. Shared traffic and four pairs prevent attributing the entire observed task ratio to classification or making a stable speed claim. The generate/classify comparison better isolates representation, yet includes their different preparation costs.

No retries, failed samples or outliers were removed. All-classification requests are audited for sampler bypass. Runtime maintenance evidence lives in ../bound-action-task-20260918-maintenance/. Run A records the original engine failure; run B records post-fix semantic rejection. Both remain preserved.
