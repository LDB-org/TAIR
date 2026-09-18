# Expanded candidate-gate checks

Sixteen candidate cases were evaluated against previous and expanded implementations in fresh Python workers, using the live 5090 model and direct-classification path. No edits were applied. Candidates deliberately bypass normal retrieval; some malformed or multi-edit proposals would not enter the previous default codebook.

Expanded: 10/10 negative candidates rejected, 6/6 positive candidates accepted. Previous: 9/10 negatives rejected, 6/6 positives accepted. The previous gate accepted a partial edit for a compound request; expanded rejected it. The extra source context and candidate guide affect conditional scores, so these observations are not a calibrated error rate.

Cases include wrong values, targets, properties, extra edits, boolean/integer and float/integer type confusion, negation, incomplete compound tasks, aliases, float/boolean values and Unicode help text. Original cases plus the additional typed cases are frozen in manifest.json. These are small designed probes, not an independent generalization dataset or semantic safety guarantee.

All 32 requests have matching sampler-bypass events in engine-events.jsonl. rows.jsonl retains every decision, candidate, score and request trace. code.tar.gz pins the executed edit/gate implementation; benchmark_codebook_guards.py pins the runner. The later Agent routing prompt affects chat only; it does not change this gate.

Transfer SHA-256: 83046644875cee516e5023c1411a256495489f8cbd2c3e6ea4f01263eecebe6e.
