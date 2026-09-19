# Multi-operation Agent experiment (batch-context-agent-20260919-a)

Real Pi 0.85.1 on the existing 6 x RTX 5090 service. Three scenarios: CLI properties, alias, and a function fix with requested new tests. Independent cold/warm pairs restore source and keep only per-arm runtime state. Fresh Agent sessions, interleaved arm order, no benchmark retries.

## Full task comparison

| Arm | Passed/tasks | Total seconds | Outer model requests | All inference requests | Generated tokens | Control records | Input tokens | Edit hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 12/12 | 136.55 | 77 | 77 | 11878 | 0 | 171266 | 0 |
| batched | 10/12 | 102.81 | 36 | 38 | 5656 | 38 | 112948 | 1 |
| contextual | 12/12 | 127.89 | 44 | 48 | 7127 | 48 | 147588 | 2 |

Total time includes Pi startup, planning, tool execution, in-loop tests/recovery, final reply and independent behavior oracle. Nested compact-edit inference is included. Post-run artifact unittest reruns are outside measured task time. Failed tasks remain in totals and are not equivalent completed work.

## Observed batching

| Arm | Plans | Multi-operation plans | Maximum steps | Multi-tool responses | Tool errors including recovery | Blocked later steps |
|---|---:|---:|---:|---:|---:|---:|
| native | 0 | 0 | 0 | 0 | 0 | 0 |
| batched | 24 | 24 | 6 | 24 | 36 | 23 |
| contextual | 32 | 31 | 4 | 31 | 15 | 4 |

These are executed plan envelopes, not a promise that the entire task needs one inference. Plans themselves are generated; the existing compact-edit codebook is reused only inside compact_edit. Source discovery and final result interpretation may need further turns.

## Scenario totals

| Scenario | Native seconds / requests | Batched seconds / requests | Contextual seconds / requests |
|---|---:|---:|---:|
| alias | 29.68 / 24 | 31.43 / 12 | 26.62 / 12 |
| properties | 41.93 / 25 | 19.02 / 10 | 30.72 / 16 |
| summary_bug | 64.94 / 28 | 52.36 / 16 | 70.55 / 20 |

## Failures

- 1-properties-batched-1: behavior passed=False; requested-test integrity passed=True; no retry or removal.
- 1-properties-batched-2: behavior passed=False; requested-test integrity passed=True; no retry or removal.

## Controls and limits

Native is the ordinary tools API on the same patched vLLM service, not a separate unpatched server. It retains the previous harness settings including parallel_tool_calls=false. Batched uses the prior multi-operation client with tokenizer caches and directory guard. Contextual adds a bounded filename inventory and observed-file edit restrictions, forbids empty edit spans, and defers replacement of unread existing files. Both use the same inner codebook and bypass the local single-clause dispatcher. It wraps standard Pi tools for sequential execution and blocks remaining steps after failure; successful earlier steps are not rolled back. Tool hooks remain active.

Both TAIR arms replace supported individual outer choices with the plan envelope (1..8 operations) and final reply; unsupported custom tools remain separate. Context gathering, failed/deferred generations and all recovery are included. This is an implementation comparison, not an isolated ablation of individual constraints. All actual runtime sources are archived per run. Prompts, grammar and control granularity differ, so this is an implementation comparison, not an isolated claim about classification speed.

Only a small handcrafted workload on a shared backend is covered. Counts, correctness, cold/warm timing and generated tokens are separate. Compile-only edit admission does not establish semantics; final behavior and test-integrity checks are independent. A tool error recovered inside an otherwise successful task remains visible in the batch profile.

`rows.jsonl`, `final-result.json`, raw Pi events, source snapshots and `batch-profile.json` contain the accounting. `verification.json`, `environment.json`, engine classification events and independent unittest reruns provide the post-run audit. Probe evidence in the separate batch-tools-execution-20260919 archive uses a mocked provider and real Pi tools; it is not a GPU performance result.

## Diagnostic outcome

Contextual passed 12/12, native 12/12, and prior batched 10/12. Both prior-batched failures ended with a preparatory reply without edits; their short times cannot represent equal completed work. Contextual took 127.89 seconds versus native 136.55 seconds, but function repair regressed (70.55 versus native 64.94 seconds and batched 52.36 seconds). Six generated plans required unread-write deferral. In one warm function repair, actual incorrect edits caused repeated recovery and 32.95 seconds total. All records remain included.

Planning details distinguish missing paths/empty spans, blocked steps, and failed tests. Some test failures were deliberate pre-fix checks, others exposed incorrect edits. Neither raw error totals nor final validity alone establish semantic efficiency. The next revision removes write from the first discovery catalog in a nonempty project, before generating replacement content.
