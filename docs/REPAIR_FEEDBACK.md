# Task-specific feedback from repaired content

2026-09-21. `PIJIT_REPAIR_FEEDBACK=1` connects generic tool-plan content reuse to the existing SQLite rejection table. Previously generic content retrieval passed an empty contract map and did not consult task-specific rejection records; generic failed-plan execution also did not record repaired old content.

## Implemented boundary

On a model final reply, inspect only the current user turn and correlate each plan call with its tool result. Require consistent completed-step prefixes. A candidate old version must have been written in a plan whose later bash step failed. The same normalized workspace path must then have an explicitly completed write/edit in a successful plan, and the latest completed plan must include a successful bash call. Pending calls, unmatched/malformed results, another failure, a read-only last result or a new user turn prevent feedback. Observe the actual final file, bounded to 1 MiB, and require changed bytes.

Only matching existing source bytes are recorded as rejected for the exact current task text. Candidate retrieval consults the task's rejected source hashes before deduplication/shortlist selection; adding the same source under another entry identity does not bypass it. Original entries and other task requests remain intact. Existing database schema/version and content identity rules are unchanged. The mechanism does not parse words like read or case-insensitive, and does not execute a new model request.

This is evidence that a version was replaced after a failed check, not an independent proof that the version was semantically wrong or that the replacement is correct. An unrelated failing check followed by a content change can cause an unnecessary miss. Restricting feedback to exact task text and making it opt-in limits the scope; it does not solve general semantic compatibility. It cannot prevent the first wrong hit or recognize paraphrased requirements. Turning the option off disables both learning and the additional retrieval filter.

## Offline replay of real histories

`benchmarks/replay_repair_feedback.py` uses frozen histories from `combined-reuse-ablation-20260921-a`, copies final artifacts into a temporary workspace, and seeds an isolated book with the original base content. It performs no inference or new Agent execution. Independent oracles recheck the copied final artifacts.

| Recorded task | Observed outcome | Feedback result |
|---|---|---|
| JavaScript changed case sensitivity | Old source reused, assertion failed, source edited, checks passed | Old bytes excluded for that exact changed request; still available for original request |
| Second JSONL repeat | Correct source reused, only test command repaired | No rejection; source remains eligible |
| JSONL changed duplicate-key handling | New generated implementation failed and was edited | No rejection of unrelated stored base bytes |

The JavaScript case also adds the rejected bytes under a fresh contract/entry ID; they remain excluded for the rejected task. The other request still sees them. This verifies persistent feedback and alias resistance, not a cache hit, model selection, or latency improvement. Machine-readable evidence and source hashes: `REPAIR_FEEDBACK_REPLAY.json`.

Tests cover scoped exclusion, disabling the filter, duplicate sources, unrelated tasks, no repair yet, check-only repair, external content changes without explicit mutation, new user turns, pending calls, read-only last results, malformed results and final failed checks. No actual user book was read or modified; the flag remains off by default. A live repeated-changed-task ablation is still needed before claiming acceleration.
