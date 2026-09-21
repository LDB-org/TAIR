# Isolate native first-tool classification

2026-09-21. `PIJIT_FIRST_TOOL_CLASSIFICATION=0` removes only native first-action choices from the classification catalog. Codebook candidates, their retrieval limit, general generation and any enabled reply branch remain. Wire selection indices still map back to the original options for continuation and decoding. Recovery is unchanged. Native tool schemas and the eight-step plan remain available inside general generation. This does not add a model round trip or execute tools inside the engine.

Unlike the earlier `PIJIT_REUSE_ROUTING` experiment, this switch does not also lower the candidate limit or repeat the current request in classification and continuation prompts. Default first-tool classification remains enabled. This new switch is experimental.

`--first-tool-ablation` compares native Pi, ordinary plan with reuse disabled, and plan with reuse disabled and native first-tool classification removed. The latter still sends the existing engine request with one general classification branch. No codebook reuse can explain a speed difference in this comparison. Both plan arms learn into isolated initially empty books, but do not offer their content for reuse. Runtime flags are asserted from recorded metrics.

Experiment `first-tool-ablation-20260921-a` uses JSONL parsing, JavaScript deduplication, explicit check-first repair and existing JSON editing. Same existing Yuesheng DeepSeek-V4-Flash-Vision-Exp service, six RTX 5090 GPUs, TP2/PP3, Pi 0.85.1, local tokenizer and one task at a time. Native retains its ordinary multi-tool protocol. The interleaved order uses seed 731; there is one sample per task and arm. No service restart or user codebook modification.

## First run

| Arm | Artifact checks | Including explicit workflow | Wall seconds | Generated tokens | Logical input tokens | Requests | Local tokenizations |
|---|---:|---:|---:|---:|---:|---:|---:|
| Native | 4/4 | 4/4 | 36.741 | 3537 | 46500 | 17 | — |
| Ordinary plan | 4/4 | 3/4 | 35.237 | 2259 | 38453 | 11 | 80 |
| General plan | 4/4 | 4/4 | 28.744 | 1700 | 33570 | 11 | 23 |

Ordinary plan read before the explicitly requested check. Its shorter repair trajectory is therefore not an equal-quality speed win. General plan followed check-first order and was faster than native on all four fixtures in this run. It also avoided one JSONL command error encountered by ordinary plan. Each arm's repair task has one intentionally failed initial check. Final artifacts were independently rechecked; usage is complete and no turn remains pending.

The local preparation total only decreased from 1.381 to 1.280 seconds versus ordinary plan; it cannot explain the entire wall-time difference. Generated output, error recovery and action sequence also changed. This initial result supports replication, not a claim of generic acceleration or a default change. Details: [first-run measurements](FIRST_TOOL_CLASSIFICATION_EVALUATION.json).

## Replication and decision

Run B uses identical source and fixtures in a new workspace with fresh isolated books. It reverses the repair result: ordinary plan follows the requested initial check; general plan first reads both files, edits the implementation and only then runs the check. The faster general repair run is a workflow failure, despite its correct artifact.

| Two-run total | Native | Ordinary plan | General plan |
|---|---:|---:|---:|
| Final artifact checks | 8/8 | 8/8 | 8/8 |
| Including explicit workflow | 8/8 | 7/8 | 7/8 |
| Wall seconds, failures included | 74.222 | 66.780 | 54.686 |
| Generated tokens | 7135 | 4153 | 3250 |
| Logical input tokens | 92619 | 75056 | 62773 |
| Inference requests | 34 | 22 | 21 |
| Local tokenizations | — | 167 | 44 |

All six non-repair runs per arm pass; general plan is faster than both other arms on each of those runs. This is encouraging for creation and JSON editing, but is only three distinct tasks repeated twice. The full suite does not establish native-equivalent workflow reliability. Equal aggregate pass counts for the two plan variants do not make their different failed executions an equal-quality timing comparison. Keep the switch experimental and default first-tool classification enabled.

The test distinguishes two problems: native branch selection can constrain the wrong first tool, and unconstrained plan generation can independently omit an explicitly requested operation. Removing the former does not solve the latter. No confidence threshold or keyword matcher was deployed. Codebook-enabled behavior has only mapping/unit coverage for this new switch; these live runs deliberately disable reuse and cannot establish warm-codebook performance.

Validation: 590 tests passed with pinned Pi in PATH, including candidate/general branch mapping when first-tool classification is disabled. Both runs froze identical runtime sources; all 24 artifacts were independently rechecked. Detailed replication and combined totals: [FIRST_TOOL_CLASSIFICATION_REPLICATION.json](FIRST_TOOL_CLASSIFICATION_REPLICATION.json).
