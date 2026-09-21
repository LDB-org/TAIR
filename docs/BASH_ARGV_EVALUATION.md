# Optional bash argv evaluation

2026-09-21. Frozen experiment: `results/experiments/bash-argv-ablation-20260921-a`.
Machine: Yuesheng, six RTX 5090 GPUs (read-only inventory confirmed after run), existing model service on loopback 8000; no deployment or restart. Pi 0.85.1. Sequential paired evaluation, one active task at a time; seed 731 arm ordering. Six tasks: Python JSONL and JavaScript uniqueStrings, each base/repeat/changed. This is a small single run, not a general speed guarantee.

Both plan arms disable codebook reuse, start with isolated empty books, and retain learning. All other optional planning experiments are off. Both use the same local tokenizer. Native uses its existing multi-tool/prefix-cache path. The difference between plan arms is the optional argv schema and accompanying instruction. Ordinary shell strings remain supported. The native/plan comparison includes their existing protocol and client differences, not only argv.

| Arm | Independent artifact checks | Total wall seconds | Generated tokens | Logical input tokens | Inference requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native Pi | 6/6 | 53.837 | 5456 | 50417 | 19 | 0 | 0 |
| Plan, reuse off | 6/6 | 53.541 | 4111 | 49222 | 14 | 14 | 2 |
| Plan + argv, reuse off | 6/6 | 50.778 | 3589 | 51621 | 14 | 14 | 1 |

All 18 saved artifacts were independently checked again; all usage is complete, no timeouts or pending assistant turns. Wall time sums full client task durations, not pure GPU inference. Logical input counts do not measure physically computed prefill. Classification control records are separate from generated tokens.

Relative to ordinary plan, argv used 12.7% fewer generated tokens and 5.2% less wall time, with 4.9% more logical input tokens and unchanged total requests. Relative to native, argv used 34.2% fewer generated tokens and 5.7% less wall time. Ordinary plan itself was only 0.6% faster than native despite fewer requests/tokens.

The model used argv in every task, nine command steps in total. Ordinary plan's JavaScript repeat and changed tasks each failed once with an unmatched shell quote; argv had no quoting failures. JavaScript total fell from 25.057 to 18.918 seconds. Python total increased from 28.484 to 31.860 seconds: the argv repeat task invoked an invalid-input test without catching the expected JSONDecodeError, requiring another model round. Parameter representation does not fix test logic or semantic compatibility. Natural generations differ, so these pairs are not identical-command causal replays.

Keep `PIJIT_BASH_ARGV` off by default pending broader replication. It is a targeted robustness mechanism with preliminary savings, not proof of universal acceleration. No claim about warm codebook gains follows from this experiment, because reuse was disabled in both plan arms.

Validation: 550 tests passed with pinned Pi in PATH, including real Pi bash argument round trips for quotes, literal dollar expressions, empty arguments and newlines; malformed arrays rejected; first/rest/general branches covered. Backend post-check: health 200, running 0, waiting 0. See `BASH_ARGV_EVALUATION.json` for per-case metrics, adoption and original error records.
