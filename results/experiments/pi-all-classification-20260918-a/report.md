# Finite whole-edit classification probe

Evidence: `results/experiments/pi-all-classification-20260918-a/` and
`results/experiments/pi-operation-prompt-20260918-a/`.

## Scope and implementation

Three previously evaluated keyword-edit tasks (workers default, Unicode JSON,
rejecting NaN) each run twice, with no fallback. Whole-edit candidates are built
from the original source's scoped calls/keyword slots and finite values:
booleans, null, and integers extracted from the task and selected call. An explicit
NONE alternative is included. String, expression, multi-edit and arbitrary code
construction are excluded. Candidate order is independently shuffled for each
repetition; this is a finite-DSL coverage probe, not arbitrary program synthesis
and not a trained multi-head model.

The model selects a complete tuple from this table. Existing V2 sampler hooks are
activated through CompletionRequest.vllm_xargs.openjev_direct_classify. One
candidate-logit argmax is transported as a control ID; software looks up the tuple
and applies it deterministically. No argument text is generated. Audit traces
verify all six classification calls bypassed the ordinary sampler; the returned
control ID is also checked against candidate-logprob argmax. This path performs
one logical next-position prediction per request, potentially across chunked
prefill, not one GPU kernel. It uses no continuation or cross-request KV reuse.

The other arms are the previous typed regex protocol and the existing direct
operation classification plus schema-constrained argument generation. All use the
same source/tasks, temperature zero, unique cache salts, isolated application and
the same behavior tests plus 17 original regressions. Random interleaving seed:
20260923. Candidate preparation/tokenization is excluded from measured requests.
There was no engine change, model training, restart or GitHub push.

## Results

| Metric, six requests each | Typed protocol | Classify + generate | Whole-edit classification |
| --- | ---: | ---: | ---: |
| Actual generated tokens | 170 | 77 | 0 |
| Classification control records | 0 | 6 | 6 |
| Input tokens | 10,108 | 11,178 | 9,798 |
| Behavior tests passed | 4/6 | 5/6 | 2/6 |
| Wall-time sum, including validation | 98.322 s | 61.091 s | 61.053 s |
| Reported initial queue sum | 78.389 s | unavailable | 49.887 s |
| Scheduling-to-first-output sum | 1.303 s | unavailable | 1.360 s |
| First-to-last-output sum | 7.046 s | unavailable | 0 s |

The live metric implementation is frozen in `live-metrics-definition.json`.
Scheduling-to-first-output plus first-to-last-output excludes initial queue wait:
8.349 s for typed versus 1.360 s for whole-edit classification, a **6.14x ratio /
83.7% reduction in this measured service interval**. It includes scheduling effects
after initial admission and is not isolated GPU kernel time. All-classification
removes subsequent autoregressive output steps; it still pays prefill and the
initial prediction. This supports a systems mechanism, not equal-quality speed,
stable throughput or a general 6x acceleration claim. Correctness and prompts
are unequal; tiny samples and shared service load remain confounders. The combined
endpoint does not expose comparable phase metrics, so no queue-adjusted speedup
against that arm is reported.

Failures are retained. Whole-edit classification chose check_circular=False or
ensure_ascii=False instead of allow_nan=False; one Unicode ordering selected
ensure_ascii=True; one workers ordering selected the existing default 10 instead
of 6. The two orderings gave different behavior outcomes for workers and Unicode.
This is consistent with candidate-order sensitivity, but concurrent numerical
variation was not separately controlled, so it does not isolate the cause.

## Operation prompt ablation

A separate six-request experiment compares the exact original classification
prefix against a simpler classification-only system instruction, retaining option
order/descriptions and source/task text. It covers the three previously failed
operation choices. The expected operation labels are only used for scoring, never
inserted into the prompts. Seed: 20260924. All six calls have verified V2 sampler
bypass events.

| Task | Original prompt | Classification-only prompt | Expected |
| --- | --- | --- | --- |
| Socket allocation failure | raise_if | raise_if | catch |
| Empty-host rejection | return_if | raise_if | raise_if |
| Workers default | arg | kw | kw |

Original: 0/3; cleaned prompt: 2/3. The old prefix combines instructions to generate
edit tuples with an instruction to select an operation letter. This small ablation
supports prompt design as a contributor to misclassification, not a conclusion
that all errors are due to model training. The socket semantic error remains.
There is no protocol-specific training in these experiments. Whether training,
better labels, order handling or joint scoring fixes the remaining errors is
untested. These diagnostic cases are selected previous failures, not a general
accuracy estimate.

Repository validation: 153 tests passed; published raw checksums passed; 69
published summary claims verified. Probe snapshots are create-only and checksum
protected. Existing headline results remain unchanged.
