# Experimental early rejection of completed oversized arguments

`TAIR_STREAM_PLAN_BUDGET=1` enables an API-side streaming budget check. It is off by default and has not been deployed or benchmarked on the GPU service.

The scanner visits each newly received character once, tracks JSON containers and escaped strings, and identifies completed `first`, `steps[i].arguments`, and `rest[i].arguments` objects. Each completed argument is decoded and counted once using the same compact JSON serialization and tokenizer as the final budget check. An object exceeding 2,048 tokens raises the existing budget error immediately; the endpoint aborts the request, returns HTTP 422, and never returns an executable partial plan. The final schema validation and budget check remain authoritative for successful results. The 17,408-token total allowance and eight-child capacity are unchanged.

Errors additionally expose `stream_argument_tokens` keyed by child index. This can be a partial set and is not sampled-token attribution. `generated_argument_tokens` counts chunks actually received; an early abort has incomplete usage because engine work may be in flight. Do not report that count as exact total GPU consumption.

The optimization only avoids generation *after a completed oversized argument*. It cannot stop a string that never closes, does not enforce the eight-child limit early, and does not early-check a content-only reply. It does not fix the historical long tails without evidence that they contained a completed oversized argument. JSON with repeated member names is outside the experimental early-check contract: an earlier oversized occurrence is rejected even if a later occurrence would overwrite it in Python's JSON decoder. Keep this opt-in until compatibility with the deployed structured-output grammar and real workloads is verified.

Tests exercise one-character and larger chunk boundaries, Unicode, escaped quotes/backslashes, braces in strings, nested objects, reversed first/rest property order, exact 2,048-token limits, incomplete strings, abort before the next output chunk, consumed-chunk accounting, and eight individually valid children. They use an engine double and a character tokenizer: they establish control flow and contract preservation for these cases, not real GPU latency or BPE speedup. No extra model request or tool-catalog restriction is introduced.

## Pinned-tokenizer archived-output replay

`benchmarks/profile_stream_plan_budget.py` replays complete recorded plan responses from the live budget acceptance and two order probes, deduplicated by raw-output SHA-256. Ten unique plans passed at 1-, 32-, and 256-character chunk sizes, five repetitions each, with zero rejections and exact agreement with the final compact-argument BPE counts. The largest median local replay cost across these cases was approximately 3.4 ms. The tokenizer is manifest/hash checked; source hashes and individual measurements are in `STREAM_PLAN_BUDGET_PROFILE.json`.

This bounds the observed CPU overhead on these small archived samples only. Artificial character chunks are not recorded engine streaming boundaries. The replay does not measure saved generation, process contention, real abort latency, or the historical failed outputs, which were not retained. The experimental flag remains off.
