# Deduplicate native tool descriptions

2026-09-21. Generic plan policy already includes the complete Pi native tool descriptions under `INNER TOOLS`. Native-action classification labels repeated those descriptions. The optional `PIJIT_DEDUP_TOOL_DESCRIPTIONS=1` replaces only that second copy with `First action <name>. See INNER TOOLS above.` Candidate data, current/historical task text, candidate count, schemas, native branch indices and generation continuations remain unchanged. Recovery and reuse-only routing have no native-action catalog entries to shorten.

## Fixed-input evidence

`benchmarks/profile_tool_description_dedup.py` uses the frozen real Pi 0.85.1 catalog and pinned tokenizer with one identical task context. It asserts exact equality of option objects (including schemas), continuation messages and continuation token lengths between arms. No inference or tools execute. Prefix tokens drop from 1236 to 932: 304 fewer tokens. Selected continuation lengths remain 1331–1477 tokens. This count is the demonstrated mechanism, not a latency estimate. Profile and source hashes: `TOOL_DESCRIPTION_DEDUP_PROFILE.json`.

## Real-service evidence and quality boundary

Frozen experiment: `results/experiments/tool-description-dedup-20260921-a`. Six tasks: Python JSONL, JavaScript deduplication, required failure-first repair, CSV parsing, existing JSON editing, and SQLite nullable grouping. Existing Yuesheng six RTX 5090 service; Pi 0.85.1; one task at a time; seed 731 interleaved arm order. Both plan arms use isolated empty books, reuse disabled, same local tokenizer, other optional features off. No service restart, deployment or user codebook modification.

| Arm | Artifact checks | Explicit workflow checks included | Wall seconds | Generated tokens | Logical input tokens | Requests | Classification controls | Tool errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Native | 6/6 | 6/6 | 62.211 | 6127 | 78542 | 28 | 0 | 1 |
| Ordinary plan | 6/6 | 5/6 | 51.539 | 3525 | 55800 | 16 | 16 | 2 |
| Description dedup | 6/6 | 6/6 | 47.343 | 3138 | 47953 | 15 | 15 | 1 |

All 18 final artifacts passed independent checks, but ordinary plan read `calc.py` before the user's explicitly requested initial `python3 check_calc.py`. Native and dedup followed check-first order. All preserved the checker. Therefore this is NOT a strict equal-quality speed comparison. The ordinary plan's shorter repair trajectory must not be treated as superior performance while ignoring its workflow violation.

Observed total time is 8.1% lower and logical input 14.1% lower for dedup versus ordinary plan. Generated output, chosen steps, request count and errors differ; the fixed-input 304-token reduction does not explain all of those changes. Repair and JSON-edit tasks were slower with dedup, while creation/SQL tasks were faster. The required initial failed check accounts for one tool error per arm; ordinary plan has one additional error. Usage is complete, with no timeout or pending turn.

Keep default off pending broader repeated tests. This is a lossless removal of duplicated tool-description text at the data level, not a guarantee of invariant model behavior. It does not shorten stored source, resolve semantic codebook applicability, or prove generic net acceleration. Existing prompts still allow the model to choose an incorrect action sequence.

Validation: 570 tests passed, including schema/continuation equality and catalog mapping for normal, recovery and reuse-only routing. Source stayed fixed during the real run; runtime flags were asserted. Independent artifact and workflow checks are recorded separately. Frozen archives verified and post-run backend health/idle checked. Detailed report: `TOOL_DESCRIPTION_DEDUP_EVALUATION.json`.
