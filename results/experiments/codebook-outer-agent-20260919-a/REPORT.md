# Full Agent outer-loop optimization: diagnostic A (2026-09-19)

18 real Pi tasks, three scenarios, one independent cold/warm pair per arm. Every task passed the behavior oracle, original-test integrity checks, and a separate rerun of the resulting unittest suite. Usage is complete.

| Arm | Tasks passed | Total seconds | Inference requests | Generated tokens | Controls | Input tokens | Edit hits |
|---|---:|---:|---:|---:|---:|---:|---:|
| native | 6/6 | 69.81 | 39 | 6112 | 0 | 86972 | 0 |
| c4 | 6/6 | 71.32 | 37 | 2524 | 37 | 101576 | 0 |
| optimized | 6/6 | 62.38 | 35 | 2411 | 35 | 92217 | 2 |

The optimized configuration enables explicit-clause batching, pinned tokenizer label/continuation caches, and directory-read recovery. It keeps the learned classification-first codebook and generation fallback; schema execution, preset edits and zero-model replay remain disabled.

Optimized total wall time is 10.6% below native and 12.5% below c4 in this diagnostic. Alias cold/warm combined is slightly slower than native; this is not universal acceleration. Tokenizer HTTP requests fall from 481 to 122. These HTTP counts are separate from inference and token usage.

Native is the ordinary tools endpoint on the same patched vLLM service, not a separate unpatched binary. Timing includes Pi startup, the full tool loop, recovery, final reply, and independent final behavioral checking. Subsequent unittest reruns used for artifact verification are outside the measured timing.

## Evidence and correction

- `rows.jsonl` contains every task and unchanged original metrics.
- `summary.json` is retained verbatim: its fixed arm registry accidentally omitted optimized.
- `corrected-summary.json` aggregates all observed arms from the same rows. The shared summarizer now iterates observed arms.
- `verification.json` checks all 72 classification requests against sampler-bypass engine events. Engine worker events are not request counts.
- `profile-summary.json` separates cases, cold/warm rounds and preprocessing.
- `independent-unittest.json` contains all 18 post-run suite results.
- The runtime source snapshots match the tested implementation. Two harness snapshots predate only the aggregation fix and expanded snapshot collection; these mismatches are explicitly recorded.

Three handcrafted scenarios on a shared 6 x RTX 5090 service, compile-only codebook admission, differing provider prompts/tool catalogs, and only one repetition limit the conclusion. See run B for independent repeated measurements. Production service start time remained 2026-09-18T05:44:43.699377485Z.
