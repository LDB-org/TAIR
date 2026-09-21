# Dedicated reply branch: expanded evaluation

2026-09-21. Frozen run `results/experiments/reply-branch-expanded-20260921-a` extends the initial four-task evaluation with changed JSONL requirements, failure-first repair, CSV parsing, Unicode normalization, a changed existing JSON configuration, and padded-list chunking. The same runtime source was used; no implementation changes were made this turn.

Existing Yuesheng six RTX 5090 service, Pi 0.85.1, one task at a time, shuffled arm order seed 731. Isolated initially empty books; both plan arms disable reuse and use the same pinned local tokenizer. Other optional switches are off. No service restart, user codebook reset or deployment.

| Arm | Independent artifact checks | Wall seconds | Generated tokens | Logical input tokens | Requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native Pi | 6/6 | 58.752 | 5864 | 66147 | 24 | 0 | 1 |
| Ordinary plan | 6/6 | 51.002 | 3597 | 51389 | 15 | 15 | 1 |
| Dedicated reply | 6/6 | 50.156 | 3513 | 45906 | 15 | 15 | 1 |

All 18 saved artifacts passed independent rechecks. Usage complete; no timeout or pending assistant turn. The one tool failure per arm is the requested initial failing check in the repair task, not an unexpected regression.

## Completion and workflow audit

The reply option was selected for five final replies and never for an unfinished action turn in this sample. The repair task entered recovery and retained the original general branch; its final reply also used recovery. This is not evidence that the dedicated branch improves recovery, because that branch was unavailable during recovery.

All three repair runs executed `python3 check_calc.py` first and left the checker unchanged. Both plan arms in the JSON edit task used a read-only first plan, then mutation plus validation in a second plan, then final reply. The optimized arm used edit; ordinary plan used write. Both preserved all fields under the independent oracle. Native also read before modifying and checked afterward. The saved turn audit records selected branches and step names for every plan request.

Final replies alone used 22,751 input / 884 generated tokens and 11.756 inference-HTTP seconds for ordinary plan, versus 16,924 / 850 / 11.311 for the candidate. Including unchanged recovery behavior, final input decreased 25.6%, but generated tokens and latency declined only slightly. Whole-task time improved just 1.7% this run, versus 6.3% in the first run. Repair and Unicode normalization were slower with the candidate.

## Combined descriptive totals

| Arm | Correct | Wall seconds | Generated tokens | Logical input tokens | Requests |
|---|---:|---:|---:|---:|---:|
| Native | 10/10 | 103.355 | 10310 | 119747 | 43 |
| Ordinary plan | 10/10 | 79.493 | 5499 | 82191 | 24 |
| Dedicated reply | 10/10 | 76.837 | 5276 | 71923 | 24 |

Combined candidate versus ordinary plan: 3.3% less wall time, 4.1% fewer generated tokens and 12.5% fewer logical input tokens, with unchanged requests. Both plan arms use 24 classification controls, separate from generated tokens. Native differences include the pre-existing batching protocol and different generated actions; they cannot be assigned solely to the reply option. Logical inputs are not physical prefill compute.

These are ten different tasks sampled once per arm, not repeated trials with confidence intervals. No premature completion was observed, but this does not establish safety for arbitrary tasks or histories. Keep the option off by default; the reliable mechanism demonstrated is reduced final-reply schema input, while end-to-end benefit remains small and variable. No warm-codebook acceleration was tested.

Validation: all saved artifacts rechecked, explicit workflows reviewed, archived checksums verified separately. Runtime remains at the previously validated 558-test state; no code changed. Post-run backend health/idle was checked. Full per-task and per-turn evidence: `REPLY_BRANCH_EXPANDED.json`.
