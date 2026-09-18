# DeepSeek: direct classification plus compact structural edits

Evidence: `results/experiments/pi-combined-structural-20260918-a/`.
Smoke evidence is retained separately in `pi-combined-smoke-20260918-a/`.

This combines the earlier source-bound typed editing protocol with the deployed
V2 vLLM direct-logit classifier and retained-KV continuation. The remote engine
selects an operation and constrains its parameter array; the local deterministic
runtime applies that operation to the original source snapshot. It is a measured
editing workflow, not a migration of the entire Pi agent loop.

## Results

One repetition of ten tasks per arm, with every failed attempt and fallback included:

| Metric | Native Pi edit | Earlier typed protocol | Combined |
| --- | ---: | ---: | ---: |
| First-attempt pass | 10/10 | 8/10 | 7/10 |
| Final pass with fallback | 10/10 | 10/10 | 10/10 |
| Requests | 10 | 12 | 13 |
| First-attempt output units | 2,036 | 249 | 225 |
| Fallback output units | 0 | 221 | 673 |
| All output units | 2,036 | 470 | 898 |
| Input tokens | 19,236 | 20,727 | 24,460 |
| Input plus output | 21,272 | 21,197 | 25,358 |
| Sum of task wall times | 187.20 s | 98.88 s | 146.76 s |
| Median task wall time | 16.11 s | 7.00 s | 11.02 s |

Combined generated 888 tokens plus ten internal classification control records.
Its 898 output units are **55.9% fewer than native**, but **91.1% more than the
earlier typed protocol**. Input plus output increased **19.2% versus native**.
Before fallback, combined output was 9.6% below typed, but these totals include
incorrect attempts and cannot be presented as equal-quality savings.

The measured combined wall-time sum was 21.6% below native and 48.4% above typed.
This is **not stable acceleration evidence**: native alone accumulated 136.47 s
of reported queue time, compared with 59.89 s for typed. Combined has no comparable
queue/decode breakdown. Shared-server contention, different prompts and tool
application costs prevent attributing the wall-time difference to classification.

All ten combined endpoint calls returned schema-valid parameter arrays. Worker
events verify that all ten bypassed the ordinary sampler for classification and
reused 1,788–1,830 prefix tokens with unchanged KV block IDs; nine overlapped normal
sampling rows. The injected continuation added 27–78 input tokens per call.

Three combined failures were semantic category errors, not malformed JSON:

- `socket_creation`: selected `raise_if` instead of catching socket allocation
  failure; the behavior test failed.
- `guard_empty_host`: selected `return_if` and put `raise ValueError(...)` in the
  return expression; Python parsing rejected it before the edited program ran.
- `default_workers_six`: selected `arg` and added `"6"` as an option alias instead
  of changing the `default` keyword; argparse rejected it in the behavior test.

The earlier isolated workers smoke passed all three arms (113 / 12 / 11 output
units). Its success and the later combined failure are both retained. Their cause
has not been isolated; no stability claim follows from the smoke.

**Conclusion:** the two mechanisms combine successfully at the engine/runtime
boundary, and compact edits preserve large output savings against native text
replacement. This version does not outperform the old typed protocol overall.
Classification accuracy and resulting fallback cost are the immediate obstacles;
schema validity alone cannot remove them. No protocol training was done here.

Repository checks: 153 tests passed, all published raw-data hashes passed, and
69 published summary claims verified. Existing headline results were unchanged.

## Method

Three arms use the same original `port_scanner.py`, task text, 2048 output-token
budget, temperature zero, fresh per-request cache salts, and isolated execution:

- Native: the model produces a real Pi `edit` call containing old/new text, then
  Pi 0.85.1's actual edit tool applies it.
- Typed: the earlier source-scoped regex protocol emits tuples containing
  operation, target and necessary values, then the deterministic runtime applies it.
- Combined: candidate-logit argmax selects `arg`, `kw`, `return_if`, `raise_if`,
  `catch`, or `mixed`, restricted to source-applicable candidates. The same engine
  request retains its KV, receives the selected continuation and schema, and
  generates only target/value tuples. The runtime supplies the selected operation
  name; `mixed` retains individual operation names when needed.

Target and keyword candidates come from the original source and the existing
lexical task-scope retrieval. No expected solution is supplied. Schema constraints
cover tuple lengths, source targets, keyword slots and value types. Condition and
return expressions remain generated Python text and undergo subsequent parsing;
a valid schema does not imply a correct or safe program.

The ten tasks are the same previously tuned project regression tasks used in the
old scoped experiment, not new held-out tasks. Tasks and arm order are randomized
with seed 20260922. Each task must fail on the pristine file. After applying a
change, a task-specific behavior test and 17 original regressions run in bubblewrap
with a private network namespace. Socket-failure tests use mocks; scanner tests
use loopback only. Both experimental arms receive at most one fresh native retry
from the pristine file after any failure. These task tests act as an oracle for
fallback: this is not an autonomous production acceptance policy.

Preparation/tokenization is outside timed attempts in all arms. Wall time includes
SSH/API waiting, edit application, behavior tests and fallback. Generated argument
tokens include termination; each combined classification control record is also
counted conservatively as one completion unit. Input totals include the injected
continuation, counting the retained classifier prefix once. No failed attempt or
fallback is discarded. Output savings do not mean equivalent total-token savings.

The live engine helper and model configuration hashes match the earlier engine
and long-output runs; this combination required neither another engine patch nor
a restart. `live-manifest.json` records vLLM version, container image, start time,
configuration hash, helper hash and serving arguments. The model metadata revision
is inherited from the earlier download record, not a fresh hash of all weights.
The existing six-GPU TP2 x PP3 service remains shared with other requests.

## Reproduction and audit

Run from the repository root in the test environment:

```sh
.venv/bin/python benchmarks/evaluate_direct_structural.py --out results/experiments/NEW_DIRECTORY
.venv/bin/python benchmarks/summarize_direct_structural.py results/experiments/NEW_DIRECTORY
.venv/bin/python benchmarks/verify_direct_structural.py results/experiments/NEW_DIRECTORY results/experiments/NEW_DIRECTORY/engine-events.jsonl
```

The event file must contain the matching remote worker events. The verifier checks
that every combined call bypassed ordinary sampling for classification, selected
the candidate-logit argmax, retained the complete prefix and identical KV block
IDs, and resumed with the selected structured schema and output budget. This
proves the measured execution path, not semantic correctness.
