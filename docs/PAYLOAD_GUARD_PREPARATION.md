# Prepare literal payload checks once per retrieval

The Pi bridge previously rescanned the same task text for fenced code blocks inside each candidate's eligibility callback. It now constructs a request-local `payload_guard` once per content-book retrieval and reuses it for candidate checks. Template-book retrieval constructs its own guard. No result is cached across requests, so changed literal requirements are immediately visible.

The regular expression, captured bytes, list membership, newline sensitivity, template decoding, rejection counts, ranking and candidate limit are unchanged. The existing `compatible_payload(entry, task)` helper remains a wrapper for callers that need a one-off check. This is the existing explicit-literal compatibility filter; model classification and semantic applicability decisions are unchanged.

`benchmarks/profile_payload_guard.py` compares against the frozen pre-change implementation. It includes guard construction, alternates execution order, discards two warmups and takes ten measured repetitions. All candidate acceptance decisions match. With a synthetic 20,036-character request:

| Candidates explicitly checked | Repeated scan | Prepared guard |
| --- | --- | --- |
| 24 | 1.289 ms | 0.057 ms |
| 2,000 | 109.594 ms | 0.156 ms |

These are isolated fixed-scan CPU measurements. Real retrieval stops when it finds enough eligible entries, so the 2,000-candidate result is not an ordinary request latency claim. It excludes SQLite, model processing, tools and full-Agent time. Full measurements and source hashes are in `PAYLOAD_GUARD_PREPARATION_PROFILE.json`.

A read-only metadata check of the user's existing content book found 24 entries, 11 distinct source hashes and mean source length 791.25 characters (range 178–4,861). No source text was exported, and the database was not modified. At this size, database retrieval is unlikely to explain the multi-second inference costs observed in earlier experiments; these changes remove repeated local work but do not establish general Agent acceleration.

The new test keeps two independently prepared guards alive with different literals and verifies raw/template acceptance, exact trailing newlines and requests with no literal block. Existing bridge candidate-rejection and ranking tests remain applicable.
