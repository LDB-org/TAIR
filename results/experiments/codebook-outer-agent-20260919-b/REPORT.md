# Full Agent outer-loop optimization: repeated run B (2026-09-19)

Two independent repetitions of three real Pi coding scenarios, each with a cold and warm round: 36 tasks total. Each arm starts a separate project and empty state per repetition/scenario. Warm rounds restore the original source and retain only runtime state, with a fresh Agent session. Arm order is interleaved using seed 921.

## Full task outcomes

| Arm | Completed correctly | Total seconds, all attempts | Inference requests | Generated tokens | Controls | Input tokens | Edit hits |
|---|---:|---:|---:|---:|---:|---:|---:|
| native | 12/12 | 130.62 | 78 | 11107 | 0 | 172029 | 0 |
| c4 | 11/12 | 144.39 | 75 | 5212 | 75 | 210366 | 0 |
| optimized | 12/12 | 128.32 | 71 | 4213 | 71 | 187656 | 4 |

Optimized total time is 1.8% below native and 11.1% below c4 in this run. All-attempt totals retain failures and their actual costs; an incomplete task is not equivalent completed work.

## Per scenario and repeat

| Scenario | Native seconds | c4 seconds | Optimized seconds |
|---|---:|---:|---:|
| alias | 29.39 | 35.53 | 30.08 |
| properties | 36.95 | 44.91 | 35.81 |
| summary_bug | 64.28 | 63.95 | 62.43 |

| Independent repetition | Native seconds | c4 seconds | Optimized seconds |
|---|---:|---:|---:|
| 1 | 65.54 | 71.04 | 64.02 |
| 2 | 65.08 | 73.35 | 64.29 |

| Round | Native seconds | c4 seconds | Optimized seconds |
|---|---:|---:|---:|
| Cold | 65.11 | 76.80 | 71.55 |
| Warm | 65.51 | 67.59 | 56.77 |

## Completed-pair comparison

- Optimized vs native: 12 mutually successful pairs; 128.32 vs 130.62 seconds (1.8% lower). All excluded failures remain in raw rows and the all-attempt table above.
- Optimized vs c4: 11 mutually successful pairs; 114.27 vs 131.93 seconds (13.4% lower). All excluded failures remain in raw rows and the all-attempt table above.

## Configuration and overhead

Native uses stock Pi tools via the standard chat-completions endpoint on the same patched vLLM service. c4 uses the expanded learned codebook with all outer-loop optimization flags disabled. Optimized enables batched explicit-clause routing after a successful source read, revision-bound tokenizer label/continuation caches, and directory-read redirection. Schema execution, preset edits and exact zero-model replay are disabled for all TAIR arms. Inner codebook candidates still go through classification with NONE/generation fallback.

| Client measure | c4 | Optimized |
|---|---:|---:|
| Tokenizer HTTP requests | 975.00 | 245.00 |
| Locally dispatched outer calls | 0.00 | 8.00 |
| Continuation-cache hits | 0.00 | 57.00 |
| Directory-read redirects | 0.00 | 10.00 |
| Measured preparation seconds | 36.95 | 30.21 |

Tokenizer HTTP calls are not inference requests. Preparation stages overlap with individual HTTP timings; their elapsed durations must not be summed with nested request durations. A local dispatch is not a zero-model edit. Cache initialization costs are included in cold rounds.

## Correctness and evidence

`rows.jsonl` and `summary.json` include final task-completeness decisions. The lower-level per-task `result.json` predates the added-test integrity check; use the separately saved `final-result.json` for the final verdict. A successful function oracle alone does not fulfill a request to add tests.

- Failed: repeat 1, summary_bug, c4, round 2; behavior oracle passed=True, original/additional test integrity passed=False. Files and events are retained; no silent retry.

Every final project has a separately recorded unittest rerun in `independent-unittest.json`. Engine classification evidence, tokenizer hashes, engine revision, unchanged service start time and source hashes are in `verification.json`, `engine-classification-events.jsonl` and `environment.json`. Worker event counts are not request counts. The post-run artifact audit is outside measured task time.

## Limits

This is a small handcrafted workload on a shared 6 x RTX 5090 backend, not a general coding benchmark or production throughput test. Native is not a separate unpatched server. Tool catalogs and provider prompts differ. The optimized configuration combines routing and transport improvements, so the end-to-end delta cannot be attributed solely to the classifier or learned codebook. Cold and warm tradeoffs and individual regressions are shown above. Compile-only admission does not prove semantic correctness; independent task oracles are applied afterward. Pinned continuation calibration is empirical for this deployed tokenizer/template.

Diagnostic A is retained separately, including its original incomplete aggregate and corrected aggregate. Its measurements are not merged with run B. No model reload, service restart or production release replacement was performed.

Post-run harness correction: the current harness also writes `final-result.json` itself and exits nonzero if a task fails or usage is incomplete. Run B used the archived harness; its process exit was zero despite the recorded c4 task failure. All runtime source snapshots match current code; the harness reporting-only difference is recorded explicitly.
