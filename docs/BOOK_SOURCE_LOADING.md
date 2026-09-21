# Load codebook sources after ranking

Candidate retrieval previously selected every entry column, including source text, into the ordered FTS query. Content-book retrieval uses unique-source and eligibility filtering, so it requests the complete ranked result and stops consuming once enough eligible unique entries are found. Large source strings need not participate in that sorting.

The query now returns only entry sequence IDs with exactly the same MATCH, rejection, version, ranking and SQL-limit rules. Full entries are loaded in batches as the existing Python filtering loop consumes them. The first batch equals the requested candidate limit; subsequent batches use 64 entries when filtering exhausts the initial shortlist. SQL fetch order is explicitly mapped back to ranked ID order. Source/identity checks, source deduplication, eligibility and candidate count/order remain unchanged. An explicit read transaction keeps the ranked IDs and subsequent source reads on one SQLite snapshot, including concurrent pruning. There is no schema migration, codebook clearing, prompt change or additional model call.

`benchmarks/profile_book_source_loading.py` compares against the frozen prior implementation on the same temporary synthetic database. It covers 100 and 2,000 entries with approximately 8 KiB source bodies, all contracts matching, 100 distinct source bodies, and a seven-candidate limit. Plain, unique-source, and selective-eligibility cases alternate old/new execution order, discard two warmup rounds, then record ten samples each. Every returned entry dictionary and its order must match exactly. User databases are untouched.

| 2,000-entry case | Old median | New median |
| --- | --- | --- |
| Plain shortlist | 7.00 ms | 3.12 ms |
| Unique source shortlist | 27.13 ms | 3.88 ms |
| Unique + eligibility | 26.17 ms | 4.20 ms |

Detailed samples and source hashes are in `BOOK_SOURCE_LOADING_PROFILE.json`. These are warm local SQLite retrieval measurements, not GPU or full-Agent acceleration. Work still scales with matched entries for ranking; a filter rejecting most entries still needs to load and inspect those sources. No universal constant-time retrieval claim is made.

A regression test uses a real WAL database and prunes the selected entry between ranking and source loading. Retrieval returns the consistent prior snapshot while the subsequent count observes the deletion. This guards the concurrency requirement introduced by the two-query design.

## Sparse-match and short-source stress follow-up

The expanded profiler covers 20 combinations: 100/2,000 entries, 64-byte/8-KiB source padding, and plain/unique/eligible/sparse/all-rejected retrieval. Sparse cases find just one unique eligible candidate; all-rejected cases return none. Every old/new entry dictionary and order still matches.

Per-row lazy reads regressed on 2,000 tiny sources when almost everything was rejected: all-rejected rose from 6.11 to 7.66 ms. `BOOK_SOURCE_LOADING_SIZE_STRESS.json` preserves that result. Batching the initial shortlist and then up to 64 entries removes most query-dispatch overhead without returning extra candidates or accepting unchecked entries. The latest measurements in `BOOK_SOURCE_LOADING_BATCHED_WIDE.json` show:

| 2,000-entry case | Original eager query | Batched lazy query |
| --- | --- | --- |
| Tiny source, all rejected | 5.93 ms | 5.91 ms |
| Tiny source, one eligible unique entry | 6.04 ms | 5.98 ms |
| 8-KiB source, unique shortlist | 26.09 ms | 3.73 ms |
| 8-KiB source, all rejected | 45.44 ms | 24.22 ms |

Tiny-source worst cases are effectively tied, not a demonstrated speedup. Some 100-entry tiny-source cases remain approximately 0.02 ms slower. Batching can load up to 63 entries beyond the eventual stopping point; source integrity and eligibility callbacks still run only as entries are consumed. This is a bounded read-ahead tradeoff, not universal acceleration. Earlier unbatched and fixed-seven batch samples remain in the separate stress/profile JSON files.
