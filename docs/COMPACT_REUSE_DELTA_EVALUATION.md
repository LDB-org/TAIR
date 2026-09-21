# Compact selected-candidate requirement delta

The runtime already supplies a word-level `contract_changes` summary in candidate descriptions, while selected-candidate continuations repeat a line-level `request_delta`. For single-paragraph requests, the latter repeats most of the old and new task even when only a filename or one clause changed.

`benchmarks/probe_candidate_binding.py --compact-delta` tests substituting the existing word summary in that continuation only, falling back to the line summary if the word summary is empty. Both arms use current runtime code, the same complete candidate catalog, full user request, source bytes and schema. A singleton label forces the candidate. This tests post-selection handling, not natural classification or complete Agent behavior. Five fixtures cover compatible JavaScript/Python reuse, changed case/duplicate-key requirements, and an unrelated candidate.

| Arm | Independent first-write checks | Input tokens | Generated tokens | Request wall total |
| --- | --- | --- | --- | --- |
| Line delta | 2/5 | 8,512 | 457 | 6.757 s |
| Word delta | 2/5 | 7,659 | 457 | 6.576 s |

Both compatible cases reuse correctly. Both changed-requirement cases still reuse incompatible source. The unrelated-candidate case abandons reuse but fails the single requested write contract in both arms. The input reduction is 853 tokens (10.0%), not generated-token savings. The small total wall difference is mostly the first pair; there is one sample per pair and no warmup, so no reliable latency improvement is established. Request timing includes local preparation and HTTP, and all failed cases stay in totals.

No runtime prompt change was retained. The failed constraint checks show that making the already-present difference shorter does not by itself repair applicability decisions on these fixtures. The probe and evidence remain available for reproduction. Complete artifacts, initial/final idle checks and checksums are frozen in `results/experiments/compact-reuse-delta-20260921-a`; aggregate counts are in `COMPACT_REUSE_DELTA_EVALUATION.json`.
