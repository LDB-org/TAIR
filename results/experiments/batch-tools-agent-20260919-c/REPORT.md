# Multi-operation Agent experiment (batch-tools-agent-20260919-c)

Real Pi 0.85.1 on the existing 6 x RTX 5090 service. Three scenarios: CLI properties, alias, and a function fix with requested new tests. Independent cold/warm pairs restore source and keep only per-arm runtime state. Fresh Agent sessions, interleaved arm order, no benchmark retries.

## Full task comparison

| Arm | Passed/tasks | Total seconds | Outer model requests | All inference requests | Generated tokens | Control records | Input tokens | Edit hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 6/6 | 66.29 | 38 | 38 | 5974 | 0 | 84524 | 0 |
| optimized | 6/6 | 62.58 | 32 | 36 | 2325 | 36 | 95702 | 2 |
| batched | 6/6 | 53.76 | 20 | 22 | 3133 | 22 | 62894 | 0 |

Total time includes Pi startup, planning, tool execution, in-loop tests/recovery, final reply and independent behavior oracle. Nested compact-edit inference is included. Post-run artifact unittest reruns are outside measured task time. Failed tasks remain in totals and are not equivalent completed work.

## Observed batching

| Arm | Plans | Multi-operation plans | Maximum steps | Multi-tool responses | Tool errors including recovery | Blocked later steps |
|---|---:|---:|---:|---:|---:|---:|
| native | 0 | 0 | 0 | 0 | 0 | 0 |
| optimized | 0 | 0 | 0 | 0 | 0 | 0 |
| batched | 14 | 14 | 6 | 14 | 15 | 9 |

These are executed plan envelopes, not a promise that the entire task needs one inference. Plans themselves are generated; the existing compact-edit codebook is reused only inside compact_edit. Source discovery and final result interpretation may need further turns.

## Scenario totals

| Scenario | Native seconds / requests | Optimized single-step seconds / requests | Batched seconds / requests |
|---|---:|---:|---:|
| alias | 18.42 / 12 | 14.81 / 10 | 12.85 / 6 |
| properties | 16.88 / 12 | 16.85 / 10 | 15.54 / 8 |
| summary_bug | 30.99 / 14 | 30.92 / 16 | 25.37 / 8 |

## Failures

Every full task passed the behavior oracle and original/additional test integrity check.

## Controls and limits

Native is the ordinary tools API on the same patched vLLM service, not a separate unpatched server. It retains the previous harness settings including parallel_tool_calls=false. Optimized is the prior classification-first client with deterministic explicit-clause routing, tokenizer caches and directory guard. Batched uses the same inner codebook and tokenizer caches but bypasses the local single-clause dispatcher. It wraps standard Pi tools for sequential execution and blocks remaining steps after failure; successful earlier steps are not rolled back. Tool hooks remain active.

A offered execute_plan alongside individual tools. B and C replace the supported individual outer choices with the plan envelope (1..8 operations) and final reply; unsupported custom tools remain separate. All actual runtime sources are archived per run. Prompts, grammar and control granularity differ, so this is an implementation comparison, not an isolated claim about classification speed.

Only a small handcrafted workload on a shared backend is covered. Counts, correctness, cold/warm timing and generated tokens are separate. Compile-only edit admission does not establish semantics; final behavior and test-integrity checks are independent. A tool error recovered inside an otherwise successful task remains visible in the batch profile.

`rows.jsonl`, `final-result.json`, raw Pi events, source snapshots and `batch-profile.json` contain the accounting. `verification.json`, `environment.json`, engine classification events and independent unittest reruns provide the post-run audit. Probe evidence in the separate batch-tools-execution-20260919 archive uses a mocked provider and real Pi tools; it is not a GPU performance result.

## Final-code result and limitations

All 18 full tasks passed. Batch total time is 14.1% below optimized single-step and 18.9% below native in C; requests fall from 36/38 to 22. B observed only 6.8% lower total time against native, so these small shared-backend results do not establish a fixed speedup. C moved jsonschema import into batch validation; all source snapshots now match the final implementation.

Batch recovery includes 6 actual failures (4 missing-path reads, 2 empty-oldText edits) and 9 skipped later steps. Every task recovered within its measured run. Entire plans are generated, not stored in the codebook; this run had no compact-edit cache hits.

284 repository tests passed. Independent unittest reruns passed for all final projects, 58 classification requests have sampler-bypass evidence, and the temporary tunnel was closed.
