# Parallel capability negotiation

2026-09-21. The client can overlap the fresh server capability GET with tokenization and classification-label preparation using `PIJIT_PARALLEL_CAPABILITIES=1`. It waits for all results before inference; query failure prevents inference, unsupported servers retain the legacy 2048-token plan budget. The existing serial preparation switch stays serial. Capability caching is independent and disabled in this experiment. Default remains off.

## Component evidence

`results/experiments/parallel-capabilities-profile-20260921-a` uses the real Yuesheng capability endpoint and pinned local tokenizer. Inference is intercepted locally; no GPU generation or tools execute. Both scheduling paths run the complete generic-plan client preparation and validate a mocked reply. Twenty-two calls (first pair separately, then ten randomized pairs) produced identical SHA-256 hashes of the complete inference payload, including token IDs, schemas and budgets.

Warm median client preparation/decode time: serial 295.524 ms, parallel 251.280 ms, a 44.244 ms reduction (15.0% of this component). First observations: serial 281.155 ms, parallel 280.862 ms. These share a process and tokenizer/label caches; they are not independent cold-process measurements. Median capability durations were 231.757 and 227.653 ms respectively. The warm preparation work is small, limiting possible overlap gains.

With overlap enabled, `generation_preparation` includes waiting for capability negotiation. It overlaps the capability stage; adding them would double-count time. No generated-token savings are expected from scheduling, and none are claimed.

## End-to-end evidence

`results/experiments/parallel-capabilities-ablation-20260921-a`: three tasks (JSONL creation, JavaScript changed requirements, JSON field edit), each run under native Pi, ordinary plan, and parallel negotiation plan. Existing Yuesheng six RTX 5090 service, Pi 0.85.1; one task at a time; shuffled arm order seed 731; initially empty isolated books, both plan arms reuse disabled, same local tokenizer. Bash argv is disabled to isolate scheduling. Service not restarted and user codebook untouched.

| Arm | Independent checks | Total wall seconds | Generated tokens | Logical input tokens | Requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native | 3/3 | 29.310 | 2908 | 35695 | 13 | 0 | 0 |
| Ordinary plan | 3/3 | 26.790 | 1908 | 29604 | 8 | 8 | 1 |
| Parallel capabilities | 3/3 | 31.650 | 2140 | 45021 | 11 | 11 | 4 |

All nine saved artifacts passed independent rechecks, with complete usage and no timeout. The parallel arm was 18.1% slower than ordinary plan overall. JSONL and JSON-edit times were slightly lower, but JavaScript took 17.535 versus 11.988 seconds: one shell quoting failure followed by three missing-module failures from a temporary test file with an incorrect relative import. This dominates the small local overlap benefit. Variable model output means these time/token differences cannot be causally assigned to capability scheduling; the fixed-input component comparison is the evidence for unchanged payloads and local savings.

Retain as a default-off experiment, not a proven end-to-end improvement. Prioritize eliminating redundant recovery calls over claiming small preparation savings as overall acceleration.

Validation: 553 tests passed, including event-synchronized overlap (not timing-only assertions), true/legacy budget propagation, trace context propagation and query-failure rejection before inference. Frozen archives verified separately; post-run service health and queue checked. See the JSON report for full metrics and component samples.
