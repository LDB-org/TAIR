# Bound-action preparation optimization under exclusive load

Forty real tasks: five repeats × defaults 6/8 × four arms, randomized within each matched task. All 40 pass identical AST/argparse checks. The same model and fixed candidate set (2/4/6/8/10 plus NONE) are used. No fallback, retries, or discarded outliers.

| Arm | Correct | Mean complete task s | Median s | Input tokens | Generated tokens | Classification controls |
|---|---:|---:|---:|---:|---:|---:|
| native | 10/10 | 3.616 | 3.599 | 51621 | 2331 | 0 |
| generate | 10/10 | 0.982 | 0.988 | 3347 | 390 | 0 |
| classify | 10/10 | 1.927 | 1.926 | 3367 | 0 | 10 |
| classify_cached | 10/10 | 0.693 | 0.691 | 3367 | 0 | 10 |

The optimized classifier is 2.78x as fast as the unchanged serial classifier, 1.42x as fast as the single-request generator, and 5.22x as fast as stock Pi on this fixture.

These are observed complete-task ratios, not general Agent claims. Native uses read/edit/reply (three inference calls) with Pi startup included. Bound arms use a specialized one-request workflow and deterministic DONE, with Python interpreter/import startup excluded. The native ratio therefore includes orchestration and prompt/input reductions, not just classification.

Optimization reuses the existing URL/model/tokenizer-revision/label-set keyed disk cache in the Pi bridge and overlaps prompt tokenization with label preparation. The same helper is wired into dynamic codebook classification preparation. The bound benchmark now uses this shared helper instead of six sequential label requests. No server change was required.

| Optimized state | Tasks | Mean complete s | Mean preparation s | Tokenize HTTP calls/task |
|---|---:|---:|---:|---:|
| cold | 5 | 0.713 | 0.287 | 7 |
| warm | 5 | 0.674 | 0.244 | 1 |

Preparation fell from 1.501 s to 0.266 s. Most latency improvement is already present when cold due to concurrency; warm cache reduces HTTP calls from seven to one. Each repeat starts with a fresh temporary cache, and both cache fill and cache-hit work are included. Tokenizer file hashes were verified on the live server and supplied as PIJIT_TOKENIZER_REVISION; missing revision disables persistent caching.

All ten serial/optimized pairs have exactly identical plans and inference payloads except fresh cache salts. See paired-payload-checks.json. Both arms use 3367 total input tokens and ten controls with zero generated argument tokens. Twenty classification requests have verified sampler-bypass audit records.

The model proxy and CyberEdge remain frozen. One-second load monitoring is in ../bound-action-task-20260918-optimized-monitor/. Mean initial queue is below 0.05 ms in every bound arm. Service intervals include scheduling-to-first plus first-to-last, not GPU kernel time. This is a small finite preset fixture under exclusive load; it does not establish natural-language coverage or full Pi integration performance for arbitrary edits.

Validation: 209 repository tests pass. Previous frozen archives remain unchanged. Temporary label caches and credentials are not archived.
