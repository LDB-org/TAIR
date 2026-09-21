# Withdrawn experiment: skip a classification with only one possible branch

The runtime experiment and its three dedicated tests have been removed after the free-content quality regression. Frozen implementations and all measurements remain available under `results/experiments/single-branch-*`; the component probe remains reproducible against the existing service. No server deployment occurred. The mechanism below describes the withdrawn implementation, not an available runtime flag.

`TAIR_SINGLE_BRANCH_DIRECT=1` was a server-side experiment, off by default. When the candidate table has exactly one entry, there is no choice to make. The API feeds `prompt_ids + continuations[0]` directly to structured generation with the selected schema and original output budget, instead of performing a one-control-token classification and a streaming pause/resume. Multiple candidates retain the original path. No tool catalog, candidate retrieval policy, or generated plan format changes.

The continuation already contains the assistant label and subsequent instruction. `bridge.continuation_tokens` derives it by removing the exact verified classification prefix from the fully tokenized conversation. Do not prepend another control ID: doing so would duplicate the label. This optimization preserves the generation input sequence; it does not remove the classification instructions from the prompt or promise fewer generated argument tokens.

The response keeps decision index zero for existing decoders, explicitly sets `selection_mode=single_branch`, `control_id=null`, and `logprobs=null`, and reports zero classification control records on success and failure. No measured classification confidence is fabricated. Generated tokens, budget validation, JSON/schema validation, error abort and incomplete-output rejection remain in place. The decision audit records the bypass mode. There is still one engine session, but only one streaming input.

In the current client, disabling first-tool classification with `PIJIT_FIRST_TOOL_CLASSIFICATION=0` and having no codebook candidates can leave only the general plan branch. The default client still includes native first-tool options, so this server flag alone does not accelerate that default cold path. When candidates are available, classification remains necessary. Neither client defaults nor the running server were changed for this experiment.

Endpoint tests verify the exact concatenated token sequence, a single input followed by iterator completion, unchanged generation budget, complete output and validation, zero classification usage on a length failure, abort, and preservation of the multi-candidate classification path. These are engine-double tests, not a deployment or GPU speed measurement. Real acceptance must verify the pinned engine accepts one-input streaming generation and compare cold/general requests with equal quality, input tokens, generated tokens, and total elapsed time before promotion.

## Live component comparison without deployment

`single-branch-direct-20260921-a` compares the existing fused endpoint with `/v1/completions` using exactly the same full generation token sequence and JSON schema. Three fixed exact-output fixtures (reply, small Python file, 32-line text file) run twice each, reversing arm order on the second repeat, after one warmup per arm. No returned tools execute. Concurrency is one, on the existing six RTX 5090 service, driver 610.43.02. Live vLLM version is `0.28.1rc1.dev137+g5ab628dd1`; API model ID is `/model`. The deployed custom module SHA-256 remains `0afc5142c518c5f723bb89709afacb407b2724d1fb5b8a9c56fd0181ceb3b661`, so the new bypass was not installed.

| Measured arm | Exact output | Total request wall time | Generated tokens | Classification records |
| --- | --- | --- | --- | --- |
| Singleton fused classification | 6/6 | 7.252 s | 500 | 6 |
| Direct structured completion | 6/6 | 6.342 s | 500 | 0 |

All six pairs have equal input and generated counts. Direct completion saves 0.138–0.172 seconds per request (median 0.149 seconds); total request time decreases 12.5% on these short fixtures. This is a fixed-overhead result, not reduced argument generation. Timing includes HTTP transport and each endpoint's processing; the fused endpoint also performs budget validation, so the difference is not isolated scheduler time. The direct endpoint is a proxy for the proposed mechanism, not acceptance of the new one-input streaming route or proof of complete Agent acceleration. Initial/final idle checks and raw requests/responses are frozen in the experiment; paired totals are in `SINGLE_BRANCH_DIRECT_EVALUATION.json`. Defaults and live service remain unchanged.

## Free-content replication: do not promote

`single-branch-open-content-20260921-a` removes the content enum and asks the model to implement UTF-8 local file I/O and JSONL deduplication. Both retain one constrained write step; code content is free. Independent subprocess checks test overwrite, empty/Unicode files, missing-file errors, reordered object keys, array order, original line whitespace, invalid JSON, and distinct `true`/`1`. Known-good implementations passed and no-op implementations failed the oracle controls. Two measured repetitions per task reverse arm order; warmups are excluded.

| Arm | Functional checks | Request time | Generated tokens |
| --- | --- | --- | --- |
| Singleton fused | 4/4 | 5.892 s | 450 |
| Direct completion | 2/4 | 6.544 s | 604 |

Both I/O pairs pass and direct saves approximately 0.15 seconds each. Both direct JSONL outputs instead use Python scalar equality in canonical hash keys, incorrectly merging `True` and `1`; fused outputs use canonical JSON strings and pass. These failures are preserved, with no repair requests or exclusion from totals. Different generated code and token counts mean the aggregate cannot isolate classification overhead. Request wall time excludes local program validation. Input token lists/schema are constructed identically for the intended generation context, but this alone does not establish equivalent internal engine state or explain the output divergence.

This small component test contradicts promotion based on the fixed-output speed result. The singleton optimization stays off; it is not established as a quality-preserving general improvement. See `SINGLE_BRANCH_OPEN_CONTENT_EVALUATION.json` and the frozen raw responses. No codebook or live service was modified.

A read-only inspection of the pinned live scheduler's `_update_request_as_session` confirms that resume discards the last sampled, uncomputed output token before appending the continuation, and replaces sampling parameters. This supports the intended prefix-plus-continuation construction; it does not establish identical numerical execution or explain why free-content decoding diverges between the two endpoints.

## Reversible split-boundary experiment

The live model generation config and server CLI have no penalty or sampling override explaining the difference. Constructing the pinned completion request's sampling parameters and comparing them with the custom route finds only `output_kind` (FINAL_ONLY versus DELTA) and `skip_clone` (true versus false) differences. This is a parameter-construction audit, not a dump of live per-request engine state.

The probe now accepts `--split-shift`: a singleton forced classification can be moved inside the token sequence, because its sampled control is discarded before continuation. This is a diagnostic operation, not a change to production prompts. Archived requests confirm that moving the boundary preserves every full input token, schema and candidate ID.

For the JSONL fixture, the original 76-token classification prefix produces correct 148-token code twice. Moving the boundary forward 32 tokens (108-token prefix, same 229-token complete input) produces the incorrect 225-token code twice. Restoring the original boundary produces the correct 148-token code twice again. Direct completion remains incorrect across all six measured repetitions in these three runs. Source hashes are retained in `SINGLE_BRANCH_SPLIT_AUDIT.json`; full results are frozen in `single-branch-split-shift-20260921-a` and `single-branch-split-restore-20260921-a` alongside the original run. I/O passes throughout.

This reversible result supports sensitivity to the split execution path, rather than an intrinsic quality benefit of a forced single-option classification. It does not identify the exact floating-point, attention, cache, or scheduling mechanism. Do not tune the boundary to this answer or count the original passing boundary as a general correctness guarantee. The optimization still needs broader functional evaluation; no default or live deployment was changed.
