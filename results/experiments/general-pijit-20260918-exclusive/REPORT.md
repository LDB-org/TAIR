# Full Pi Agent comparison under exclusive load

Three selected small coding tasks, two repeats each: mixed integer/float CLI defaults, numerical-summary bug repair with test changes, and a multi-file CLI feature with module/tests/README. Both arms have read/edit/write/bash; pijit additionally exposes compact_edit and set_cli_default and advertises them in its prompt. Agents choose their own sequence and arguments. No complete correct action is prebound and no final reply is synthesized by the harness.

Each task starts with a fresh project, codebook and label cache. Timing includes Pi startup, preparation, all model/tool calls, recovery, model final reply, and independent final validation. Project fixtures are created before timing. Normal edit/write fallback is allowed. Compact/preset operations have normal syntax guards without running a final-task oracle against intermediate edits. Final check scripts live outside the project; native and pijit receive the same checks.

| Task (2 attempts per arm) | Native mean s | Pijit mean s | Native checks passed | Pijit checks passed |
|---|---:|---:|---:|---:|
| mixed_config | 9.403 | 9.689 | 2/2 | 2/2 |
| summary_bug | 15.354 | 15.395 | 2/2 | 2/2 |
| multifile_feature | 21.737 | 22.382 | 2/2 | 1/2 |

| Aggregate | Native | Pijit |
|---|---:|---:|
| Tasks passing final checks | 6 | 5 |
| Mean complete seconds | 15.498 | 15.822 |
| Total complete seconds | 92.988 | 94.932 |
| Inference requests | 47 | 50 |
| Input tokens | 131593 | 168067 |
| Generated tokens | 8332 | 4382 |
| Classification controls | 0 | 50 |
| Tool errors | 0 | 7 |
| Preset applied | 0 | 0 |
| Codebook hits | 0 | 0 |

No overall speedup is demonstrated: mean complete time is about 2.1% higher, and final-check success is 5/6 versus 6/6. Generated tokens fall about 47.4%, while input tokens rise about 27.7%. Different output style/verbosity and tool paths affect these counts, so output reduction is not entirely attributable to structural compression.

Crucially, pijit never selected compact_edit or set_cli_default in these six runs: the complete-action reuse path was not exercised. It used ordinary read/edit/write/bash, with classification of the outer tool followed by generated arguments. All fifty classification requests have engine sampler-bypass evidence. There were seven tool errors (six attempts to read a directory and one README exact-text mismatch) but no HTTP/inference error records; those are different counters.

The failed multi-file run implemented the functionality and passed the functional checks but omitted the explicitly requested README update. The oracle failed at the README assertion. Agent-generated tests passing therefore did not establish full instruction completion. Project-test commands are retained in project-test-execution.json. Final oracles cover specified behavior and basic file/document presence, not exhaustive quality or every requested test-coverage detail.

This is a small diagnostic suite, not a broad benchmark of general agents. It shows that the ideal 5x specialized-task result does not automatically transfer to the current general Pi integration. Future work should address automatically reaching the reusable action path and tool-selection errors, rather than claiming classification alone accelerates every Agent.

The model proxy and CyberEdge remain frozen; no engine configuration was changed. Monitoring and final state are in ../general-pijit-20260918-exclusive-monitor/. All attempts, failed tool calls and final artifacts are preserved. Auth/model runtime profiles and disposable bytecode caches are excluded.
