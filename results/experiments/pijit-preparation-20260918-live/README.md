# Live preparation optimization comparison

18 real Pi tasks: three interleaved arms, three repeats, defaults 4 -> 6 -> 8.
All 18 completed with complete usage accounting and passed the independent AST
and behavior oracle, including explicit `--workers` overrides. Each repeat starts
with a cold label cache. No retries or outlier removal.

| Metric | Previous preset preparation | Optimized preset preparation | Native Pi |
| --- | ---: | ---: | ---: |
| Tasks passed | 6/6 | 6/6 | 6/6 |
| Median preparation per task, seconds | 1.5489 | 0.9978 | Not instrumented |
| Tokenizer HTTP requests | 162 | 102 | Provider-internal |
| Model requests | 18 | 18 | 18 |
| Generated tokens | 258 | 258 | 1380 |
| Classification control records | 18 | 18 | 0 |
| Input tokens | 33594 | 33542 | 30922 |
| Median validated task time, seconds | 21.1816 | 31.8645 | 10.8578 |
| Total validated task time, seconds | 117.8354 | 226.5610 | 74.9635 |

Preparation median decreased 35.6%, but the end-to-end task median increased
50.4%. This run does **not** demonstrate end-to-end acceleration or parity with
native Pi. The shared server had concurrent traffic; the recorded load snapshot
and all slow samples are retained. The optimized arm accumulated 206.41 seconds
before classified results versus 93.74 seconds in the previous arm. These server
timers include queueing, prefill and scheduling, not just classification compute.
Continuation-stage totals were 5.66 versus 6.02 seconds, also not pure decode time.
The data do not establish why the scheduling/waiting differed between arms.

`preset_before` uses the original sequential tokenization waves and no label
cache. `preset` overlaps the independent waves and caches validated labels under
an explicit deployed-tokenizer hash identity. Tools, edit checks, and task prompts
are otherwise identical. Contexts contain changing request IDs and separate
project paths, so full live input token counts are close but not identical.
Native Pi uses the stock provider/read/edit tools on the same patched backend;
this is not an unpatched-vLLM deployment comparison.

## Fixed-input remote tokenizer check

`tokenization-only/` contains 10 interleaved pairs using identical synthetic
inputs and real remote `/tokenize` calls. Inference is intercepted and is **not**
executed in this separate check. Every assembled inference payload matched
exactly (asserted and hashed). The first optimized call starts cold.

Median preparation: **0.4535 -> 0.2832 seconds**, down **37.5%**.
Tokenizer requests: **90 -> 54**; optimized label-cache hits: **9/10**.
These are actual remote tokenization timings, not a simulated network delay or
an end-to-end GPU inference benchmark.

## Evidence and boundaries

- `manifest.json` and `sources/`: task controls and source snapshots.
- `rows.jsonl`, `summary.json`, `timing-breakdown.json`: complete task accounting.
- Per-task events, native inference traces, source before/after, and metrics.
- `backend-identity.json`: live engine/model/tokenizer hashes and model revision.
- `engine-events.jsonl`, `engine-checks.json`: request-correlated engine evidence.
- `cache-exclusion.json`: disposable tokenizer cache paths moved outside the
  archive after both experiments; hit/request telemetry remains in the records.

No service restart or vLLM patch change was performed. Preparation improvements
do not remove shared-engine queueing. Labels are cached only when the operator
provides `PIJIT_TOKENIZER_REVISION`; update it whenever the tokenizer changes.
