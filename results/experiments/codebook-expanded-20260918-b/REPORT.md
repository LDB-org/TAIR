# Expanded learned codebook: final edit-path evaluation

## Implementation

The default persistent codebook now learns typed single CLI keyword/alias templates
and exact-task typed edit arrays. Explicit CLI requests can rebind integer, float,
string and boolean values or aliases after a successful generated edit. Related
source targets are updated when adding an alias changes a selector's name.

Explicit templates can reuse an AST-equivalent source snapshot, allowing ordinary
comment/format changes. Actual AST changes invalidate them. Exact-task entries
require the original byte-identical source and stripped task; their already-edited
result is not registered as a replay input. Guards, exception handling and multiple
edits can therefore be learned without pretending to generalize their parameters.
Every write still checks current bytes against the inference snapshot.

All reuse still goes through engine classification with NONE. Complete explicit
bindings or exact task/source matches provide an acceptance basis; other legacy
candidates retain the old heuristic score gate. Mismatches are rejected regardless
of score. Operation semantics are included in the candidate prompt. A generated
edit contradicting a complete explicit binding is rejected before writing.
Source hashes are computed once per retrieval and equivalent actions deduplicated.
Admission still inherits the caller's verification: compile-only is not semantic
proof. These experiments configure an independent behavioral check for every edit.

## Evaluation design

11 families: integer default, float default, string default, boolean default, help
text, required flag, alias, conditional return, conditional raise, catch/return,
and multiple keyword edits. Every family has cold, repeated, changed-task/value,
comment-change and actual-code-change phases. Explicit families also have a
continuous edit phase; boolean variants deliberately toggle the previous result.
Two independently empty-codebook repeats yield 124 tasks per arm, 372 total edits.

Arms are native vLLM `oldText/newText` tool calling, the previous optimized TAIR
implementation, and the expanded implementation. Arm order is randomized. A fresh
Python worker executes every task, with isolated old/new imports and codebook
state persisted across workers. Continuous phases use each arm's actual prior
output; reset phases share the declared fixture. All arms use the same behavioral
oracles, temperature zero, fresh request salts, and no retries. No optional schema
actions, preset execution, exact-replay flag or tokenizer label cache is enabled.

This is a hand-authored regression workload, not an independent representative
task distribution. Diagnostic A exposed alias-selector and catch-description
issues, then final B reran the entire workload after fixes. Both are retained.
All endpoints share the existing patched vLLM backend; native calls do not use the
direct classifier. This is not an unpatched-server binary A/B or full Agent test.

## Results

| Metric | Native vLLM | Previous TAIR | Expanded TAIR |
|---|---:|---:|---:|
| Behavioral checks passed | 124/124 | 124/124 | 124/124 |
| Accepted learned reuse | 0 | 18 | 64 |
| Inference requests | 124 | 124 | 124 |
| Generated tokens | 14,328 | 1,416 | 838 |
| Classification control records | 0 | 124 | 124 |
| Input tokens | 55,362 | 60,276 | 45,680 |
| Sum of edit wall time | 141.058 s | 52.581 s | 41.282 s |
| Median edit wall time | 1.117 s | 0.449 s | 0.215 s |
| Sum including fresh worker startup | 150.174 s | 62.338 s | 50.699 s |

Expanded edit wall time decreased 21.5% versus previous TAIR and 70.7% versus native
tool calls (3.42× wall-time ratio). Including worker startup, the decrease is 18.7%
versus previous TAIR and 66.2% versus native. Generated arguments fell 40.8% versus
previous TAIR. Native generation counts include the full serialized tool call;
TAIR argument tokens and classification controls remain separate.

Eight tasks per arm already satisfied the requested boolean value and were AST
no-ops. Excluding those same eight cases leaves 116 changed tasks per arm, with
wall sums 132.709 / 49.093 / 38.689 seconds respectively. The benefit is not solely
due to no-op cases. They remain in the primary totals, with raw before/after source.

| Family | Previous hits | Expanded hits |
|---|---:|---:|
| Integer | 6 | 8 |
| Float | 0 | 8 |
| String | 2 | 8 |
| Boolean | 4 | 8 |
| Help | 2 | 8 |
| Required | 4 | 8 |
| Alias | 0 | 8 |
| Conditional return | 0 | 2 |
| Conditional raise | 0 | 2 |
| Catch/return | 0 | 2 |
| Multiple edits | 0 | 2 |

Real code changes remained misses. Exact-task operations also missed after comment
changes or changed task text. This demonstrates controlled reuse expansion, not
general semantic matching, arbitrary program synthesis, or monotonic acceleration
on every future task. Full Agent behavior is measured separately in the Agent run.

## Evidence and reproduction

`rows.jsonl` includes requests, timings, usage, actual source before/after, behavior
results and candidate decisions. Per-phase books demonstrate cross-process state.
All 248 TAIR inference requests have matching direct-classification worker events;
the environment record reports no missing events. Multiple worker events may refer
to one request and are not counted as separate inference requests. The existing
6×RTX 5090 container was not restarted or patched.

`code.tar.gz` and `environment.json` pin executed sources. The subsequent Agent
routing change modifies only `chat` instructions and the UI/tool description;
edit-path functions remain identical to this executed snapshot. Full Agent runs
preserve their own source snapshots. Tests after the implementation changes:
279 passed in an isolated Python 3.11 environment installed with `.[test]`.

```sh
python benchmarks/benchmark_codebook_expanded.py \
  --legacy-root /path/to/previous-optimized-TAIR \
  --out results/experiments/NEW_EXPANDED_RUN --repeats 2
```

Transfer archive SHA-256:
`151c80090c58bb28597b0172d1a1e61b759ea74b827d764aa8d39cc273f32109`.
