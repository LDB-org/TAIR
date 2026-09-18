# Protocol SFT v2: diverse payload generalization

## Frozen design

V1 improved finite-choice selection but often generated one unrelated Chinese
sentence. V2 tests whether broader data improves exact argument generation.
This is still an authored routing/copy benchmark, not open-ended generation or
real tool execution. The earlier test failures informed category design; none
of the old requests or payload strings are reused as v2 training or evaluation
rows. The new test remains untouched by training/checkpoint selection.

Compared with v1's 96 training cases built from 24 payloads, v2 has 256 training
cases with 256 distinct payloads. Validation has 32 and test has 64 distinct
payloads. Eight categories cover plain text, quotes, paths, Chinese, call-shaped
text, urgency/tool words inside text, whitespace, and longer sentences. Each
category balances both tools and both priorities. Payload identity, variable
word pools, and request templates differ across splits. Repeated runs do not
add independent test cases. This synthetic template family remains narrow.

The model starts fresh from Qwen/Qwen3-1.7B revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; it does not continue v1 training.
Training code and inference protocol are unchanged: BF16 LoRA rank 16, alpha 32,
q_proj/v_proj, learning rate 0.0002, accumulation 4, seed 731, fixed two epochs.
Each case supervises both complete JSON and the three hybrid stages. This means
1024 training examples per epoch, versus v1's 384; increased optimization work
and data diversity are both changed, so this is not a pure diversity ablation.
Only the final checkpoint is evaluated; validation loss is diagnostic.

[Data generator](../benchmarks/build_protocol_sft_v2_data.py) and
[frozen split manifest](../benchmarks/data/protocol-sft-v2-manifest.json).
The manifest was created before optimization. Source/report/checkpoint hashes
preserve exact provenance. Local weights remain outside the repository.

## Comparison and acceptance

Run the untouched base model and v2 merged checkpoint on all 64 new cases,
twice each, with plain JSON, schema-constrained JSON, and hybrid fields.
Thus each model has 384 timed calls. The same unchanged vLLM runner/settings
apply: vLLM 0.28.0, eager BF16, batch one, 1024-token context, 256 maximum batched
tokens, 256MiB explicit KV cache, 128-token output cap, and one exposed RTX 4070.
Retain prefix cache within the three-stage hybrid call, clear it between calls.
Warm up all modes and rotate their order. Base/trained scoring is sequential,
so desktop scheduling and temperature remain potential timing confounders.

Report exact calls, complete valid calls, each field's accuracy, output tokens,
and median latency. Independently rederive scores from row-level objects.
The speed acceptance criterion is comparable exact accuracy against the trained
JSON baseline; a faster incorrect output is not a useful speedup. Per-category
scores help expose errors hidden by aggregate accuracy. Agreement on this small
fixture would not establish statistical noninferiority or production safety.

## Reproduction

Use the v1 training command with `protocol-sft-v2-train.jsonl` and
`protocol-sft-v2-validation.jsonl`, and new checkpoint/report paths. Model
revision, trainer and hyperparameters remain as specified above. Then use the
v1 vLLM command with `protocol-sft-v2-test.jsonl` and new base/trained report
paths. Compare the two reports with `benchmarks/compare_protocol_sft.py`.
See [v1](PROTOCOL_SFT_EXPERIMENT.md) for the full environment and commands.

## Results

The run completed with validation target-token loss decreasing from 2.6046 to
0.1088. Both repeats returned identical call objects for every model/mode/case.
Each table row contains 128 timed calls over 64 distinct authored cases.

| Model | Path | Median ms | Complete valid | Exact call | Output tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| Base | JSON | 760 | 128/128 | 50/128 | 5266 |
| Base | JSON + schema* | 776 | 128/128 | 32/128 | 5188 |
| Base | Hybrid | 626 | 128/128 | 14/128 | 4214 |
| V2 trained | JSON | 888 | 128/128 | 118/128 | 5782 |
| V2 trained | JSON + schema* | 863 | 114/128 | 62/128 | 5540 |
| V2 trained | Hybrid | 492 | 128/128 | 102/128 | 3006 |

**The matched-quality acceptance criterion was not met.** Trained hybrid exact
accuracy was 79.7%, versus trained plain JSON's 92.2%, with 44.6% lower median
time and 48.0% fewer output tokens. Hybrid adaptation improved from 14/128 to
102/128 on this fixed set. This is stronger mechanism evidence but not an
accuracy-preserving speedup. Do not compare these accuracy percentages directly
with v1: the test cases and their difficulty changed.

Trained hybrid tool/priority/content accuracy was 116/128, 128/128, and 110/128.
Among the 64 distinct cases, there were six tool errors and nine content errors,
with two overlapping. Eight of the nine content errors were Chinese cases; the
other changed whitespace. The Chinese cases substituted training phrases such
as `缓存需要清理` for unseen phrases, while often retaining the new numbers and
Latin words. No full output string repeated across distinct hybrid requests,
so the previous constant-sentence behavior disappeared, but partial memorization
remains. The evidence JSON currently represents Chinese with Unicode escapes;
its role in these failures is a hypothesis for a separate future experiment.

### Every predefined category

Each category contains eight distinct cases, each repeated twice. No failed
category is excluded from aggregate accuracy or timing.

| Category | Trained JSON exact | Trained hybrid exact | JSON / hybrid median ms |
| --- | ---: | ---: | ---: |
| Plain | 16/16 | 16/16 | 789 / 403 |
| Quotes | 16/16 | 14/16 | 921 / 550 |
| Path | 16/16 | 14/16 | 791 / 406 |
| Chinese | 16/16 | 0/16 | 799 / 396 |
| Call-shaped text | 16/16 | 16/16 | 1056 / 629 |
| Urgency/tool words in text | 14/16 | 16/16 | 994 / 619 |
| Whitespace | 8/16 | 14/16 | 840 / 425 |
| Longer text | 16/16 | 12/16 | 1145 / 754 |

### Schema baseline anomaly: exclude from superiority claims

The starred schema baseline uses the locally installed XGrammar 0.2.3 compiler.
The trained run emitted seven distinct completed objects (14 repeated calls)
containing unescaped Tab characters inside JSON strings. They stopped normally,
did not hit the token limit, and were rejected by Python's JSON parser. This is
different from the v1 length-limit failures.

A CPU-only reproduction with the same schema isolates unexpected grammar
behavior when `content.minLength` is 1 (or 2): valid escaped Tab, escaped quote,
and escaped backslash strings are rejected by both string and token acceptance,
while a string with an invalid literal Tab is accepted to completion. Removing
minLength or setting it to zero produces the expected acceptance for these six
probes. This reproduces a local compiler issue without GPU inference, model
weights, or the hybrid protocol. It is not evidence that all structured-output
implementations are unreliable. The compiler issue can distort both correctness
and latency, so these schema results cannot establish superiority over a sound
schema-constrained baseline. The unmodified plain JSON baseline remains the
primary comparison. No local package, grammar, or inference schema was silently
changed to repair the measured run.

Reproduction:

```bash
/home/Kei/projects/ldb-gpu-acceptance-20260908/.venv-vllm/bin/python \
  benchmarks/reproduce_schema_escape.py \
  --model /home/Kei/.cache/openjev-protocol-sft/qwen17b-v2/merged \
  --output results/experiments/NEW-ESCAPE-REPRO.json
```

## Evidence and next experiment

- [Training report and checkpoint hashes](../results/experiments/protocol-sft-qwen17b-training-v2.json)
- [Base calls](../results/experiments/protocol-sft-qwen17b-base-test-v2.json)
- [Trained calls](../results/experiments/protocol-sft-qwen17b-trained-test-v2.json)
- [Independent comparison](../results/experiments/protocol-sft-qwen17b-comparison-v2.json)
- [All category results and invalid calls](../results/experiments/protocol-sft-qwen17b-trained-categories-v2.json)
- [CPU grammar reproduction](../results/experiments/protocol-sft-schema-escape-repro-v2.json)
- [minLength probes](../results/experiments/protocol-sft-schema-minlength-probe-v2.json)

The next experiment should address Chinese string representation and diverse
copy supervision, and separately correct or replace the schema baseline before
using it for claims. Any tuning informed by these failures needs another new
held-out set. More tools, arbitrary schemas, free-form answer generation, and
production throughput remain untested. Data-generation patterns and numeric
identifiers are synthetic, so this is not a broad capability assessment.

29 repository tests passed; original raw checksums and all 69 published scalar
checks passed. Phase 1 claims and evidence remain unchanged. No tools were
executed and no model-serving process was left running.
