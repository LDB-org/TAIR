# Multi-operation Agent experiment (batch-tools-agent-20260919-a)

Real Pi 0.85.1 on the existing 6 x RTX 5090 service. Three scenarios: CLI properties, alias, and a function fix with requested new tests. Independent cold/warm pairs restore source and keep only per-arm runtime state. Fresh Agent sessions, interleaved arm order, no benchmark retries.

## Full task comparison

| Arm | Passed/tasks | Total seconds | Outer model requests | All inference requests | Generated tokens | Control records | Input tokens | Edit hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 6/6 | 64.61 | 38 | 38 | 5764 | 0 | 83678 | 0 |
| optimized | 6/6 | 61.04 | 31 | 35 | 2249 | 35 | 92556 | 2 |
| batched | 5/6 | 67.88 | 34 | 36 | 2467 | 36 | 121808 | 1 |

Total time includes Pi startup, planning, tool execution, in-loop tests/recovery, final reply and independent behavior oracle. Nested compact-edit inference is included. Post-run artifact unittest reruns are outside measured task time. Failed tasks remain in totals and are not equivalent completed work.

## Observed batching

| Arm | Plans | Multi-operation plans | Maximum steps | Multi-tool responses | Tool errors including recovery | Blocked later steps |
|---|---:|---:|---:|---:|---:|---:|
| native | 0 | 0 | 0 | 0 | 0 | 0 |
| optimized | 0 | 0 | 0 | 0 | 0 | 0 |
| batched | 0 | 0 | 0 | 0 | 0 | 0 |

These are executed plan envelopes, not a promise that the entire task needs one inference. Plans themselves are generated; the existing compact-edit codebook is reused only inside compact_edit. Source discovery and final result interpretation may need further turns.

## Scenario totals

| Scenario | Native seconds / requests | Optimized single-step seconds / requests | Batched seconds / requests |
|---|---:|---:|---:|
| alias | 13.67 / 12 | 14.42 / 10 | 16.64 / 10 |
| properties | 19.70 / 12 | 17.51 / 10 | 21.90 / 12 |
| summary_bug | 31.23 / 14 | 29.11 / 15 | 29.33 / 14 |

## Failures

- 0-summary_bug-batched-1: behavior passed=True; requested-test integrity passed=False; no retry or removal.

## Controls and limits

Native is the ordinary tools API on the same patched vLLM service, not a separate unpatched server. It retains the previous harness settings including parallel_tool_calls=false. Optimized is the prior classification-first client with deterministic explicit-clause routing, tokenizer caches and directory guard. Batched uses the same inner codebook and tokenizer caches but bypasses the local single-clause dispatcher. It wraps standard Pi tools for sequential execution and blocks remaining steps after failure; successful earlier steps are not rolled back. Tool hooks remain active.

A offered execute_plan alongside individual tools. B replaces the supported individual outer choices with the plan envelope (1..8 operations) and final reply; unsupported custom tools remain separate. All actual runtime sources are archived per run. Prompts, grammar and control granularity differ, so this is an implementation comparison, not an isolated claim about classification speed.

Only a small handcrafted workload on a shared backend is covered. Counts, correctness, cold/warm timing and generated tokens are separate. Compile-only edit admission does not establish semantics; final behavior and test-integrity checks are independent. A tool error recovered inside an otherwise successful task remains visible in the batch profile.

`rows.jsonl`, `final-result.json`, raw Pi events, source snapshots and `batch-profile.json` contain the accounting. `verification.json`, `environment.json`, engine classification events and independent unittest reruns provide the post-run audit. Probe evidence in the separate batch-tools-execution-20260919 archive uses a mocked provider and real Pi tools; it is not a GPU performance result.

## Diagnostic interpretation

The optional batch choice was selected zero times. This run therefore does not measure actual batching. The batched-labelled arm also omitted requested new tests once (5/6 full tasks passed), correctly making the benchmark exit nonzero. The source snapshot predates the plan-envelope-only change tested separately in B; it is intentionally different from current bridge.py. All original records are retained.
