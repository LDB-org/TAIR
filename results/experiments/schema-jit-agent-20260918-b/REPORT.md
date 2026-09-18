# Expanded schema coverage and learned JIT in full Agent loops

Three selected small Python tasks, two independent repeats, three arms, two rounds:
36 completed task attempts, 36 passed external task checks. Native uses stock Pi
on the same patched vLLM server. Generation uses the custom provider and compact
catalog with schema/JIT/local routing disabled. Accelerated enables all three.
This is a small development benchmark, not held-out general coding evaluation.

Each round starts with identical original project files at the same absolute path,
and a fresh Agent session. Round two retains runtime codebook and tokenizer cache,
not prior conversation. Baselines also have two rounds. No action entries were
preseeded. Timing includes Pi process startup, outer model requests, tools, tests,
recovery, final reply and an identical external behavior oracle. Fixture creation
and source restoration are excluded. Tests that must remain unchanged are checked.

| Task | Accelerated first round | Accelerated second round | Native second round | Generation second round |
|---|---:|---:|---:|---:|
| Five CLI properties | 11.659 s | 9.445 s | 9.348 s | 11.094 s |
| Add CLI alias | 9.209 s | 8.646 s | 7.845 s | 9.698 s |
| General summary bug | 14.054 s | 16.336 s | 14.634 s | 13.333 s |
| Equal task mix | 11.641 s | 11.476 s | 10.609 s | 11.375 s |

Mean of two repeats per task/round. First-to-second full-task time decreases 19.0%
for properties and 6.1% for alias; ordinary Agent variation remains substantial.
Overall decreases only 1.4%, and second-round accelerated is 8.2% slower than native.
The general summary task has no learned-action coverage and remains stock edit/
write work. These data do NOT establish a general Agent speedup.

## What actually learned and hit

Across two independent workspaces per covered task, first round admitted 12 records:
10 schema-selected property actions (float/string/bool defaults, help, required),
and 2 previously generated alias actions. Second round hit all 12/12 routed edit
calls. Four of six accelerated second-round tasks used JIT; the two summary tasks
did not. A 100% edit-hit rate must not be reported as universal task coverage.

All 12 JIT hits made zero HTTP/model requests, generated zero argument tokens,
and emitted zero model classification control records. Full Agent planning,
reads, tests and replies still invoke the model. Sampler-bypass audit independently
verified 159 inference classification requests in this benchmark (audit.json).

Inside covered compact_edit tools, total property-edit time per task went from
3.2023 s to .1027 s; alias edit went from .9345 s to .0188 s. These are edit-only
intervals, not full-Agent speed ratios. A separate matched schema-only versus
schema+JIT edit experiment controls the remaining inference cost and includes a
configured AST plus behavior check on every edit.

## Mechanism and limits

The static semantic enum lives in schema; executable templates remain local.
After a successful Python read, a bounded dispatcher recognizes explicit atomic
user property/alias clauses and forwards the exact clause to compact_edit. It
preserves quoted strings, rejects ambiguous files, and does not reroute an already
attempted clause. Other work stays with the ordinary Agent. Source/task remain
model inputs; no expanded codebook table is appended to classification prompts.

Locally unsupported schema bindings skip the extra schema classification. Cold
aliases therefore go straight to compact generation, which still has its own
operation classification. Warm aliases replay the learned typed operation locally.

JIT here is exact task/path/source action memoization, not training, fuzzy semantic
retrieval, or generalization to new source versions. Admission preserves its actual
validation level; Agent tools in this benchmark retain syntax checks, and the
independent whole-task oracle runs afterward. Compile-only admission alone does
not establish correctness on future tasks. Replay rechecks typed scope, result hash,
source concurrency and configured verification with backup/rollback.

A previous prompt-only routing run is retained in ../schema-jit-agent-20260918-a,
including its incomplete final attempt. It was deliberately stopped after seeing
inconsistent compact-tool selection. B sources were held constant throughout all
36 attempts; no service configuration or model weights changed.

The competing proxy and CyberEdge services remain frozen. monitor.jsonl samples
running/waiting counts during most of the run (monitor began after benchmark start).
Snapshots and one-second sampling cannot prove absence of subsecond queue waits.
No server restart or scheduler change was made for these experiments.
