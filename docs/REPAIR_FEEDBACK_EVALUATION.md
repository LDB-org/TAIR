# Repair feedback: live Agent evaluation

2026-09-21. Frozen run: `results/experiments/repair-feedback-ablation-20260921-a`. Existing Yuesheng six RTX 5090 service, Pi 0.85.1, pinned local tokenizer, one task at a time, seed 731 shuffled arm order. Each arm starts with its own empty book; workspace files reset before every task. User books and services are unchanged.

Eight tasks per arm: Python JSONL and JavaScript uniqueStrings, each base, changed requirement, then two repeats of that exact changed request. Repeat prompt, filename, initial files and oracle are identical. Both plan arms enable argv, reply branch, write references, recovery admission and reuse; only `PIJIT_REPAIR_FEEDBACK` differs. Runtime flag assertions passed for every request. Native retains ordinary multi-tool behavior.

| Arm | Final checks | Wall seconds | Generated tokens | Logical input tokens | Requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native | 8/8 | 84.494 | 8647 | 83716 | 30 | 0 | 0 |
| Combined, feedback off | 8/8 | 60.152 | 3972 | 78510 | 18 | 18 | 2 |
| Combined, feedback on | 8/8 | 73.120 | 5059 | 89822 | 21 | 21 | 4 |

All 24 saved final artifacts independently rechecked, usage complete, no timeout or pending turn. Feedback-on total was slower, not an acceleration result. Its cold JSONL task required three tool-error recoveries and 21.644 seconds versus 8.935 for the control. No content was reusable or rejected at that point. Differing generated actions and repairs confound a causal attribution of this total difference to feedback; the regression is still included in all totals.

## Mechanism audit

Both plan arms initially reused wrong case-sensitive content for the JavaScript case-insensitive changed request. Independent checks of the first-written bytes fail for both. Both repaired the content and eventually passed. Only the feedback arm recorded the old entry plus SHA-256 of the exact changed task in the existing `rejections` table. The isolated database was opened read-only after the run; its entry inventory matches the frozen final-book inventory. There is exactly one rejection row, and no feedback errors.

On both subsequent repeats, the feedback arm's actual candidate IDs exclude the old source. The control arm still offers it. Both nevertheless choose correct new content, with no tool failures in these repeated tasks. The final-source and first-written-content audits distinguish successful recovery from initially correct reuse. Candidate exclusion is proven; an avoided repeated error is not, because the control also chose correctly.

Python changed requirements generated correct fresh source and did not trigger feedback. Its two repeats correctly reused the new source in both arms. Across all four repeats, both arms have four correct initial content reuses and four successful final outputs.

| Four repeated changed requests | Wall seconds | Generated tokens |
|---|---:|---:|
| Native | 45.389 | 4670 |
| Combined, feedback off | 24.858 | 1506 |
| Combined, feedback on | 24.553 | 1462 |

The 0.305-second aggregate difference (1.2%) is too small and confounded to call a demonstrated feedback speedup. Only the two JavaScript repeats exercised a nonempty rejection set. Normal content learning/reuse, batching and the existing optimizations account for other potential differences versus native; this run does not isolate each.

Keep repair feedback off by default. It now has live evidence for recording an observed repair and excluding the replaced bytes on the same request, but cannot prevent the first wrong hit, cannot equate a successful check with semantic correctness, and has no proven net latency advantage. It also will not match paraphrased requests. Further testing should expose competing stale entries and check whether rejection actually avoids an error, not merely whether the rejection table contains a row.

Validation: 566 tests passed after trace/harness changes; runtime configuration checked, all final artifacts and first-written content in plan arms audited, rejection row and subsequent candidate lists cross-checked, frozen archives verified. Post-run backend health/idle checked separately. Detailed evidence: `REPAIR_FEEDBACK_EVALUATION.json`.
