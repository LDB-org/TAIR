# Tool-description deduplication replication

2026-09-21. Frozen runs `tool-description-dedup-20260921-a` and `tool-description-dedup-20260921-b`, six identical fixtures per run, one task at a time. Pi 0.85.1 against the existing Yuesheng DeepSeek-V4-Flash-Vision-Exp service on six RTX 5090 GPUs (TP2/PP3). Both plan arms disable reuse, use isolated empty books and the same local tokenizer. Native uses its original tool protocol. These results compare full paths, not isolated classification-kernel latency.

| Two-run total | Native | Ordinary plan | Description dedup |
|---|---:|---:|---:|
| Final artifact checks | 12/12 | 12/12 | 12/12 |
| Including explicit workflow checks | 12/12 | 11/12 | 11/12 |
| Wall seconds | 125.990 | 102.105 | 93.608 |
| Generated tokens | 12539 | 6999 | 6088 |
| Logical input tokens | 151263 | 111233 | 98575 |
| Inference requests | 54 | 32 | 31 |

The second run independently observed 63.779/50.566/46.265 seconds for native/ordinary/dedup. Ordinary plan violated the repair fixture's explicit check-first instruction in A; dedup violated it in B by reading files before running the checker. All preserved the checker and eventually produced correct artifacts. Neither plan configuration has demonstrated equal workflow reliability to native in these trials. Do not report the aggregate time difference as a quality-matched speedup.

The controlled fixed-input profile proves a 304-token prefix reduction (1236 to 932), with identical option schemas and generation continuations. Actual run totals also reflect different generated code, errors and action sequences. They cannot isolate the latency contribution of those 304 tokens. Dedup remains default off.

## Immediate workflow validation

`benchmarks/workflow_validation.py` now applies explicit fixture metadata before each run's result is printed or aggregated. `artifact_passed` describes final output checks; `workflow_validation` records the specified order and unchanged-file checks; `passed` additionally requires those checks. The repair fixture requires the first tool action (or first plan substep) to run `python3 check_calc.py` and requires the checker to remain unchanged. A preceding read therefore fails even if the final artifact passes.

This validates declared fixture requirements, not arbitrary natural-language semantics. Historical frozen results retain their original `passed` fields. The separate replay audit detects the two historical violations without rewriting evidence. See [workflow audit](WORKFLOW_VALIDATION_AUDIT.json), [replication measurements](TOOL_DESCRIPTION_DEDUP_REPLICATION.json), and [fixed-input profile](TOOL_DESCRIPTION_DEDUP_PROFILE.json).
