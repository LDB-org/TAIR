# Schema-directed tool-call experiment

This separate exploratory experiment does not change Phase 1 claims. It compares
two readout protocols using one frozen causal model, BF16, one CUDA GPU, batch
size one, and greedy text decoding. It constructs calls but never executes tools.

- **JSON:** generate the entire compact call, parse it, then validate its shape.
- **Hybrid:** classify the tool name and priority using exact single-token option
  labels, then generate only the raw `content` string. Python constructs the
  object and serializes it. Selected fields enter subsequent model context.

The same incremental Transformers forward loop powers both paths. The hybrid
path retains its KV cache across field-instruction turns and checks that every
new prompt extends the exact cached token prefix. Neither path shares cache
across requests. Both paths receive a warmup, then execution order alternates
across cases and repeats. Timing includes tokenization, model execution, CPU
readout, validation, and serialization; excludes loading and warmup.

This prototype uses Qwen ChatML's `im_end` turn boundary. It appends turns
without re-rendering earlier assistant messages: the Qwen template otherwise
removes earlier empty thinking blocks and invalidates the cached token prefix.

## Local reproduction

From the repository root, in the environment installed with `pip install -e
'.[test]'`:

```bash
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python benchmarks/schema_toolcall.py \
  --model /home/Kei/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/snapshots/c1899de289a04d12100db370d81485cdf75e47ca \
  --revision c1899de289a04d12100db370d81485cdf75e47ca \
  --repeats 2 --max-tokens 128 \
  --output results/experiments/schema-toolcall-qwen06b-4070-new.json
```

Use a new output path for every run. Reports retain all case definitions, the
fixed schema, rendered prompts and hashes, raw text, constructed calls, exact
match checks, token/forward counts, timing, environment metadata, and runner
hash. This is a two-tool schema subset, not a general JSON Schema compiler.

## Observed local results (2026-09-18)

Hardware: WSL, RTX 4070 12 GiB; approximately 3 GiB was already in use by the
desktop/other activity. Qwen3-0.6B revision
`c1899de289a04d12100db370d81485cdf75e47ca`, BF16, PyTorch 2.10.0,
Transformers 5.17.0. The second run peaked at 1203 MiB of PyTorch-allocated
GPU memory, excluding other applications, driver allocations, and reserved
memory. No new model weights were downloaded.

| Prompt version / path | Median seconds | Valid complete calls | Exact expected calls | Correct tool + priority |
|---|---:|---:|---:|---:|
| v1 JSON | 0.914 | 10/12 | 8/12 | 10/12 |
| v1 hybrid | 0.145 | 12/12 | 0/12 | 6/12 |
| v2 JSON | 0.925 | 10/12 | 6/12 | 10/12 |
| v2 hybrid | 0.150 | 12/12 | 0/12 | 6/12 |

Each row represents six cases repeated twice, not twelve independent cases.
After observing v1 failures, v2 explicitly distinguished TASK data from the
CURRENT STEP and repeated the task at field transitions. It did not fix the
hybrid failures. This is exploratory prompt iteration, not a held-out test.

The hybrid frequently selected `A` and generated `A` as the text value. Its
short wrong answers reduce generation time. **These measurements do not
establish a useful speedup or equivalent semantic quality.** The engine kept
output shapes valid, but the model did not reliably perform the intended
classification/generation protocol. The JSON path failed parsing on the
call-like-data case in both versions.

For v1, a full-prefill audit recomputed the two classification distributions
for all six cases using the saved exact prompts, `use_cache=False`, and the same
model. All 12 choices agreed with the incremental path. The maximum absolute
probability difference was 0.00166625. This checks the observed discrete-choice
failure against fresh forward passes; it is not proof of cache correctness for
all inputs or generated strings.

Evidence:

- [v1 report](../results/experiments/schema-toolcall-qwen06b-4070-v1.json)
- [v1 runner snapshot](../results/experiments/schema-toolcall-runner-v1.py)
- [v1 cache audit](../results/experiments/schema-toolcall-cache-audit-v1.json)
- [v2 report](../results/experiments/schema-toolcall-qwen06b-4070-v2.json)
- [v2 runner snapshot](../results/experiments/schema-toolcall-runner-v2.py)

The cached 0.6B model is sufficient to exercise mechanics, but these results do
not qualify it as a reliable tool caller. Before engine/plugin work, test a
stronger small instruction model, expand held-out cases, and compare against
schema-constrained JSON at matched quality. Additional model weights were not
fetched in this experiment.

## Follow-up: larger model and same-engine constrained baseline

The follow-up downloaded Qwen3-1.7B at immutable revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Its safetensors total
4,063,515,592 bytes. No model weights are included in the repository.

On the original six development cases, the unchanged v2 hybrid protocol still
scored 0/12 exact calls with this larger model. A field-specific prompt variant
then separated evidence from the current instruction and described the two
tool operations explicitly. It scored 0/6 exact calls on those same development
cases. This variant was frozen before evaluating the twelve new cases in
[`schema-toolcall-heldout12.jsonl`](../benchmarks/data/schema-toolcall-heldout12.jsonl),
SHA256 `cc57301364a7a8d764c1cca51d6e69e233abdb178533d90a1a853ab0bc822beb`.
No prompt changes were made in response to those twelve cases.

The vLLM runner compares three paths in the **same engine**: unconstrained JSON,
JSON constrained by the complete schema, and the field-specific hybrid. The
hybrid uses a one-token allowed-ID request for each discrete selection and
generates only the text field. This is an equivalent constrained greedy slot
selection, not a custom classification head or plugin. The engine's automatic
prefix cache is cleared before each independent call, outside timing, and can
be reused between the hybrid's three requests. Thus no cross-case or
cross-repeat prefix-cache advantage is retained.

### Qwen3-1.7B, twelve frozen cases repeated twice

| vLLM path | Median seconds | Valid complete calls | Exact expected calls | Correct tool + priority |
|---|---:|---:|---:|---:|
| JSON | 0.569 | 22/24 | 20/24 | 22/24 |
| Schema-constrained JSON | 0.564 | 24/24 | 18/24 | 22/24 |
| Hybrid fields | 0.261 | 24/24 | 0/24 | 10/24 |

The schema baseline eliminates the observed malformed shapes without requiring
the new hybrid protocol. It does not guarantee correct values. The hybrid's
shorter time remains unusable as a speed claim because semantic quality is
unequal. This result concerns the tested letter-selection protocol and prompts;
it does not establish that all classification/generation architectures fail.

Independently scoring the three fields clarifies the failure: hybrid fields got
18/24 tool names, 14/24 priorities, and only 2/24 exact text values right. Typical
text errors were extra wrapping quotes, omitted punctuation, copying the whole
request, or retaining JSON escape sequences. Schema-constrained JSON got 22/24
tool names, 24/24 priorities, and 18/24 exact text values right. Strict exact
matching is intentional for a tool argument; these are not all meaningless
answers, but they do not satisfy the supplied string-copy contract.

The original 0.6B model also reproduced the hybrid failures on vLLM: 0/6 exact
calls on development cases, versus 3/6 for both JSON paths. This is evidence
against attributing the original failure solely to the Transformers loop.

### Local vLLM compatibility and measurement scope

The existing isolated vLLM environment is version 0.28.0, with its own PyTorch
and Transformers versions recorded in each report. This differs from the
repository's Transformers-only environment; compare the three vLLM paths
against each other, not as an isolated backend speed comparison to Transformers.

On this WSL host, the default V2 model runner failed with `UVA is not available`.
Setting `VLLM_USE_V2_MODEL_RUNNER=0` selected the existing legacy runner. Its
FlashInfer sampler then failed because `nvcc` and `/usr/local/cuda` were absent;
`VLLM_USE_FLASHINFER_SAMPLER=0` selected the native sampler. No vLLM source or
system CUDA installation was modified. Runs use eager execution, batch one,
4096-token maximum context, BF16, and a 128-token output cap. They do not measure
CUDA-graph-optimized production throughput. Schema/kernel warmup occurs before
the recorded measurements.

```bash
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
VLLM_WORKER_MULTIPROC_METHOD=spawn VLLM_USE_V2_MODEL_RUNNER=0 \
VLLM_USE_FLASHINFER_SAMPLER=0 \
/home/Kei/projects/ldb-gpu-acceptance-20260908/.venv-vllm/bin/python \
  benchmarks/schema_toolcall_vllm.py \
  --model /home/Kei/.cache/huggingface/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --cases benchmarks/data/schema-toolcall-heldout12.jsonl \
  --protocol fields --repeats 2 --output results/experiments/new-vllm-run.json
```

Follow-up evidence:

- [1.7B original protocol, development](../results/experiments/schema-toolcall-qwen17b-development-v2.json)
- [1.7B field prompts, development](../results/experiments/schema-toolcall-qwen17b-development-fields-v1.json)
- [0.6B vLLM cross-check](../results/experiments/schema-toolcall-vllm-qwen06b-development-v1.json)
- [1.7B vLLM frozen-case comparison](../results/experiments/schema-toolcall-vllm-qwen17b-heldout-fields-v1.json)
- [vLLM runner](../benchmarks/schema_toolcall_vllm.py)

## Qwen3-4B frozen comparison

The unchanged 12 held-out cases and field protocol were run twice per path on
Qwen/Qwen3-4B revision `1cfa9a7208912126459214e8b04321603b3df60c`, on the
same RTX 4070 12GB WSL host. These are 12 unique cases, not 24 independent
quality samples. No protocol tuning was performed on these results.

| Path | Median seconds | Valid shape | Exact call | Correct tool + priority | Output tokens, total |
| --- | ---: | ---: | ---: | ---: | ---: |
| JSON | 0.740 | 24/24 | 22/24 | 22/24 | 652 |
| JSON + schema | 0.745 | 24/24 | 18/24 | 22/24 | 672 |
| Hybrid fields | 0.400 | 24/24 | 8/24 | 22/24 | 304 |

Hybrid elapsed time was 46.3% lower than the schema baseline, with 54.8% fewer
output tokens, but correctness was substantially lower. This is **not a
matched-quality speedup**. Its tool, priority, and exact content scores were
22/24, 24/24, and 10/24 respectively. Frequent failures copied the instruction
into the query or retained escaped backslashes/Unicode instead of literal text.
Case h09 selected search_docs even though that name appeared inside text meant
for a reply. Host assembly preserves syntax; it cannot guarantee correct routing.
All three paths misrouted that case in both repeats.

The hybrid uses three vLLM requests per call (72 total), versus one for each
JSON path (24 total). This is a Python protocol prototype using restricted
single-token selection and host serialization, not an integrated vLLM plugin or
a separately trained classification head. Prompt processing and all three
requests are included in elapsed time. Output-token counts include the two
classification tokens per hybrid call and generated EOS tokens.

The 4B run uses BF16, eager execution, one sequence, a 1024-token context,
256 maximum batched tokens, and an explicit 256MiB KV cache. The automatic
memory budget failed twice during initialization (estimated available KV
memory -0.34GiB); neither failed attempt produced measured rows. An explicit
cache allocation completed successfully. These settings differ from the 1.7B
run, so cross-model latency changes do not isolate model size. Prefix caching
is reset before each independent call and retained between hybrid steps.

Reproduce with the same environment variables and vLLM interpreter above:

```bash
# Use a fresh output path; existing benchmark evidence must not be overwritten.
python benchmarks/schema_toolcall_vllm.py \
  --model /home/Kei/.cache/huggingface/hub/models--Qwen--Qwen3-4B/snapshots/1cfa9a7208912126459214e8b04321603b3df60c \
  --revision 1cfa9a7208912126459214e8b04321603b3df60c \
  --cases benchmarks/data/schema-toolcall-heldout12.jsonl \
  --protocol fields --repeats 2 --gpu-memory-utilization 0.75 \
  --max-model-len 1024 --max-batched-tokens 256 \
  --kv-cache-memory-bytes 268435456 \
  --output results/experiments/new-qwen4b-run.json
```

[Row-level report](../results/experiments/schema-toolcall-vllm-qwen4b-heldout-fields-v1.json)
contains exact prompts, outputs, settings, revisions, and source hashes.
The next useful experiment is protocol adaptation/training evaluated on new
frozen cases, with matched correctness as the speed acceptance criterion.

## Interpretation boundaries

The initial six development cases and subsequent twelve frozen routing/copy
cases test the mechanism, not general agent ability.
Two cases contain quoting/backslash and call-like text. Structural validity,
correct tool/priority selection, and exact content correctness are separate
metrics. Repeats do not add independent quality samples.

EOS ends each generated string. Hitting the token cap rejects the entire call;
it does not silently submit a truncated value. Python serialization keeps
call-like text inside its field, but neither this nor classification prevents
wrong decisions or establishes execution safety. No dedicated protocol tokens
or protocol training are used. This does not establish reliable control flow
for arbitrary models, schemas, nested objects, or adversarial inputs.

The initial JSON baseline is unconstrained; follow-up vLLM runs additionally
include a schema-constrained baseline. The experiment does **not** show
matched-quality superiority to structured outputs, speculative decoding, or
other serving engines. Hybrid field prompts add prefill work; their cost is
included. Long free-text fields still require autoregressive decoding.

## Engine choice

Start with this small Transformers experiment to inspect raw logits and exact
cache transitions. For a stronger baseline, compare against vLLM's existing
[structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/).
Its [custom logits processors](https://docs.vllm.ai/en/latest/features/custom_logitsprocs/)
can modify the candidate distribution without patching vLLM itself. A full
typed-object protocol would additionally need field-state management,
completion/cancellation rules, context updates, and object/event output; a
logits processor alone is not that protocol.

## Later baseline qualification

The v2 investigation reproduced a local XGrammar 0.2.3 JSON string escaping
issue with positive `minLength`. Schema-constrained results in this environment
are not a reliable basis for superiority claims over structured outputs.
See [the v2 reproduction and results](PROTOCOL_SFT_V2_EXPERIMENT.md).
The original row-level evidence remains unchanged.
