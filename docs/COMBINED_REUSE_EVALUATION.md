# Combined plan optimizations and warm content reuse

2026-09-21. Frozen evidence: `results/experiments/combined-reuse-ablation-20260921-a`. Existing Yuesheng six RTX 5090 model service; Pi 0.85.1; one task at a time, seed 731 interleaved arm order. Eight task executions per arm: Python JSONL and JavaScript uniqueStrings, each base, identical repeat twice, changed constraints. Thirty-two total runs. All user codebooks remain untouched; each plan arm starts with an empty isolated book and learns across tasks. Project files reset between tasks.

Four arms separate native behavior, ordinary plan, combined plan without reuse, and combined plan with reuse. Combined arms enable argv command representation, dedicated reply classification, write references, and recovery admission. Only reuse differs between those two arms. All plan arms use the same pinned local tokenizer; other experimental switches are off. This comparison does not isolate each member of the combined configuration individually.

## Whole-task results

| Arm | Final independent checks | Wall seconds | Generated tokens | Logical input tokens | Requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native | 8/8 | 71.178 | 7114 | 69554 | 26 | 0 | 0 |
| Ordinary plan, reuse off | 8/8 | 81.815 | 5846 | 81972 | 23 | 23 | 3 |
| Combined plan, reuse off | 8/8 | 59.169 | 4349 | 47865 | 16 | 16 | 0 |
| Combined plan, reuse on | 8/8 | 70.233 | 4839 | 85347 | 20 | 20 | 3 |

All 32 artifacts were independently rechecked; usage complete, no timeout or pending turn. Combined plan without reuse was 16.9% faster than native with 38.9% fewer generated tokens in this run. Ordinary plan was slower than native despite fewer generated tokens, due in part to three JavaScript shell-quoting failures. Do not extrapolate one small run to universal performance.

Adding reuse to the identical combined configuration increased whole-task time 18.7%, generated tokens 11.3%, and logical input 78.3%. Final correctness alone hides the failure/repair path. No default switches are changed.

## Repeated-task subset

| Arm (four repeated tasks) | Wall seconds | Generated tokens | Logical input tokens | Requests |
|---|---:|---:|---:|---:|
| Native | 33.642 | 3380 | 31380 | 12 |
| Ordinary plan, reuse off | 43.631 | 2944 | 49035 | 14 |
| Combined plan, reuse off | 28.315 | 2042 | 23821 | 8 |
| Combined plan, reuse on | 25.255 | 1400 | 36889 | 9 |

Content reuse reduced repeated-subset time 10.8% and generated tokens 31.4%, but increased logical input 54.9% and added one repair request. All four repeated tasks selected and actually wrote correct stored content. The selected entry IDs match the first-written source hashes; independent oracles passed on those first-written bytes, before any later repair. JSONL uses the generated short write reference; JavaScript uses the dedicated reuse classification branch. These are different selection paths, not all an additional classifier kernel.

The second JSONL repeat reused correct source but generated invalid Python check syntax (`try` after a semicolon), then repaired the check. Therefore the original whole-plan successful-reuse counter is 3, whereas correct executed content reuses on repeated tasks are 4. JSONL repeat times were 5.563 then 9.039 seconds; JavaScript repeats 5.304 then 5.350. More uses did not monotonically reduce time.

## Changed requirements and cold starts

Changed-task total with reuse enabled was 31.027 seconds versus 15.884 without reuse. JSONL correctly declined reuse but generated a wrong implementation: checking duplicate keys after `json.loads` had already collapsed them. A failed check, file read, and correction increased it to 21.973 seconds. This is a generation error in the presence of candidates, not an executed reuse hit; this run alone cannot causally attribute it to the candidate context.

JavaScript changed requirements were initially served by the old case-sensitive implementation despite the new case-insensitive requirement. Its first-written bytes fail the independent oracle. A check caught the mismatch and the model corrected it, yielding final success after 9.055 seconds. Across all five actual content reuse decisions, four were initially correct and one was wrong. The final 8/8 score must not be called perfect reuse correctness.

Two base-task totals were 13.950 seconds with reuse enabled and 14.970 without it, but neither reused content. That difference cannot be credited to cache hits. The second language's base task had unrelated Python candidates in the shared arm book; it generated new JavaScript.

The current evidence supports real repeated-content savings, but not reliable net acceleration across changing requirements. Remaining priorities are semantic applicability and the cost of candidate context and generated checks. Recovery admission records execution-observed final bytes, not semantic certification. Logical input counts are not physical prefill work.

Validation: 558 tests passed after harness changes; runtime flags asserted for every plan request; all final outputs and all eight first-written contents in the reuse arm audited separately; frozen archives verified. No service restart, deployment, user book reset or push. Full metrics, phase totals, selected IDs and direct-content oracle outcomes are in `COMBINED_REUSE_EVALUATION.json`.
