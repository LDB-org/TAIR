# Dynamic codebook with generative fallback: DeepSeek 5090 probe

Evidence: `results/experiments/pi-jit-codebook-20260918-b/`.
An interrupted development run is preserved separately as `pi-jit-codebook-20260918-a/`.

## What was implemented

An initially empty, in-process codebook learns supported edits from successful
model generations. Each entry records its source hash, originating task description,
edit template and validation provenance. A single integer value becomes a task
binding when the same unambiguous integer appears in the task. Boolean/string/null
values remain literal. Only single `kw` edits are admitted in this prototype.
Generated conditions and exception handlers can execute but are not learned.

Retrieval checks the entire source hash and source-derived target scope. For
applicable entries, DeepSeek directly classifies the proposed instantiated edits
plus an explicit NONE candidate. Existing V2 vLLM hooks bypass ordinary sampling;
no new engine patch or restart was needed. Parameters on a cache hit are constructed
by software, not generated. This is a client-side codebook prototype using real
engine classification, not a fully fused server-side JIT or arbitrary-code compiler.
Snapshots are persisted for audit; loading a codebook across process restarts is
not implemented.

The gate was fixed before the measured run: conditional candidate probability at
least 0.8 and top-versus-runner-up logprob margin at least 1.0. It is not calibrated.
NONE, an empty/inapplicable table, or insufficient score causes one generative
request. A failed cached behavior test also causes that request. Failed generated
edits are not admitted and are not retried. Admission and post-selection rejection
use hand-authored task tests plus 17 original regressions. Those tests are an
experimental oracle, not a deployed general reliability verifier.

## Workload and controls

Ten sequential tasks cover initial workers=6, a paraphrase requesting workers=8,
Unicode JSON and its paraphrase, a novel NaN requirement and its paraphrase, a
changed source snapshot requesting workers=12, a subsequent workers=14 request,
and two timeout-guard tasks outside the cacheable operation subset. The source
change is a comment appended to exercise conservative snapshot invalidation.
Each task starts from its declared pristine snapshot, not the prior task's edited
workspace; the codebook alone carries state across tasks.

For every task, an always-generate compact-protocol baseline and the JIT path run
in shuffled order (seed 20260925). Both use identical source/task text and the same
generation path on a miss. Only JIT generations can populate the JIT codebook;
baseline results do not seed it. Temperature is zero; requests use fresh cache
salts. The classifier and generative fallback are separate requests, so a miss
pays another prefill. All misses and failed attempts are included in totals.

The backend was confirmed live as six RTX 5090 GPUs, vLLM
`0.28.1rc1.dev137+g5ab628dd1`, with unchanged engine-helper and model-config hashes.
Container start time remained `2026-09-17T23:21:39.643641966Z`.

## Results

| Metric | Always generate | Dynamic codebook |
| --- | ---: | ---: |
| Final task tests passed | 9/10 | 9/10 |
| Model inference requests | 10 | 14 |
| Separate tokenize requests | 0 | 5 |
| Generated tokens | 194 | 182 |
| Classification control records | 0 | 5 |
| Total output units | 194 | 187 |
| Input tokens | 16,812 | 22,757 |
| Input plus output | 17,006 | 22,944 |
| End-to-end task time sum | 104.08 s | 137.01 s |
| Scheduled-to-last-output interval sum | 7.982 s | 8.380 s |
| Initial queue time sum | 74.02 s | 93.80 s |

JIT saved 6.2% of generated tokens, or 3.6% including controls. Input plus output
increased 34.9%. Its queue-excluded service interval increased about 5.0%; observed
end-to-end time increased 31.6%. The shared server had large queue fluctuations.
The scheduled interval includes interference after admission and is not exclusive
GPU kernel time. Client timing includes extra tokenization/SSH and task checks.
This prototype did **not** achieve aggregate net acceleration.

The codebook ended with four version-bound entries: parameterized workers default
for two source versions, ensure_ascii=False, and allow_nan=False. Five requests
had candidates and used direct classification; three passed the score gate, but
two were wrong. Only one request completed through a validated cache hit. All five
classification calls have worker-event evidence of V2 sampler bypass.

The successful hit reused the generated workers=6 template for a new request for
workers=8. Baseline output was 12 tokens versus one classification control ID and
zero generated arguments. Its service interval was 0.337 s versus 0.273 s, about
19% lower for this single pair. Client time was nevertheless 2.49 s versus 3.92 s
because the prototype adds remote tokenization and transport. One hit is not a
stable speed estimate.

## Reliability findings

The gate accepted the Unicode edit ensure_ascii=False for BOTH NaN requests,
with conditional probability approximately 0.818 and margin 1.5. It did not satisfy
the NaN requirement. Oracle tests rejected both cached edits. One subsequent
generation also failed, while the paraphrased generation succeeded and was admitted
as allow_nan=False. Without the oracle, both bad classifications would have been
accepted as valid-looking but wrong edits.

Conversely, the correct Unicode candidate scored approximately 0.777 and a correct
workers=14 candidate scored approximately 0.622, so both triggered generation.
The gate accepts the wrong candidates at scores higher than correct candidates;
therefore lowering the scalar threshold alone cannot separate these observed
examples. Conditional candidate probability and almost-unit candidate mass are
not evidence that the intended operation is in the retrieved table.

Source-hash mismatch prevented stale worker templates from being reused. Failed
generations never entered the codebook; unsupported guard edits were generated
and tested without being cached. These mechanisms worked, but they do not solve
semantic applicability, production admission or arbitrary-prompt coverage.

## Next engineering questions

- Can applicability checks and calibrated out-of-candidate detection improve
  correct hit rate without oracle tests or increased false acceptance?
- Can tokenization/lookup live beside the engine, and can generated fallback reuse
  classification KV rather than paying a second request/prefill?
- Does a validated parameterized template keep its meaning across paraphrases,
  new values and relevant source changes? What should invalidate it?
- At what measured hit rate and task size does this path break even?

The JIT analogy is useful: pay more on discovery, then use guarded reuse. The
current experiment demonstrates that state transition and one successful reuse,
not a reliable or faster general agent inference framework.

## Reproduction and validation

```bash
ENGINE_TOOLCALL_HOST=your-ssh-host python benchmarks/probe_jit_codebook.py \
  --out results/experiments/NEW_JIT_RUN
python benchmarks/summarize_jit_codebook.py results/experiments/NEW_JIT_RUN
python benchmarks/verify_jit_codebook.py results/experiments/NEW_JIT_RUN \
  --host your-ssh-host --container your-vllm-container
```

The verification command captures matching engine events and creates a verification
file; do not rerun it into an existing output path. No Pi installation is needed
for these compact-protocol-only arms, but Linux bubblewrap and the original
isolated Python test environment are required.

Standalone tests: 152 passed. Original imported archive checks passed. Run `a`
was interrupted when a unit test exposed a number-binding regex rejecting a
sentence-final period. Four completed rows and an in-flight request with unknown
usage are retained there; it is excluded from measured totals. The regex was fixed
and binding tests passed before the separate complete run `b`.
