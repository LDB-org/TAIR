# Diagnose exhausted structured-output generations

2026-09-21. Two ordinary-plan requests in `first-tool-reuse-ablation-20260921-a` returned HTTP 500 after 17408 generated tokens, followed by cancelled retries at the task deadline. Existing client records establish the consumed budget but do not retain generated output structure. They cannot establish whether output never completed its JSON value, emitted trailing whitespace, or failed for another reason.

A read-only container inspection confirmed that the live API module hash is `0afc5142c518c5f723bb89709afacb407b2724d1fb5b8a9c56fd0181ceb3b661`, exactly matching that experiment's frozen source. The generation loop starts at line 224 and `measure_plan_arguments` is called at line 253, outside the loop. The 2048-token subtool rule is therefore a compact-JSON check after generation, not an incremental generation stop. This is the existing documented contract, not evidence that those particular failures contained oversized child arguments.

The repository now adds `generation_diagnostics` to engine error responses. It reports character count, trailing whitespace count, whether a complete JSON value/document exists, its end offset, unconsumed character count, and JSON parser error position/message or parser failure type. It does not include generated content. Successful responses and budget enforcement are unchanged. The bridge retains the structure under `engine_generation_diagnostics`, alongside the already added engine request ID, wire decision index and finish reason.

The distinction matters before choosing a remedy: a valid completed value followed by whitespace may need a different stopping rule from an unterminated argument string. Neither early completion nor streaming per-child budget enforcement is implemented by this diagnostics change. No latency improvement is claimed.

Tests cover an incomplete string, a completed object followed by 10000 spaces, non-whitespace trailing data, and a simulated length-ended engine response. The endpoint still returns an error, aborts that request, preserves incomplete usage and never exposes an executable call. The client test confirms all diagnostic fields survive its HTTP error path. Full suite: 593 passed.

The server change is **not deployed**. Live inspection confirmed the diagnostic helper is absent from the running module. No model restart, weight change or GPU inference was performed for this change. Verification details: [GENERATION_DIAGNOSTICS_VERIFICATION.json](GENERATION_DIAGNOSTICS_VERIFICATION.json).
