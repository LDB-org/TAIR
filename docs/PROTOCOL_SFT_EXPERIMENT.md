# Protocol SFT experiment v1

This is a bounded engineering test of protocol adaptation, not a general
agent benchmark. It follows the untrained field-protocol failures documented
in [the earlier experiment](SCHEMA_TOOLCALL_EXPERIMENT.md).

## Frozen design

- Base: Qwen/Qwen3-1.7B, revision
  `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`.
- RTX 4070 12GB, WSL; BF16 training, no weight quantization.
- PEFT 0.18.0 LoRA, rank 16, alpha 32, q_proj/v_proj, no dropout.
- Learning rate 0.0002, AdamW, gradient accumulation 4, seed 731,
  exactly two epochs; final checkpoint only, no test-driven selection.
- 96 authored training cases, 16 validation cases, 32 new test cases.
  Request templates and payload strings are disjoint across splits.
  Each payload occurs with all four tool/priority combinations within a split.
  Thus rows are correlated and do not represent 32 independent payloads.
- Each training case produces four supervised examples: tool letter, priority
  letter, raw content plus EOS, and complete JSON plus EOS. Both output
  approaches receive task-specific training. Teacher-forced prompts use the
  exact append-only inference serialization, including the empty thinking block.
- Loss covers target tokens only. Classification targets contain one letter;
  the engine supplies their turn terminator. Prior decisions are teacher-forced
  in training and model-selected in evaluation.
- Validation loss is diagnostic only. The training program never reads the test
  file. Data and manifest are frozen before optimization starts.
- Urgency inside a literal payload does not change the outer request's priority.
  Quotes, backslashes, Chinese, newlines, and call-shaped content are covered.
- No tools are actually executed. Replying is represented as `reply_user`.

The data generator is [build_protocol_sft_data.py](../benchmarks/build_protocol_sft_data.py).
The exact split hashes are in [the manifest](../benchmarks/data/protocol-sft-v1-manifest.json).
Training uses [train_toolcall_protocol.py](../benchmarks/train_toolcall_protocol.py).
Weights and adapters are stored under `/home/Kei/.cache/openjev-protocol-sft/`,
not in the repository. The training report records their SHA-256 hashes.

LoRA uses the standard [PEFT implementation](https://github.com/huggingface/peft).
Adapters are merged before inference so adapter runtime overhead does not bias
latency. No vLLM plugin or custom classification head is introduced.

## Acceptance and evaluation

Evaluate the untouched base and merged trained model on the same 32 new cases,
using plain JSON, vLLM schema-constrained JSON, and hybrid fields, twice each.
All six cells use identical vLLM settings, eager BF16, batch one, a 1024-token
context, 256 maximum batched tokens, and an explicit 256MiB KV cache. Reset
prefix cache between independent calls, retaining it between hybrid stages.
Warm up all three paths before measurement and rotate path order by case/repeat.
Training and scoring must run sequentially on the one exposed CUDA device.

Report schema validity, exact complete-call match, individual field accuracy,
output tokens, and median latency. Repeats measure timing stability, not new
quality samples. Compare base versus trained to measure adaptation, and compare
trained hybrid versus trained JSON paths to assess speed at comparable quality.
A lower latency with poorer exact accuracy is not a matched-quality speedup.
Base and trained runs are sequential on a desktop GPU; thermal/background drift
remains a limitation. This task tests exact routing and copying, not open-ended
content quality, unseen tools, arbitrary schemas, or production throughput.

## Reproduction

Install `peft==0.18.0` in the repository's isolated test environment. Preserve
the package versions recorded in the training report. Run from repository root:

```bash
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python benchmarks/train_toolcall_protocol.py \
  --model /home/Kei/.cache/huggingface/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --train benchmarks/data/protocol-sft-v1-train.jsonl \
  --validation benchmarks/data/protocol-sft-v1-validation.jsonl \
  --output /home/Kei/.cache/openjev-protocol-sft/NEW-RUN \
  --report results/experiments/NEW-TRAINING-REPORT.json
```

For each of the base and merged model paths, use the vLLM environment and
compatibility flags from the earlier experiment. Run the unchanged
`benchmarks/schema_toolcall_vllm.py` with `--protocol fields --repeats 2`,
`--cases benchmarks/data/protocol-sft-v1-test.jsonl`,
`--gpu-memory-utilization 0.75 --max-model-len 1024`,
`--max-batched-tokens 256 --kv-cache-memory-bytes 268435456`, and a fresh output
path. The merged checkpoint retains base revision provenance; its exact identity
is additionally defined by checkpoint hashes in the training report.

Use `benchmarks/compare_protocol_sft.py --base BASE-REPORT --trained TRAINED-REPORT
--output NEW-COMPARISON` to independently recompute outcomes and verify matched
settings. Keep all evidence create-only.

## Measured result

Training completed successfully. Mean per-example target-token validation loss
fell from 2.2345 to 0.5579. This validation loss is not call accuracy. The final
checkpoint was used without changing prompts or tuning on test outcomes.
All 384 inference calls completed. The two repeats produced identical call
objects within each mode/model cell; the table reports all 64 timed calls per
cell, representing 32 distinct cases and only eight distinct payloads.

| Model | Path | Median ms | Complete valid calls | Exact calls | Output tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| Base | JSON | 581 | 62/64 | 30/64 | 1830 |
| Base | JSON + schema | 605 | 64/64 | 18/64 | 1794 |
| Base | Hybrid | 467 | 64/64 | 6/64 | 1568 |
| Trained | JSON | 580 | 64/64 | 46/64 | 1834 |
| Trained | JSON + schema | 607 | 58/64 | 26/64 | 2388 |
| Trained | Hybrid | 182 | 64/64 | 32/64 | 494 |

The trained hybrid got tool/priority/content right on 60/64, 64/64, and 36/64
calls. Before training these scores were 32/64, 42/64, and 22/64. Thus this
bounded protocol adaptation improved classification and complete-call accuracy,
but did not meet matched-quality speed acceptance: trained plain JSON still
achieved 46/64 exact calls versus hybrid's 32/64. The hybrid's 68.6% lower median
time versus trained JSON must not be advertised as an equivalent-quality gain.
Incorrect shortened content contributes to its lower token count and latency.

Inspection found a repeated unrelated string, `任务已经完成。`, in eleven of the
32 distinct hybrid cases, including requests for a certificate query, a Windows
path, Chinese text, and one multiline payload. This resembles a training
payload with its numeric index removed, suggesting poor generalization/content
collapse rather than a serializer problem. Four multiline cases also failed to
preserve the exact newline/tab content (one is the unrelated-string case).
Two reply cases were misrouted because their literal content named search_docs.
These are observed errors, not a claim about all possible protocol training.

The six invalid trained schema calls were three cases repeated twice:
`test-009`, `test-010`, and `test-021`. Each hit the 128-token limit while emitting
whitespace instead of completing the object. All were rejected; no truncated
call was accepted. A grammar constraint is not a guarantee of completion within
a token budget. This does not establish that the grammar accepted a malformed
completed object. Hybrid calls all passed the fixed shape validator, but several
contained semantically wrong values.

The small training set has just 24 unique payloads. Strong training loss with
these held-out errors makes expanding payload and template diversity the next
useful test, especially literal-copy boundaries and escaping. These 32 cases
are now diagnostic data and must not be reused as a fresh held-out acceptance
set after tuning. No further training or prompt selection used their results.

Evidence:

- [Training and checkpoint hashes](../results/experiments/protocol-sft-qwen17b-training-v1.json)
- [Base row-level calls](../results/experiments/protocol-sft-qwen17b-base-test-v1.json)
- [Trained row-level calls](../results/experiments/protocol-sft-qwen17b-trained-test-v1.json)
- [Independent comparison](../results/experiments/protocol-sft-qwen17b-comparison-v1.json)

Repository tests: 28 passed. Original raw checksums and all 69 published scalar
checks passed. Phase 1 claims and results were not changed.

## Later baseline qualification

The v2 investigation reproduced a local XGrammar 0.2.3 JSON string escaping
issue with positive `minLength`. Schema-constrained results in this environment
are not a reliable basis for superiority claims over structured outputs.
See [the v2 reproduction and results](PROTOCOL_SFT_V2_EXPERIMENT.md).
The original row-level evidence remains unchanged.
