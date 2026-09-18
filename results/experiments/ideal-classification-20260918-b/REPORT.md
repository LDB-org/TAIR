# Ideal complete-action classification versus JSON generation

Finite named lookup among four complete, prebound write_file actions. Both arms see the same candidate table; candidate order is shuffled. Three output lengths, three repetitions each. Explicit profile selection removes open-ended planning and argument binding. This measures the ideal representation mechanism, not coding ability or a complete Pi Agent.

Each call has a fresh cache salt. Serial randomized interleaving; no retries. Shared four-sequence engine is unchanged. Candidate construction/tokenization are prepared offline and excluded; their timings are retained in manifest/plans. File application and exact read-back are checked locally. All formal rows, including failures, contribute to timing. One warm-up per arm is excluded and preserved.

Run A uses unconstrained JSON and exposed unwanted wrapper output. Run B adds a shape-only JSON Schema without forcing the correct name, path or content. Run A remains preserved; Run B is the main comparison.

| Nominal size | Generated tokens/call | Generation service s | Classification service s | Service ratio | Generation HTTP s | Classification HTTP s | Exact correct gen/class |
|---|---:|---:|---:|---:|---:|---:|---|
| 32 | 36.3 | 0.542 | 0.160 | 3.38x | 12.018 | 6.821 | 3/3 ; 3/3 |
| 128 | 92.3 | 1.181 | 0.151 | 7.81x | 10.136 | 8.130 | 3/3 ; 3/3 |
| 512 | 316.3 | 3.785 | 0.203 | 18.64x | 20.383 | 15.700 | 3/3 ; 3/3 |

All timing entries are arithmetic means. Service = scheduled-to-first-output + first-to-last-output, excluding initial queue wait. It includes prefill and later scheduling effects; it is not GPU kernel time. HTTP includes queue and transport, excludes offline preparation. Validated wall includes HTTP plus decoding/application/checks. Nominal sizes name the fixture scales, not exact character or token counts.

Classification generates zero argument tokens and returns one internal control ID per call. Every formal classification request is verified against V2 sampler-bypass audit events. Prompt/input lengths differ slightly due to output instructions. Long candidates increase prefill; this experiment does not establish general scaling to large codebooks, throughput, equal-quality coding, or end-to-end Agent speedup.

| Arm | Input tokens | Generated tokens | Controls | Mean queue s | Mean validated s |
|---|---:|---:|---:|---:|---:|
| generate | 5982 | 1335 | 0 | 12.044 | 14.179 |
| classify | 5946 | 0 | 9 | 9.733 | 10.217 |
