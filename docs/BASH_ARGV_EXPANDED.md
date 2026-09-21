# Bash argv: expanded task evaluation

2026-09-21. Frozen source and evidence: `results/experiments/bash-argv-expanded-20260921-a`; detailed metrics and original errors: `BASH_ARGV_EXPANDED.json`.

Same deployed Yuesheng model service and six RTX 5090 environment as the first argv experiment; Pi 0.85.1. One task at a time, randomized arm ordering with seed 731, full client wall timing, isolated initially empty books. Both plan arms disable reuse while retaining learning and use the local tokenizer. No service restart or user codebook modification. Native retains its multi-tool/prefix-cache path. Six additional tasks cover failure-first repair, CSV parsing, Unicode normalization, existing JSON edits, and two SQLite grouping requirements.

| Arm | Artifact and explicit workflow checks | Wall seconds | Generated tokens | Logical input tokens | Requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native | 6/6 | 59.835 | 5752 | 82889 | 30 | 0 | 2 |
| Plan, reuse off | 6/6 | 51.495 | 3514 | 55463 | 16 | 16 | 2 |
| Plan + argv, reuse off | 6/6 | 45.362 | 2806 | 58561 | 16 | 16 | 2 |

All 18 saved outputs passed independent rechecks. Usage complete; no timeouts or pending assistant turns. Each repair task deliberately begins with a failed check, counted in tool errors. All arms actually ran that check first and preserved the checker. The summary evaluator now recognizes the bridge's exact `command --` prefix before checking the requested command; no frozen evidence changed.

The new option was used in all six tasks, eight argv steps total. Ordinary plan's changed SQL case had an unmatched shell quote; argv did not. Native's changed SQL case tried unsupported macOS `cat -A`, causing a repair round. The argv CSV case generated invalid Python syntax (`try` after a semicolon) and needed recovery. Thus neither all native/plan timing differences nor all argv gains can be assigned solely to quoting.

## Combined descriptive totals

These combine the first six tasks and the six new tasks, not repeated trials of every fixture. They are descriptive totals, without confidence intervals or a claim of stable performance across arbitrary agents/models.

| Arm | Correct | Wall seconds | Generated tokens | Logical input tokens | Requests |
|---|---:|---:|---:|---:|---:|
| Native | 12/12 | 113.673 | 11208 | 133306 | 49 |
| Plan, reuse off | 12/12 | 105.036 | 7625 | 104685 | 30 |
| Plan + argv, reuse off | 12/12 | 96.140 | 6395 | 110182 | 30 |

Combined argv versus native: 15.4% less time, 42.9% fewer generated tokens. Versus ordinary plan: 8.5% less time, 16.1% fewer generated tokens, 5.3% more logical input tokens and unchanged requests. Ordinary plan versus native: 7.6% less time and 32.0% fewer generated tokens. Classification controls remain separate (30 in each plan arm). Logical input is not physical prefill work. Neither trial measures warm-codebook acceleration.

The improvement is promising across more than JavaScript, but not uniform: argv was slower than ordinary plan on repair, CSV, and JSON editing in this run, and all three Python JSONL cases in the first run. Retain the default-off switch pending replication and broader workloads. This change addresses shell representation; generated program syntax, test correctness, and semantic codebook selection remain separate issues.

Validation: full repository tests and frozen archive verification; backend post-run health/idle checked separately. Runtime source unchanged during inference. Only the summary evaluator was adjusted after the run.
