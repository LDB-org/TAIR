# Dedicated internal reply branch

2026-09-21. `PIJIT_REPLY_BRANCH=1` adds a classification option whose only generated argument is `content`. All public tool calls are still exposed as plan; native tool and codebook branch indices remain unchanged, and a general action-generation branch remains last. The dedicated reply branch is inserted immediately before it. At most 16 classification branches are accepted. No additional model request is introduced. Existing recovery uses the full general branch; this first experiment does not optimize recovery replies.

Motivation: across the preceding two argv experiments, ordinary plan made 30 model requests for 12 tasks; 12 were final replies, using 45,948 logical input and 1,988 generated tokens, and 25.55 seconds of inference HTTP time. Those replies used an action-or-content schema containing the full inner-tool catalog. Their input is not all removable: history and classification context are still needed.

## Paired real-service evaluation

Frozen source/evidence: `results/experiments/reply-branch-ablation-20260921-a`. Four tasks: JSONL creation, JavaScript string deduplication, JSON field edit, and SQLite nullable grouping. Existing Yuesheng model service, six RTX 5090 environment, Pi 0.85.1, sequential tasks, shuffled arm order seed 731. Both plan arms start with isolated empty books, disable reuse, retain learning and use the pinned local tokenizer. Other optional switches (argv, parallel capabilities, capability caching, conditional completion) are off. Native retains its standard multi-tool/prefix-cache behavior. No service restart or user codebook modification.

| Arm | Correct | Wall seconds | Generated tokens | Logical input tokens | Requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native | 4/4 | 44.603 | 4446 | 53600 | 19 | 0 | 0 |
| Ordinary plan | 4/4 | 28.491 | 1902 | 30802 | 9 | 9 | 0 |
| Dedicated reply | 4/4 | 26.682 | 1763 | 26017 | 9 | 9 | 0 |

All 12 saved outputs passed independent rechecks, usage was complete and there were no timeouts or pending turns. Dedicated reply was selected in all four final replies. No action turn selected it. Relative to ordinary plan, total time fell 6.3%, generated tokens 7.3%, and logical input 15.5%; request count stayed unchanged. The much larger gap versus native includes existing plan batching and different generated work, so it is not attributable solely to this change.

| Final replies only (four per plan arm) | Logical input | Generated tokens | Inference HTTP seconds |
|---|---:|---:|---:|
| Ordinary general branch | 14882 | 659 | 8.558 |
| Dedicated reply branch | 10034 | 388 | 5.953 |

Final-reply input fell 32.6%, generation 41.1%, HTTP time 30.4%. Whole-task gains were smaller because earlier action generations also changed. JavaScript task time increased slightly (7.006 to 7.235 seconds). These are single samples of four tasks, not a stable universal acceleration guarantee. Logical input counts do not measure physical prefill; classification controls remain separate from generated tokens.

Keep default off until larger and failure-oriented tests check for premature reply selection. A mistaken reply classification cannot generate action steps within that branch; the presence of other branches does not itself guarantee correct selection. This is an optimization of completion generation, not automatic completion from tool exit codes, nor elimination of the final model turn.

Validation covers reply schema rejection of steps, preservation of native/general/reuse decoding, classification mapping with optional reuse routing, and unchanged recovery selection. Source stayed fixed throughout inference. Test and archive checks run after changes; post-run backend health 200, running 0, waiting 0. Detailed metrics and each turn's selected branch are in `REPLY_BRANCH_EVALUATION.json`.
