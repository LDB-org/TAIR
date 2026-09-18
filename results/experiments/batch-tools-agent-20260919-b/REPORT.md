# Multi-operation Agent experiment (batch-tools-agent-20260919-b)

Real Pi 0.85.1 on the existing 6 x RTX 5090 service. Three scenarios: CLI properties, alias, and a function fix with requested new tests. Independent cold/warm pairs restore source and keep only per-arm runtime state. Fresh Agent sessions, interleaved arm order, no benchmark retries.

## Full task comparison

| Arm | Passed/tasks | Total seconds | Outer model requests | All inference requests | Generated tokens | Control records | Input tokens | Edit hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 12/12 | 125.83 | 76 | 76 | 10997 | 0 | 166518 | 0 |
| optimized | 11/12 | 129.09 | 61 | 69 | 4576 | 69 | 180299 | 4 |
| batched | 12/12 | 117.21 | 40 | 43 | 6716 | 43 | 127174 | 1 |

Total time includes Pi startup, planning, tool execution, in-loop tests/recovery, final reply and independent behavior oracle. Nested compact-edit inference is included. Post-run artifact unittest reruns are outside measured task time. Failed tasks remain in totals and are not equivalent completed work.

## Observed batching

| Arm | Plans | Multi-operation plans | Maximum steps | Multi-tool responses | Tool errors including recovery | Blocked later steps |
|---|---:|---:|---:|---:|---:|---:|
| native | 0 | 0 | 0 | 0 | 0 | 0 |
| optimized | 0 | 0 | 0 | 0 | 0 | 0 |
| batched | 28 | 28 | 6 | 28 | 35 | 24 |

These are executed plan envelopes, not a promise that the entire task needs one inference. Plans themselves are generated; the existing compact-edit codebook is reused only inside compact_edit. Source discovery and final result interpretation may need further turns.

## Scenario totals

| Scenario | Native seconds / requests | Optimized single-step seconds / requests | Batched seconds / requests |
|---|---:|---:|---:|
| alias | 28.78 / 24 | 32.41 / 20 | 28.89 / 12 |
| properties | 32.92 / 24 | 36.36 / 20 | 35.97 / 15 |
| summary_bug | 64.13 / 28 | 60.32 / 29 | 52.35 / 16 |

## Failures

- 0-summary_bug-optimized-1: behavior passed=True; requested-test integrity passed=False; no retry or removal.

## Controls and limits

Native is the ordinary tools API on the same patched vLLM service, not a separate unpatched server. It retains the previous harness settings including parallel_tool_calls=false. Optimized is the prior classification-first client with deterministic explicit-clause routing, tokenizer caches and directory guard. Batched uses the same inner codebook and tokenizer caches but bypasses the local single-clause dispatcher. It wraps standard Pi tools for sequential execution and blocks remaining steps after failure; successful earlier steps are not rolled back. Tool hooks remain active.

A offered execute_plan alongside individual tools. B replaces the supported individual outer choices with the plan envelope (1..8 operations) and final reply; unsupported custom tools remain separate. All actual runtime sources are archived per run. Prompts, grammar and control granularity differ, so this is an implementation comparison, not an isolated claim about classification speed.

Only a small handcrafted workload on a shared backend is covered. Counts, correctness, cold/warm timing and generated tokens are separate. Compile-only edit admission does not establish semantics; final behavior and test-integrity checks are independent. A tool error recovered inside an otherwise successful task remains visible in the batch profile.

`rows.jsonl`, `final-result.json`, raw Pi events, source snapshots and `batch-profile.json` contain the accounting. `verification.json`, `environment.json`, engine classification events and independent unittest reruns provide the post-run audit. Probe evidence in the separate batch-tools-execution-20260919 archive uses a mocked provider and real Pi tools; it is not a GPU performance result.

## Observed recovery and follow-up

The batch arm recorded 11 actual tool failures (7 missing-path reads and 4 empty-oldText edits) and 24 later steps blocked by fail-stop handling. It recovered and passed all 12 complete tasks; recovery time is included. Prompting alone did not prevent speculative operations whose inputs required earlier read results. This is a reason to keep the feature experimental, not evidence that arbitrary plans are semantically safe.

After B, jsonschema import was moved into batch validation so disabled mode and replies do not pay its startup cost. Current bridge.py therefore differs from this snapshot only in import placement. Run C tests that final implementation separately. Other runtime sources match.
