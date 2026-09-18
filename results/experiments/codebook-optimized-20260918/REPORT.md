# Dynamic codebook: explicit binding optimization

## Change

The default persistent codebook now recognizes complete CLI property requests using
the existing bounded `schema_actions.bind` parser. Recognized paraphrases can
retrieve previously learned entries from the same file and exact source snapshot.
The instantiated edit must match the requested option, property, value and JSON
value type. Other tasks retain the original normalized-wording restriction.

The engine still classifies candidates plus NONE. If its selected candidate exactly
matches the explicit binding, acceptance uses that match instead of the heuristic
0.95 conditional score / 3 logprob margin gate. Contradictory candidates are rejected
even with high scores; NONE remains a rejection. Unparsed tasks retain the old gate.
Traces distinguish `explicit_binding` from `score_gate` acceptance.

This is a bounded deterministic applicability check combined with model selection,
not improved general semantic classification or universal confidence calibration.
Cold misses still generate and learn: the parser does not insert a preset entry.
Source-hash invalidation and single-keyword admission limits remain unchanged.

## Method

Existing yuesheng 6×RTX 5090 backend, three independent repeats, seven sequential
cases, three randomly interleaved arms: always generate, legacy dynamic codebook,
optimized dynamic codebook. Total: 63 actual edits. The generation control uses
the same compact protocol and engine-side operation classification, not ordinary
full-source generation. All arms use a fresh codebook per repeat, preserve it
across cases, and restore the declared source before each task. No preseeded actions,
retries, tokenizer label cache, schema-action execution, or exact replay.

Cases: cold workers=6, exact repeat, workers=8, paraphrased workers=10, changed
source requesting workers=12, add alias, repeat alias. The first two repeats of the
previous diagnostic exposed these optimization targets; these are regression cases,
not an independent generalization benchmark. Two separate positive gate probes use
a different option/integer and a string property. Seven negative probes challenge
the gate with wrong values, target, property, extra edits, bool/int confusion,
negation and an incompletely satisfied compound task. Gate probes do not execute
edits and are reported separately.

Every edit uses the same configured behavior oracle checking argparse defaults,
explicit input handling and action count; alias cases also check the short option.
Wall time includes HTTP preparation, classification/generation, backup, apply and
oracle execution. It excludes fixture restoration and final metrics append, and
does not include the outer Agent loop. Shared backend, small workload, three repeats;
these timings are not exclusive GPU kernel time or a broad production estimate.

## Matched results

| Metric | Always generate | Legacy codebook | Optimized codebook |
|---|---:|---:|---:|
| Behavior checks passed | 21/21 | 21/21 | 21/21 |
| Accepted learned reuse | 0 | 0 | 9 |
| Inference requests | 21 | 27 | 21 |
| Generated argument tokens | 210 | 210 | 120 |
| Classification control records | 21 | 27 | 21 |
| Input tokens | 10,146 | 10,890 | 6,897 |
| Total edit wall time | 8.776 s | 9.678 s | 6.657 s |
| Median edit wall time | 0.417 s | 0.418 s | 0.411 s |

Optimized total wall time decreased 31.2% versus legacy and 24.1% versus always
generate; generated arguments decreased 42.9%. The median changes little because
12 of 21 edits still generate. On the nine matching repeat/value/paraphrase cases,
mean edit wall time was 0.415 s for generation, 0.520 s for legacy and 0.186 s for
optimized reuse, a 55.2% decrease versus generation. Each accepted reuse makes one
classification request and emits zero generated argument tokens; it is not zero
model computation.

All three repeats show the same behavior: the cold generation admits its template;
the next three tasks reuse it. Changed source invalidates it; alias edits do not
enter the single-keyword book and generate again. Thus the experiment demonstrates
reuse of a learned template within a bounded family, not monotonically decreasing
latency for arbitrary tasks or general learning of every generated action.

## Gate challenges

| Result | Legacy | Optimized |
|---|---:|---:|
| Incorrect candidates rejected | 6/7 | 7/7 |
| Separate correct candidates accepted | 1/2 | 2/2 |

Legacy accepted the constructed extra-edit candidate at conditional score 0.977
and margin 3.75; optimized rejected its mismatch with the complete request. This
is a direct gate probe: multi-edit candidates cannot normally enter the default
single-keyword codebook, so it is not evidence of a reachable default-runtime
multi-edit failure. The tests deliberately bypass retrieval to challenge the gate.
The other legacy miss was a correct integer candidate rejected at score 0.818.
Nine probes do not establish a calibrated error rate or guarantee safe semantics.

## Reproduction and evidence

Run against a compatible existing engine, with a checkout of the legacy source:

```sh
python benchmarks/benchmark_codebook_reuse.py \
  --url http://127.0.0.1:8000 \
  --legacy-root /path/to/legacy/TAIR \
  --out results/experiments/NEW_OUTPUT --repeats 3
```

Legacy base: `4772970c061837e78a8af23da946c0ecfb4c3d26`. Current executed source
is captured in `code.tar.gz` and selected readable files under `sources/`;
`environment.json` records source hashes and the legacy bridge hash.
`rows.jsonl`, `challenges.jsonl`, per-task book snapshots and `engine-events.jsonl`
retain raw observations. Multiple workers may record events for the same request;
event counts must not be treated as inference-request counts. Evidence transfer
archive SHA-256: `837335d13457a58655871642fdef352d51539b8f4009aa5b62be176d3cc02c8b`.

No vLLM patch, model reload, service restart or production release replacement.
Container start time remained `2026-09-18T05:44:43.699377485Z` before/after.
Local validation: isolated Python 3.11 environment installed with `pip install -e
'.[test]'`; 264 pytest tests passed, including bound-match, contradictory high-score,
NONE, negation, compound-task and wrong-type regression tests. Frozen archive
integrity checks passed. No model was loaded by the API benchmark client.
