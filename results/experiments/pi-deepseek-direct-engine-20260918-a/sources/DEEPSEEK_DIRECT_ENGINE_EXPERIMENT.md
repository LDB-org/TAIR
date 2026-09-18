# DeepSeek: direct tool classification inside vLLM

This experiment patches the existing Yuesheng deployment to read option logits,
retain its KV cache, and then generate only the selected tool's argument JSON.
It is an experimental engine integration, not a production release or a complete
Pi agent execution benchmark.

## Result

Evidence: `results/experiments/pi-deepseek-direct-engine-20260918-a/`.
Nine tasks cover Pi's eight built-in tools plus `reply_user`, with two repetitions
per task and method, randomly interleaved with seed 20260921.

| Metric | Whole tool-call JSON | Direct classification + arguments |
| --- | ---: | ---: |
| Completed calls | 18/18 | 18/18 |
| Correct tool | 18/18 | 18/18 |
| Exact tool and arguments | 18/18 | 18/18 |
| Generated tokens, including termination | 504 | 336 |
| Internal classification control records | 0 | 18 |
| Median client latency | 0.6787 s | 0.6762 s |
| Sum of client latencies | 98.6073 s | 40.8502 s |

Generated tokens fell **33.3%**. Conservatively counting each internal control ID
as another output unit gives 354 versus 504, a **29.8%** reduction. These IDs use
vLLM's output transport but are obtained by direct candidate-logit argmax, not
by calling the normal sampler. They must not be silently omitted from accounting.

The latency medians are effectively equal. The shared deployment experienced
large queue fluctuations, including a 41.2-second whole-JSON request. **The sums
do not establish a speedup**, and this experiment does not establish stable
latency, throughput improvement, or production readiness.

An additional four-client mixed-concurrency check completed eight calls: direct
was **4/4 exact**, whole JSON was **3/4 exact**. The failed baseline reply was
`Done` instead of `Done.`; its JSON was valid. The strict acceptance command
therefore exited nonzero, and that failure is retained rather than retried away.
Its cause has not been isolated. Invalid candidate tables were rejected, a
one-token argument budget returned an error without a call, and the original
text, native tool-call, and real-image vision API canaries passed afterward.

## Exact backend and method

- Model directory: `DeepSeek-V4-Flash-Vision-Exp`; download metadata revision
  `6821d6ad3681a4b137b066b76094fa82ebd0a380`. Configuration and weight-index hashes
  are preserved; the entire weight set was not rehashed.
- vLLM: `0.28.1rc1.dev137+g5ab628dd1`; actual worker path is the V2 model runner.
- Container base image:
  `sha256:c0dec7f60c449fc4089134dcbc2b80462e9d39622fa33dba83dfb0b1d90987dc`.
- Existing six-GPU TP2 × PP3 deployment, DeepSeek FP8 quantization, FP8 KV,
  no speculative decoder, max sequences 4, batched token budget 1024.
- Temperature zero. Both arms use the same actual Pi schemas, closed against
  additional object properties. Maximum argument/completion length: 192 tokens.
- API benchmark clients load no model and allocate no CUDA GPU. They use the
  already distributed model service, rather than launching a new scorer.

The `/v1/openjev/toolcall` endpoint accepts tokenized classification input, a
candidate table, each candidate's deterministic continuation, and its schema.
The benchmark checks that every continuation extends the exact original token
prefix. Tool descriptions appear in the classification prompt; only the selected
schema appears in its continuation. The whole-JSON baseline receives all schemas,
so this is a comparison of complete approaches, not an isolated sampler ablation.

1. The V2 sampler hook directly gathers candidate logits and takes argmax.
   In mixed batches, classification rows are excluded from normal sampling;
   ordinary rows keep their own slot mappings and sampling state.
2. One internal control ID communicates the decision. The server chooses the
   corresponding continuation and argument grammar; generated text is not parsed
   to determine the tool category.
3. vLLM's streaming-input session retains the scheduler request and KV blocks.
   The uncomputed control output is discarded by the existing continuation path;
   the chosen label and schema instruction are injected as prefill input.
4. A necessary streaming fix updates both `max_tokens` and the structured-output
   state for the resumed request. XGrammar constrains argument generation, and
   the endpoint validates the finished JSON against the selected schema.
5. The server constructs the `{name, arguments}` wrapper. Truncated or invalid
   output returns an error and never becomes an executable tool call.

This retains one engine session, but is **not a single fused GPU kernel or an
uninterrupted scheduler step**. There is still a server-side decision callback,
another scheduling admission, and a continuation prefill. The forced continuation
tokens cost input computation even though they are not counted as generated
tokens. Argument keys and free-form values are still generated.

The generic V1 compatibility hook is also present in the patch. Its mixed-batch
behavior differs and was only unit-tested; the DeepSeek results concern V2 only.

## Failure found and fixed

The first live smoke test failed with `AssertionError: No free indices`.
Classification had succeeded and retained 499 computed tokens, but a paused V2
request still occupied a worker slot while waiting for continuation/grammar.
The scheduler could admit another request into the nominally available capacity.

The fix retires the classification request's **worker metadata** at the pause
boundary, without freeing the scheduler request or its KV blocks. The continued
request is re-added with its previous computed-token count and block table.
The failed `smoke-a` row is retained separately from successful `smoke-b` and the
complete measured run. It is not counted as a successful result.

Engine events record candidate readout, worker-slot retirement, and continuation.
`benchmarks/verify_deepseek_direct_engine.py` verifies matching request IDs,
candidate argmax, sampler bypass, identical KV block IDs across the boundary,
preserved computed-token counts, and the resumed argument limit/grammar.

## Scope and reproducibility

The tests generate calls; they do not execute Pi tools, build a scanner, or run a
complete agent loop. Nine short known tasks do not establish held-out task
accuracy, arbitrary-schema support, semantic safety, or sustained reliability.
Schema validity cannot guarantee the right tool, correct values, or authorized
actions. The original Pi harness has not yet been switched to this new endpoint.

Main files:

- `deploy/vllm_direct_tools.py`: engine helper and experimental API route.
- `deploy/install_vllm_direct_tools.py`: pinned-version patch installer and
  hash-checked rollback, with separate V2 and streaming-slot patch stages.
- `benchmarks/test_deepseek_direct_engine.py`: interleaved API benchmark.
- `benchmarks/accept_deepseek_direct_engine.py`: mixed-concurrency and ordinary
  API canaries, plus invalid-input and truncation checks.
- `tests/test_vllm_direct_tools.py`: sampler exclusion, slot retirement, and
  retained-cache/schema-transition tests.

The patch is installed in the existing container's writable layer. Restarting
that container retains it; recreating it from the base image does not. A private
deployment backup remains on the remote host and is deliberately excluded from
repository evidence. Source backups in the container are:

```
/opt/openjev-direct-backup-20260918-a
/opt/openjev-direct-backup-20260918-b
/opt/openjev-direct-backup-20260918-c
```

To roll back this exact installation, run the installer with `--rollback` and
`--backup` for **c, then b, then a**, followed by a container restart. The installer
checks current patched hashes before restoring files. The ordinary API routes
remain available alongside the experimental endpoint.

Re-run the benchmark against a compatible patched service with a **new** output
directory. Preserve rows, inputs, live version metadata, source snapshots, engine
events, and checksums. Do not update the repository's original headline results
from this small experiment.
