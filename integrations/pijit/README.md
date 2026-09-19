# pijit — local Pi with TAIR inference

An independent launcher for Pi 0.85.1. The original `pi` installation and profile
are unchanged. The custom provider uses engine-side tool classification and
retained-KV argument generation. `reply_user` is selected in the engine and mapped
to a displayed answer by the provider. Tools execute on the local machine.

## Use on this WSL installation

```sh
cd /path/to/your/project
pijit
```

```sh
pijit -p 'Read app.py, change the --workers default to 8 with compact_edit, then test it.'
```

Use `/jit` in the interactive session to inspect the current project's codebook
and session counters. The footer reports generated argument tokens, classification
control records, and compact-edit hits. This is buffered output: completed tool
arguments are validated before dispatch, rather than streamed for early execution.

Request preparation tokenizes messages/continuations and candidate labels in
overlapping pools of at most eight HTTP requests each. Labels no longer wait for all
message tokenization to finish. Token IDs still come from the current server;
prefix preservation and distinct single-token label checks remain mandatory.
This overlaps client preparation only: request/token counts and inference
semantics are unchanged, and shared-engine queueing can still dominate latency.
With `PIJIT_TOKENIZER_REVISION` set to the deployed tokenizer's immutable revision
or file hashes, validated labels are reused across bridge processes under
`PIJIT_STATE_DIR/tokenizer-labels`. The key includes endpoint, model, revision and
label set. Update this value whenever the deployed tokenizer changes; without it,
labels are fetched on every call. Continuation caching is separately opt-in below;
the current conversation is always tokenized.
`label_cache_hit` records reuse separately from edit-codebook hits.

Live evidence in `results/experiments/pijit-preparation-20260918-live/` shows
task preparation median decreasing from 1.55 to 1.00 seconds across six tasks per
arm, with all tasks correct. Full task median increased from 21.18 to 31.86
seconds on the busy shared backend; this is not an end-to-end acceleration claim.
An independent fixed-input remote-tokenizer check measured 0.453 to 0.283 seconds
and verified identical assembled inference payloads across ten pairs.

The launcher creates an ephemeral loopback SSH tunnel to the existing DeepSeek
service, starts Pi, and closes its tunnel when Pi exits. It does not restart vLLM
or create a second model process. Session/profile data is under `~/.pijit/agent`;
per-project codebooks, metrics and source backups are under
`~/.pijit/workspaces/<path-hash>/`. Normal Pi tool permissions still apply; this
is not a sandbox. Source and conversation context are sent to the configured engine.

## Compact edits and the dynamic codebook

`compact_edit(path, task)` reads a Python source snapshot, constructs source-bound
operation schemas, attempts classified codebook reuse, and otherwise requests a
new compact edit. It checks the snapshot again before writing, compiles the new
source, saves a backup and atomically replaces the file. Supported constructs:
keyword/default changes, positional option aliases, function-entry guards, and
catch/return operations. Other languages and unsupported changes use Pi's ordinary
`edit` or `write` tools; their tool selection still uses the engine.

The persistent table learns **typed CLI keyword/alias templates and exact-task
typed edits**. Complete explicit CLI requests supported by `schema_actions.bind_edit`
can reuse a generated template with new integer, float, string or boolean values,
or a new alias. Target, property and value type must match the learned template;
the instantiated edit must match the complete request. Original and resulting
snapshots are registered, including updated selector names after adding an alias.
Entries remain project/file bound. Explicit bindings can also reuse a snapshot
with the same location-free Python AST (ordinary comments/formatting may change);
actual AST changes invalidate it. Current-byte checks still guard every write.

Other supported generated operations, including guards, exception handling and
multi-edit arrays, are retained for the exact stripped task and exact original
source. They do not acquire arbitrary parameter binding or semantic paraphrase
support. Their already-edited result is not registered as another replay input.
Equivalent retrieved actions are deduplicated before the bounded candidate table.
The historical standalone probe and older entry format retain their narrower
behavior; these default-client additions are not retroactive benchmark claims.

Candidates still go through direct classification with NONE. An explicitly bound
matching candidate selected by the model is accepted on the structural match;
the trace records `acceptance_basis=explicit_binding`. A selected exact-task entry
whose task and source match uses `acceptance_basis=exact_task`. Contradictory
bindings or stale exact-task metadata are rejected regardless of score. Other
legacy candidates retain the conditional score >= 0.95 and logprob margin >= 3
gate. These thresholds are heuristic, not calibrated correctness probabilities.
The classification prompt explains the candidate operation fields. NONE still
causes generation; generation that contradicts a complete explicit binding is
rejected before writing. A cold miss always generates before learning; there is
no preseeded correct action. Exact-task reuse inherits its original validation
level and does not prove semantic correctness. Only this nested edit inference can avoid argument
generation; the outer Pi tool call still generates its path/task arguments.

Default admission means **schema + Python compilation**, not semantic correctness.
Generated and cached edits can both be wrong. For stronger local checks, configure
a project command before launching (it is not supplied by model arguments):

```sh
PIJIT_VERIFY_CMD='python3 -m pytest -q' pijit
```

The command runs after each compact edit, with a 90-second timeout. A failure
restores the edited file if it still contains our version and returns a tool
error, without admitting a new entry. The agent can then recover using ordinary
tools. The command's other side effects are not rolled back. A passing project
suite still does not prove that a new task was fulfilled. This live admission
policy differs from the hand-written task oracle in the archived JIT experiment.

## Experimental preset operation

Launch with `PIJIT_PRESET_EDITS=1 pijit` to expose `set_cli_default` alongside
`compact_edit`. The first maintained template is `argparse_int_default/v1`:

```json
{"path":"app.py","option":"--workers","expected_default":4,"value":8}
```

The outer Agent reads the file and generates these arguments. The local preset
performs **no nested model request** and does not classify or admit dynamic cache
entries. Metrics identify its applications by `preset_id`; they are not JIT hits.
It replaces only the existing integer default literal, preserving other bytes,
comments and line endings. It shares snapshot conflict checks, backups, atomic
replacement and optional `PIJIT_VERIFY_CMD` rollback with compact edits.

Version 1 deliberately accepts only a unique literal option name (including an
alias), explicit `type=int`, an observed matching integer default, and a simple
direct `argparse.ArgumentParser` variable binding with `import argparse`. Dynamic
keyword expansion, duplicate targets, nonliteral defaults, shadowed bindings and
unsupported source layouts are rejected. These are bounded syntactic checks, not
proof of arbitrary Python behavior or the user's intent. Unsupported tasks can
use `compact_edit`; rejection itself makes no hidden inference/retry.

The preset is opt-in while evaluated. Its outer tool selection and argument
generation still cost inference; local zero-inference execution is not a claim
that the complete Agent action is free or always faster.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PIJIT_SSH_HOST` | `rs-yuesheng-gpu-vps` | SSH configuration alias |
| `PIJIT_URL` | Automatic SSH loopback tunnel | Existing engine HTTP base URL; skips SSH |
| `PIJIT_MODEL` | `/model` | Model used by tokenizer and classification endpoints |
| `PIJIT_API_KEY` | Unset | Optional HTTP Bearer key |
| `PIJIT_STATE_DIR` | `~/.pijit` | Separate profile and project data |
| `PIJIT_PYTHON` | Repository `.venv/bin/python` | Python with repository test dependencies |
| `PIJIT_VERIFY_CMD` | Unset | Optional local post-edit project checks |
| `PIJIT_DISABLE_CODEBOOK` | Unset | Set to `1` to generate every compact edit without reading or admitting codebook entries; comparison baseline |
| `PIJIT_PRESET_EDITS` | Unset | Set to `1` to expose the experimental `set_cli_default` tool |
| `PIJIT_TOKENIZER_REVISION` | Unset | Immutable deployed tokenizer revision/hashes; enables persistent label cache |
| `PIJIT_SERIAL_PREPARATION` | Unset | Set to `1` for the original serial tokenization waves without label caching; benchmark control |

The engine must already support `/tokenize`, `/v1/openjev/toolcall`, and
`/v1/completions` with the repository's direct-classification patch. This is not
a drop-in client for arbitrary OpenAI-compatible servers. It supports at most
15 ordinary tools plus `reply_user`, text input, and up to 2,048 generated argument
tokens per call. Images fail explicitly. Compact source files are limited to
200 KB and must be inside the current project. Schema support remains subject
to the pinned vLLM/XGrammar implementation.

`metrics.jsonl` records outer calls and nested edit inference separately. Version 2
records include `session_id`, a unique `trace_id`, and the outer tool-call ID for
nested edits. Restart pijit to load the extension's session correlation changes;
old records remain unchanged. Outer-call and nested-call costs both matter.

For compact edits, records include retrieved candidates, task/path and source
match counts, the actual selected candidate (including NONE), candidate scores,
the gate thresholds, and separate rejection reasons for NONE, low probability
and low margin. A gate acceptance is not a successful edit: `cache_hit` is only
true after application and configured verification succeed. Failed validation,
rollback and admission failure retain the earlier decision and spent requests.
Candidate descriptions/edits can contain task text; treat these local logs as
project data, not public telemetry. No HTTP authorization headers are recorded.

`stage_seconds` measures retrieval, lock wait, cache classification, generation,
validation, writing, configured verification (including rollback), and admission.
`generation_preparation` / `generation_http` are **inside** `generation`;
`cache_preparation` / `cache_http` are **inside** `cache_classification`.
Do not add these nested timers together. Per-HTTP records include tokenizer calls,
status and elapsed time; parallel tokenizer durations also overlap. Engine-reported
`classification_seconds` and `engine_seconds` include scheduling/queueing and are
not GPU compute times. `wall_seconds` ends before the final metrics append.

The instrumented engine helper also returns `decision.timing`, retained in HTTP traces
as `classification_timing`: `initial_queue_seconds` and
`scheduled_to_first_output_seconds`, plus their engine monotonic timestamps.
It snapshots these at the classification output, before continuation can mutate
the same engine statistics. Missing, invalid or reordered timestamps yield null,
not zero. These are wall-clock intervals, not GPU kernel times or total queueing
across all resumptions. Older deployed helpers remain compatible and return no
such timing; changing the local helper alone does not activate it on the server.
The 2026-09-18 capacity-8 maintenance test exercised this helper, then restored
the original capacity-4 service and helper after Agent latency regressed. See
[measured results](../../docs/PIJIT_SCHEDULER_TUNING.md).

Caught errors and cancellation now produce a metrics record. `accounting` keeps
known input tokens, generated argument tokens, and classification control records
separate. An inference timeout/error without usage sets `usage_complete=false`
and increments `unknown_usage_requests`; known totals are lower bounds, not a
zero-cost failed request. Forced process termination or a metrics-write failure
can still lose records. These logs are not billing-grade accounting.

### Interleaved C4 comparison

Use an existing tunnel or engine URL, with a new output directory:

```sh
.venv/bin/python benchmarks/compare_pijit_c4.py \
  --url http://127.0.0.1:YOUR_TUNNEL_PORT \
  --out /tmp/pijit-c4-comparison-new --repeats 3 --values 6 8 10 12
```

This makes real inference requests. It uses independent temporary fixture projects
and an empty C4 table per repeat, randomizing arm order within each paired edit.
Both arms receive identical source snapshots. The baseline is C1–C3 generation
with codebook lookup/admission disabled, **not native Pi or unpatched vLLM**.
Cold generation, unsuccessful cache classification, fallback generation, failed
edits, verification and admission all remain in totals. There are no retries.

The fixture verifier checks the exact expected AST before executing the generated
file, then checks the default value and explicit overrides. Both arms use the same
task oracle. This stronger admission policy is specific to the experiment, not
the default live client. The benchmark isolates nested compact edits; it does not
measure outer Pi tool selection or a complete Agent session.

`manifest.json` records the seed and source hashes, `rows.jsonl` preserves every
attempt, and `summary.json` reports both arms including failures. It emits an
observed wall-time ratio only when every pair passes with complete recorded
usage. Even then, shared-server load and this small synthetic workload prevent a
general speed claim. The output directory is create-only; existing evidence is
never overwritten. Exact backend/model revisions must be captured separately
for a publishable reproduction; the served model alias alone is insufficient.

For a **real Pi-loop** comparison including outer inference, read/edit tools,
configured verification and final reply:

```sh
.venv/bin/python benchmarks/compare_pijit_presets.py \
  --url http://127.0.0.1:YOUR_TUNNEL_PORT \
  --out /tmp/pijit-preset-comparison-new --repeats 2 --values 6 8
```

The three arms are compact generation (C4 disabled), dynamic C4, and preset-enabled
Pi with compact fallback available. The Agent chooses the actual tool. This is a
comparison of complete approaches with different tool catalogs, not an isolated
kernel benchmark. Both outer and nested calls, agent recovery and timeouts remain
in the output; unknown usage is marked incomplete. Validated wall time includes Pi
startup, its full loop and the independent final audit; fixture/tunnel setup is
excluded. Every compact/preset edit also runs the same AST/behavior oracle inside the timed
tool path. The workload is a small synthetic integer-default fixture, not a
representative software engineering evaluation.

To compare against **original Pi tool calling** on the same backend:

```sh
.venv/bin/python benchmarks/compare_pijit_presets.py \
  --url http://127.0.0.1:YOUR_TUNNEL_PORT \
  --out /tmp/pijit-native-comparison-new --arms native preset --repeats 3
```

The native arm uses Pi's built-in streaming `openai-completions` provider and
`read/edit` tools. A benchmark-only extension fixes temperature, output budget,
thinking and per-request cache salt, and records usage; it does not replace
the provider or tool implementations. Native calls use the normal tools API of
the **same patched vLLM service**, not a separately deployed unpatched server.
Native prose is retained. This compares entire methods with different tool
catalogs/prompts, transport and output formats, not only the preset transform.

The current runner's summary `wall_seconds` / `median_seconds` include the
identical final AST/behavior audit in both arms (`validated_seconds` per row).
`seconds` / `pi_loop_seconds` retain just the Pi process interval. Preset/compact
edits also keep their in-tool verifier and rollback; native edits remain unchanged
and are checked at task completion. Input accounting adds native `cacheRead` and
`cacheWrite` back to uncached `input`; controls and generated tokens stay separate.
Missing native responses have unknown usage. Runtime auth/model profiles live
outside the archive and are removed after each task.

## Installation elsewhere

Install Pi 0.85.1 and the repository environment (`pip install -e '.[test]'`).
Run `node /absolute/path/TAIR/integrations/pijit/launch.mjs`, or create
a `pijit` shell launcher for that command. The extension uses Pi's documented
[provider and tool extension interface](https://github.com/earendil-works/pi/tree/main/packages/coding-agent/docs),
without patching its core. Automatic extension discovery is disabled for this
profile; additional extensions can be loaded explicitly with `-e`.

### Whole-action classification preparation

`prepare_classification(messages, count)` overlaps prompt tokenization with the
existing revision-bound label cache lookup/fill. Dynamic codebook selection uses
this helper; whole-action callers can reuse it too. Configure a verified
`PIJIT_TOKENIZER_REVISION` to reuse labels across calls. Without a revision, labels
are fetched again; unknown tokenizer identity never permits stale cache reuse.

The exclusive-load [bound-action comparison](../../results/experiments/bound-action-task-20260918-optimized/REPORT.md)
measured 0.693 s complete-task average, versus 1.927 s with serial preparation,
0.982 s for one-shot JSON generation, and 3.616 s for stock Pi. All 40 tasks passed.
This is a finite preset fixture and a specialized one-request workflow, not a
general Agent speed claim. Cold cache fill is included; cold/warm results are
reported separately.

### Schema action prototype

Set `PIJIT_SCHEMA_ACTIONS=1` to use the opt-in schema path for `compact_edit`.
`deploy/schema_actions.py` owns the stable semantic enum and executable codebook.
The bridge compiles `enum: [default, help, required, generate]` to distinct single-token candidate
IDs for the experimental direct-classification endpoint. It does not append the
codebook, enum list, parameter bindings, or candidate edits to the prompt. Source,
task, and a classification question remain model inputs. This is candidate-logit
classification, not ordinary JSON generation or a newly trained classifier head.

The fast path supports explicit atomic argparse default changes with matching
integer, float, string or boolean types, plus existing string `help` and boolean
`required` keywords. Local AST checks bind the option, property, original value and
requested value. Unsupported or compound forms skip classification entirely and
fall back to the generator; ambiguous targets and shadowed parser bindings are
rejected by the local fast path. Successful edits retain
backup, concurrency checks, and configured project verification. Legacy dynamic
codebook retrieval is bypassed in this mode. Ordinary agent tool selection and
fallback argument generation retain their existing prompts; this flag does not
convert the whole agent to schema-only classification.

Acceptance requires conditional probability >= .95, logit margin >= 3, and total
candidate probability mass >= .1, followed by deterministic binding. These are
heuristics, not calibrated correctness guarantees. Relative confidence alone can
be high even when every allowed label is unlikely. Schema validity does not teach
label semantics: the first live prompt failed to route default changes correctly.
The initial v1 development experiment, including unsuccessful probes, is preserved in
`results/experiments/schema-actions-20260918-a`. Its cases are not a held-out general
agent evaluation. Generated argument tokens, control records, input tokens, and
fallback latency are reported separately.


### Learned replay and Agent routing

Enable the integrated experimental path with:

```sh
PIJIT_SCHEMA_ACTIONS=1 PIJIT_JIT_ACTIONS=1 PIJIT_LOCAL_ROUTING=1 pijit
```

The launcher can also be called as `node integrations/pijit/launch.mjs` with these
variables. Flags are opt-in. Ordinary tools remain available for unsupported work.

`PIJIT_LOCAL_ROUTING` recognizes explicit property-change and alias sentences in
the latest user request after the Agent successfully reads a Python file. It routes
a uniquely applicable clause to `compact_edit`, preserving its exact text. With
the default learned codebook it groups up to eight applicable clauses for the same
file into one call; schema/exact-action modes retain one clause per call. It does
not generate an outer tool-call argument payload. Quoted strings stay intact;
negated/compound/unrecognized clauses and ambiguous files go to the ordinary Agent.
An attempted clause is not automatically scheduled again, including on tool error.
Attempt tracking expands previously grouped tasks back into their original clauses.
This is a bounded deterministic dispatcher, not learned general-purpose planning.

`PIJIT_JIT_ACTIONS` stores learned typed actions in each workspace's
`jit-actions.json`, separately from the legacy dynamic codebook. A generated edit
is admitted only after the existing apply/verification guards succeed. A schema
edit can also enter if the typed decoder reproduces its exact result. Each entry
records its task, absolute path, source hash, result hash, concrete edits and actual
validation level. No claim of semantic correctness follows from compile-only
validation. `PIJIT_VERIFY_CMD` adds project validation when configured.

Second-round exact task/path/source matches replay locally, with zero model calls;
this is exact memoization, not a newly trained classifier or fuzzy semantic match.
Replay revalidates scope, typed operations, result hash, concurrent-source checks,
and project checks, retaining backup/rollback. Different source versions, paths or
wording miss. No-op results are not admitted. Generated entries and prewritten
schema templates have separate accounting (`jit_admission_origin`). Disabling the
codebook with `PIJIT_DISABLE_CODEBOOK=1` also disables learned replay.

The repeat benchmark restores original project files before round two, retains
only codebook/tokenizer state, and creates a fresh Agent session. Both baseline
arms also get two rounds, so ordinary warm-state variation is visible. Full task
wall time includes Agent planning, tools, tests, recovery and final reply; a JIT
edit hit does not imply the whole Agent makes zero model calls.

Results: [full Agent cold/warm comparison](../../results/experiments/schema-jit-agent-20260918-b/REPORT.md)
and [matched edit-only control](../../results/experiments/schema-jit-edits-20260918-a/REPORT.md).
The full Agent experiment passed 36/36 tasks, with 12/12 covered second-round
edits replayed; the mixed task set remained slower than native Pi. The edit-only
experiment passed 54/54 checks and separates local replay savings from Agent work.

### Experimental multi-operation plans

`PIJIT_BATCH_TOOLS=1` enables an experimental outer planning path for `read`,
`edit`, `write`, `bash`, and `compact_edit`. The outer model selects either a
final reply or a plan envelope containing 1..8 operations, instead of selecting
each supported tool separately. It emits an operation list
whose arguments must already be known; the model still needs another turn when
discovery changes what to do. Final replies wait for actual execution results.

Pi receives ordinary individual tool calls, with distinct IDs and normal tool
hooks. In this mode the four built-in tools use their standard Pi factories with
sequential execution, and compact edits also execute sequentially. A failed or
blocked step prevents later plan steps from running. Earlier successful edits
are retained: this is not a transaction or whole-plan rollback. The existing
compact-edit codebook remains active; entire plans are not learned or replayed.
The deterministic single-clause outer dispatcher is bypassed in this mode.

This mode is opt-in and requires the tested Pi 0.85.1 execution semantics.

### Outer-loop preparation and directory reads

Two additional opt-in controls target overhead outside learned edits:

For the learned **classification-first** codebook, use this configuration with an
immutable revision covering both tokenizer and chat-template files:

```sh
PIJIT_SSH_HOST=rs-yuesheng-gpu-public \
PIJIT_TOKENIZER_REVISION='<deployed tokenizer and chat-template revision or hashes>' \
PIJIT_CONTINUATION_CACHE=1 PIJIT_DIRECTORY_GUARD=1 PIJIT_LOCAL_ROUTING=1 \
PIJIT_SCHEMA_ACTIONS=0 PIJIT_JIT_ACTIONS=0 PIJIT_PRESET_EDITS=0 PIJIT_DISABLE_CODEBOOK=0 \
node integrations/pijit/launch.mjs
```

Routing removes an outer planning request only for recognized user clauses after
a source read. The inner edit still classifies learned candidates; NONE falls back
to generation and admission. No schema execution or zero-model edit replay is
enabled by this configuration. All controls remain opt-in.

For the separate schema/exact-replay experiment:

```sh
PIJIT_CONTINUATION_CACHE=1 PIJIT_DIRECTORY_GUARD=1 \
PIJIT_SCHEMA_ACTIONS=1 PIJIT_JIT_ACTIONS=1 PIJIT_LOCAL_ROUTING=1 \
node integrations/pijit/launch.mjs
```

Continuation caching also requires `PIJIT_TOKENIZER_REVISION` to identify the
pinned tokenizer/chat-template deployment. The cache key includes endpoint, model,
revision, thinking flags and exact label/instruction tails. Cold preparation checks
that full real-context tokenization and an independent calibration context yield
identical continuation tokens. Context-dependent results are not cached. Warm
preparation tokenizes the current conversation once and appends cached tool tails;
model prompt tokens, candidate IDs, grammar and output budget stay the same.
Cached arrays have shape/type/checksum checks; invalid entries are rebuilt. State
stays in the private runtime directory, not experiment archives. Calibration is an
empirical check of this pinned template, not a proof for arbitrary chat templates.
Update the revision or clear the cache if the deployed template changes.

The directory guard detects a model-selected `read` on a directory within the
workspace and returns a quoted, read-only `bash` listing call when that tool is
available. This prevents an EISDIR error followed by another planning round. File
reads and out-of-workspace paths are unchanged. The original model request and its
usage remain charged; traces retain both original and replacement calls. It does
not fabricate a successful read or hide a failed tool execution.

For paired evaluation, `benchmark_schema_jit_agent.py --outer-comparison` compares
native, previous accelerated, and optimized arms on the same tasks and restored
cold/warm projects. Only the optimized arm enables these two new controls. Cold
calibration cost, normal Agent recovery, tests and replies remain in wall time.

[Outer-loop comparison results](../../results/experiments/outer-agent-20260918-a/REPORT.md):
36/36 task checks passed. Combined cold/warm time decreased 9.3% versus the prior
custom path, but remained 3.1% above native Pi. Covered warm tasks improved;
ordinary logic repair showed regressions and recovery variation. All formal
samples and calibration costs are included.

### Context-aware batch planning (experimental)

**Expanded-test finding:** the deployed xgrammar 0.2.3 rejects legal JSON escapes
when compiling the added `oldText.minLength=1` constraint. This causes repeated
failed edits and severe regressions on broader tasks. The bridge now stops adding
that constraint; empty spans remain rejected by the edit tool at execution.
The repaired mode remains opt-in. A subsequent six-family ablation completed
without timeouts but still failed both CSV tasks; it is not a general correctness
or rollout result. See [single-factor results](../../docs/MECHANISM_ABLATION.md).
[Reproducer and evidence](../../docs/JSON_STRING_GRAMMAR_COMPATIBILITY.md).

`PIJIT_BATCH_TOOLS=1 PIJIT_PLAN_CONTEXT=1` adds a partial workspace-root listing
(up to 64 non-hidden names, no automatic source reads). Edit tools become available
only for paths with a successful read/write result in the current conversation.
In a nonempty project, write is also withheld until the first successful file
observation; an empty workspace still permits creating files immediately.
The edit grammar rejects empty edit lists; the edit executor rejects empty
`oldText`. A planned write to
an unread existing file is replaced by a read; subsequent steps are deferred until
another planning turn. Generated tokens for deferred operations remain charged.

This is a planning aid, not a filesystem permission boundary or freshness proof:
partial reads count as observations, external changes are not tracked, and bash
can still operate on files. The inner learned edit codebook is unchanged. Both
flags default to off. Compare against the previous batch implementation using
`benchmark_codebook_agent.py --plan-context-comparison --tokenizer-revision ...`.

[Initial small-suite context-aware comparison](../../docs/BATCH_CONTEXT_OPTIMIZATION.md): final 36/36 tasks passed;
99.69 seconds versus previous batched 117.24 seconds and native 131.98 seconds.
The failed/slower pilot remains archived separately. Small shared-backend workload only.

### Expanded controlled benchmark

`benchmark_codebook_agent.py --suite expanded --plan-context-comparison --repeats 2`
(with the usual `--url`, `--out`, and pinned `--tokenizer-revision`) runs 120 full
Agent attempts: ten families, two independent repeats, cold/warm pairs, three
arms. Use `--timeout 180` for this suite. It adds cross-file features, nested
packages, CSV parsing, JSON config edits, exception handling, and an 84-file
project with 80 unrelated modules. Before GPU execution, run
`python benchmarks/verify_expanded_scenarios.py` to validate the seven new oracles
against both broken initial fixtures and offline reference implementations.

`python benchmarks/report_expanded_agent.py <out>` requires a complete suite and
reports all-attempt success, latency percentiles, per-family results and the
subset of identical tasks completed by all arms. Failed samples stay in the
all-attempt totals. This is a synthetic workload, not a public coding benchmark
or a production-throughput evaluation.

[Expanded results](../../docs/EXPANDED_AGENT_BENCHMARK.md): all 120 attempts are
preserved. Basic success was native 40/40, prior batched 38/40, contextual 24/40;
additional requested-test audits yield 40/40, 36/40 and 23/40. Contextual took
2229.15 seconds, including eight timeouts. Its minLength/deployed-grammar
incompatibility is independently reproduced; the earlier small-suite gain must
not be generalized to this broader workload.

### Native planner and bound reuse experiments

The new controls are opt-in; they are not a general correctness guarantee:

- `PIJIT_NATIVE_PLANNER=1` keeps ordinary OpenAI tool-call messages and tool
  results for outer planning. Local explicit-clause routing and `compact_edit`
  remain available. Unsupported edits use the ordinary edit/write tools.
- `PIJIT_NATIVE_PREFIX_CACHE=1` gives that planner a stable per-workspace cache
  salt, permitting the server's existing prefix cache. This is a vLLM facility,
  not learned-codebook speedup. Different benchmark arms have separate workspaces.
- `PIJIT_BOUND_REUSE=1` skips model selection only when source-bound retrieval
  yields one candidate exactly matching a supported typed task binding. Cold
  generation/admission remains necessary. Source checks, operation validation,
  compile and any configured project verification still run. Other candidates
  retain the existing classifier and generation fallback.
- `PIJIT_BATCH_LOCAL_ROUTING=1`, together with batch and local-routing flags,
  permits supported clauses to reach `compact_edit` from batch mode.

Aliases that would change argparse's implicit destination are rejected before
compact editing writes a file; use normal editing to retain the original field.
Automatic alias binding additionally requires a recognized argparse receiver.
Unsupported/dynamic parser patterns conservatively fall back.

Cache/timing details remain in tool metadata, traces and the status display;
model-facing compact-edit results contain the applied diff and validation scope.
This avoids changing the planning prompt merely because a cached edit was used.

The completion-check prompt is experimental and opt-in with
`PIJIT_COMPLETION_CHECKS=1`. The failed mandatory verification prototype is
preserved in the pilot archive, not kept as an active completion gate.
See [three-goal experiments](../../docs/THREE_GOALS_EXPERIMENT.md) for evidence,
strong native baseline definitions and limitations.

### Verified dynamic codebook mode

Set `PIJIT_SAFE_CODEBOOK=1` to use conservative learned reuse inside the actual
`compact_edit` bridge. This is opt-in and cannot be combined with
`PIJIT_SCHEMA_ACTIONS=1` or `PIJIT_JIT_ACTIONS=1`; `PIJIT_DISABLE_CODEBOOK=1`
still disables admission and retrieval.

The first request generates an edit. After source checks, decoding, compilation
and any configured `PIJIT_VERIFY_CMD` succeed, the bridge writes a learned entry
atomically to its workspace codebook. A unique applicable learned entry bypasses
model selection; file application and the current verification command still run.

- Fully parsed CLI requests may reuse a learned typed operation with a new value,
  help string or supported alias. The whole request must match the local parser.
- Other edits are admitted in this mode only when a project verification command
  is configured. Reuse requires the exact task, exact source and path, and matching
  recorded verification-command provenance. Generic edits without such a check
  may execute, but are not learned. Old unverified generic entries are not eligible.
- Changed or ambiguous entries miss and generate. Verification failure rolls back
  the write and prevents admission. Changing the verification command invalidates
  generic reuse; existing legacy entries are not automatically promoted.
- A configured test command is not a proof of arbitrary task semantics. It must
  cover the requested behavior; this mode does not infer new tests or guarantee
  that an inadequate project suite detects every wrong generation.

All cache-selection modes now require explicit binding or exact task/source
matching; high classification scores alone no longer authorize a cached edit.
The new mode does not learn arbitrary ordinary `edit`/`write` calls outside
`compact_edit`, does not train model weights, and is not a general semantic cache.

See [the persistent cold/warm experiment](../../docs/SAFE_CODEBOOK_LOOP.md).
