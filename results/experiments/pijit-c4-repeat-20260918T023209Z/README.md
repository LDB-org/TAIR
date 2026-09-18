# C4 repeated paired test — 2026-09-18

Three independent cold-start repeats; four consecutive workers-default edits per
repeat (6, 8, 10, 12), randomized paired order. Baseline is C1–C3 generation with
codebook disabled; C4 keeps its existing probability >= 0.95 / margin >= 3 gate.
Each pair receives identical input source. Both arms pass the same exact-AST and
behavior checks; those checks run before admission and are included in timing.
This is a synthetic nested-edit test, not native Pi or full Agent throughput.

| Metric | Generation | C4 |
| --- | ---: | ---: |
| Correct edits | 12/12 | 12/12 |
| Inference requests | 12 | 21 |
| Input tokens | 5832 | 6966 |
| Generated argument tokens | 126 | 128 |
| Classification controls | 12 | 21 |
| Total client wall seconds | 19.282 | 71.070 |
| Median edit seconds | 1.274 | 1.979 |
| Successful cache hits | n/a | 0/12 (0/9 with candidates) |

All nine cache classifications selected the correct bound edit, but the gate
rejected every one. The scores were approximately 0.7773 (8), 0.6792 (10), and
0.8176 (12), with margins 1.25, 0.75, and 1.50 respectively. All subsequently
fell back to generation. No parameters were saved by reuse. C4 added nine
inference requests, 1,134 input tokens, nine control records, and two generated
tokens (output formatting may vary even when ASTs match).

Cache lookup/classification (including its tokenization and network) took a
median 0.765 seconds; total 28.363 seconds.
The largest cache-classification interval was 22.300 seconds.

## Per-repeat wall seconds (all attempts retained)

| Repeat | Generation | C4 |
| --- | ---: | ---: |
| 0 | 9.340 | 56.378 |
| 1 | 4.894 | 7.266 |
| 2 | 5.048 | 7.425 |

Shared-service load was not isolated. A live snapshot saw four running requests
and one waiting request. The total wall-time ratio is an observation, not a
stable slowdown factor or causal attribution to C4. Even the two less variable
repeats remain tiny samples. Cache preparation and HTTP stages are nested in
cache-classification time; do not add them twice. Error accounting is complete
for this run; there were no failed calls or retries.

## Engine and evidence verification

All 33 inference requests have matching V2 sampler-bypass events. All 24
classification-to-generation requests retained their computed prefix and KV
block IDs across continuation. The nine cache-only classifications have no
argument continuation. See engine-events.jsonl and engine-checks.json.

Backend: vLLM 0.28.1rc1.dev137+g5ab628dd1. Download metadata revision:
6821d6ad3681a4b137b066b76094fa82ebd0a380. Config, tokenizer, weight-index and
engine-helper hashes were captured; full weight bytes were not rehashed.
Source snapshots and their hashes, exact rows and arm totals are in comparison/.

A historical-session recheck also verified all six original calls' prefix/KV
continuation events. The earlier absence report was a matching error: worker
request IDs have a suffix and must be matched by request ID plus '-'. The events
were retained. This establishes reuse within each classification/generation
call, not tokens or time saved against a measured native baseline.

No gate thresholds were changed. These positive fixtures do not calibrate a
lower threshold; false-acceptance testing remains necessary before changing
admission policy. Archived earlier experiments were not modified.
