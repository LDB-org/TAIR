# Multi-operation Agent experiment (batch-context-agent-20260919-b)

Real Pi 0.85.1 on the existing 6 x RTX 5090 service. Three scenarios: CLI properties, alias, and a function fix with requested new tests. Independent cold/warm pairs restore source and keep only per-arm runtime state. Fresh Agent sessions, interleaved arm order, no benchmark retries.

## Full task comparison

| Arm | Passed/tasks | Total seconds | Outer model requests | All inference requests | Generated tokens | Control records | Input tokens | Edit hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 12/12 | 131.98 | 77 | 77 | 11271 | 0 | 169677 | 0 |
| batched | 12/12 | 117.24 | 40 | 44 | 6353 | 44 | 127306 | 1 |
| contextual | 12/12 | 99.69 | 36 | 42 | 4837 | 42 | 97758 | 2 |

Total time includes Pi startup, planning, tool execution, in-loop tests/recovery, final reply and independent behavior oracle. Nested compact-edit inference is included. Post-run artifact unittest reruns are outside measured task time. Failed tasks remain in totals and are not equivalent completed work.

## Observed batching

| Arm | Plans | Multi-operation plans | Maximum steps | Multi-tool responses | Tool errors including recovery | Blocked later steps |
|---|---:|---:|---:|---:|---:|---:|
| native | 0 | 0 | 0 | 0 | 0 | 0 |
| batched | 28 | 28 | 6 | 28 | 35 | 23 |
| contextual | 24 | 24 | 4 | 24 | 4 | 0 |

These are executed plan envelopes, not a promise that the entire task needs one inference. Plans themselves are generated; the existing compact-edit codebook is reused only inside compact_edit. Source discovery and final result interpretation may need further turns.

## Scenario totals

| Scenario | Native seconds / requests | Batched seconds / requests | Contextual seconds / requests |
|---|---:|---:|---:|
| alias | 28.72 / 24 | 31.69 / 13 | 28.38 / 14 |
| properties | 36.29 / 25 | 34.61 / 15 | 33.23 / 16 |
| summary_bug | 66.97 / 28 | 50.94 / 16 | 38.08 / 12 |

## Failures

Every full task passed the behavior oracle and original/additional test integrity check.

## Controls and limits

Native is the ordinary tools API on the same patched vLLM service, not a separate unpatched server. It retains the previous harness settings including parallel_tool_calls=false. Batched uses the prior multi-operation client with tokenizer caches and directory guard. Contextual adds a bounded filename inventory and observed-file edit restrictions, forbids empty edit spans, and defers replacement of unread existing files. Both use the same inner codebook and bypass the local single-clause dispatcher. It wraps standard Pi tools for sequential execution and blocks remaining steps after failure; successful earlier steps are not rolled back. Tool hooks remain active.

Both TAIR arms replace supported individual outer choices with the plan envelope (1..8 operations) and final reply; unsupported custom tools remain separate. Context gathering, failed/deferred generations and all recovery are included. This is an implementation comparison, not an isolated ablation of individual constraints. All actual runtime sources are archived per run. Prompts, grammar and control granularity differ, so this is an implementation comparison, not an isolated claim about classification speed.

Only a small handcrafted workload on a shared backend is covered. Counts, correctness, cold/warm timing and generated tokens are separate. Compile-only edit admission does not establish semantics; final behavior and test-integrity checks are independent. A tool error recovered inside an otherwise successful task remains visible in the batch profile.

`rows.jsonl`, `final-result.json`, raw Pi events, source snapshots and `batch-profile.json` contain the accounting. `verification.json`, `environment.json`, engine classification events and independent unittest reruns provide the post-run audit. Probe evidence in the separate batch-tools-execution-20260919 archive uses a mocked provider and real Pi tools; it is not a GPU performance result.

## Final revision and outcome

In B, write is withheld before the first successful file observation in a nonempty project; empty workspaces still permit new-file creation. This moves the discovery constraint before content generation. Unread-write deferral also reuses an already scheduled read instead of adding a duplicate. All other comparisons retain the same settings. A is preserved separately, including its long recovery and failed baseline tasks.

All 36 full tasks passed. Contextual took 99.69 seconds versus prior batched 117.24 seconds (15.0% lower) and native 131.98 seconds (24.5% lower). Outer requests fell from 40 to 36 versus prior batched; total requests including inner edit inference fell from 44 to 42. Generated tokens fell from 6353 to 4837. These are shared-backend small-workload observations, not guaranteed speedups.

Contextual had no missing-path or empty-oldText failures, blocked steps, or deferred writes. Its four failed tool results were pre-fix alias test runs; subsequent edits and tests succeeded. Prior batched had ten missing-path failures, two empty-oldText failures, and 23 blocked steps. Each contextual task used three outer requests; six tasks also invoked inner edit inference. Plans themselves remain generated, not learned as codebook entries.

The 12 function-repair outputs across all arms were additionally checked by injecting a negative-total error and in-place sorting into the function binding used by their tests, without changing archived source. Every original test suite passed and every suite caught both injected faults. This verifies the requested added tests have relevant behavioral checks for negative values and input immutability; it is not a general proof of completeness. See requested-test-review.json. This post-run review is outside measured task time.

All 86 TAIR inference requests have matching engine classification/sampler-bypass evidence. Runtime source snapshots match the tested revision. The server container still started at 2026-09-18T05:44:43.699377485Z; no service restart occurred. Tokenizer HTTP calls rose from 143 to 190, and preparation time was 19.67 versus 19.84 seconds (batched versus contextual), so this revision did not reduce tokenization overhead. Repository validation: 289 tests passed.
