# pijit — local Pi with TAIR inference

For the general single-plan interface, launch with `--plan-only`; see [generic plan](../../docs/GENERIC_PLAN.md).

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

## Optional local preparation for a pinned DeepSeek V4 deployment

`pip install -e '.[tokenizer-client]'` installs only the optional CPU tokenizer dependency.
`PIJIT_LOCAL_TOKENIZER=/trusted/snapshot` enables local text tokenization;
`PIJIT_TOKENIZER_REVISION` must be the SHA-256 of that snapshot's `manifest.json`.
The manifest format is `tair-deepseek-v4-text-v1`, with `client_tokenizers_version`
and `files` mapping `tokenizer.json` and `encoding.py` to SHA-256 digests.
Copy these files from the actual deployment (the latter is vLLM's
`tokenizers/deepseek_v4_encoding.py`), retaining its license notice. The snapshot
contains trusted executable renderer code: do not use an untrusted snapshot.
Keep model files and tokenizer snapshots outside this repository.

The client checks manifest/file digests and its tokenizer library version on load.
Set `PIJIT_LOCAL_TOKENIZER_VERIFY=1` to compare every locally prepared token sequence
with the deployment's `/tokenize` result before inference; a mismatch stops the
request. Disable this shadow check only after validating the deployment snapshot.
The snapshot is deployment-specific, not a live server identity check: revalidate
it whenever the deployed tokenizer, renderer or engine preprocessing changes.

This opt-in adapter handles the existing non-thinking text messages and labels.
Unsupported payloads use the original remote tokenizer. Other models retain the
original path; no model weights are loaded on the client. `local_tokenization`
records CPU time, token counts and shadow equality separately from HTTP calls.
Neither prompts, candidate contents, generated schemas nor engine KV-cache
settings are changed by local preparation. The default engine cache salt remains per-request; local preparation alone does
not change it. Session-level prefix caching is a separate opt-in below.

## Session-level prefix caching

`PIJIT_PREFIX_CACHE=1` lets the generic plan path request a stable KV-cache salt
within one Pi session and workspace, after negotiating `prefix_cache_version=1`
with the engine. State directory, backend URL and model also participate in the
namespace. The request ID remains unique. Missing session/workspace identity or
an older server keeps the original per-request isolation, with a trace reason.
No cross-session sharing or user codebook clearing is performed.

The engine endpoint accepts an optional `cache_salt` of 1–128 characters; omitted
means the original per-request salt. `decision.cached_prefix_tokens` reports the
engine's cached-token count at the initial classification output, separately from
logical input tokens and request timing. `prefix_cache_mode` confirms the actual
server mode. This is vLLM KV reuse, independent of dynamic content-codebook hits.
Candidate changes and altered prompt prefixes can still prevent reuse.

See [the session-cache experiment](../../docs/SESSION_PREFIX_CACHE_EVALUATION.md)
for the exact deployment, fixed-input controls and Agent quality results. This
option does not enable speculative decoding or train a model.

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

### 外层规划效率（可选）

在 `PIJIT_NATIVE_PLANNER=1 PIJIT_BATCH_TOOLS=1` 的混合路径中，设置
`PIJIT_PLANNER_EFFICIENCY=1`：

- 对用户消息开头明确的 `Read relative/file.py.`，若文件存在、位于当前项目内且不超过 200 KB，直接发出 read 工具调用，省掉决定这次读取的模型请求。缺失文件、越界路径、symlink 越界或无法严格解析的句式仍交给模型；不会跳过读取结果或失败处理。
- 给原生规划器提供工作区根目录及最多 64 个根条目，并提示直接读取用户指定的文件、搜索限制在工作区、合并已确定的操作和必要检查，避免无变化时反复检查。
- 提示 pytest 使用 `-p no:cacheprovider`、临时数据放临时目录，减少无关项目产物。

默认关闭。搜索范围和检查合并属于规划提示，不是 shell 拦截器或操作系统沙箱；用户明确要求搜索外部位置时提示允许该范围。读取直达为确定性代码路径，其余行为需要用轨迹验证，不能保证消除所有冗余调用。不会自动跳过语义验证或因码表命中提前结束任务。

实测对照见 `docs/PLANNER_EFFICIENCY.md`；测试入口增加 `--planner-efficiency` 和
`hybrid_unoptimized` 对照组，后者保持码表开启、仅关闭外层效率开关。

原生规划器的单次生成上限可用 `PIJIT_PLANNER_MAX_TOKENS` 配置，默认 2048。
从零生成长文件时需要留够输出预算，例如 8192；这不是总任务 token 上限。
对照测试的原生跟踪器用 `TAIR_NATIVE_MAX_TOKENS` 设置相同预算。

### Verified new-module plan mode (opt-in)

`PIJIT_ADAPTIVE_PLAN=1` with `PIJIT_NATIVE_PLANNER=1` enables a **new Python module creation mode**. The first assistant request is constrained to the `plan` tool; the model supplies the task and full per-module contracts. Later turns use ordinary tools for inspection, checks, error recovery and the final answer. Do not enable this mode indiscriminately for existing-file edits or unrelated tasks. It does not alter the default Pi workflow.

Configure a trusted validator through an operator-owned JSON argv array:

```sh
export PIJIT_NATIVE_PLANNER=1
export PIJIT_ADAPTIVE_PLAN=1
export PIJIT_PLAN_VERIFY_ARGV='["/absolute/venv/bin/python", "/absolute/project_validator.py"]'
```

The runtime appends `candidate_path`, `contract`, and `workspace` to this command, with the real workspace as cwd. The validator must check the candidate against the original task/project requirements and exit nonzero on failure. A model-written test suite or a successful compile alone is not a trusted acceptance criterion. Verification is mandatory for both generated and reused code; no validator means no plan execution. The verifier executes locally and is not an OS sandbox. Context-dependent imports may be resolved from the workspace argument.

Successful complete plans publish only new files and automatically admit generated modules. Workspace state contains `plan-codebook.sqlite3`, with no default entry-count eviction, an FTS5 index, verified reuse statistics, and contract-scoped rejection records. Legacy `plan-codebook.json` and rejection records are imported once without modifying the originals. Indexed lexical retrieval chooses at most 15 candidates; it does **not** decide reuse. The engine classifies the candidates plus GENERATE, retains KV, and generates the remaining plan parameters. One plan still selects at most one reusable entry; other outputs may be generated.

A trusted verification failure rejects an attempted reuse for that contract and permits **one** additional inference forced to generation. Both attempts are charged and recorded. A second verification failure stops without admitting the plan. Shape/path/transport errors are surfaced to the outer Agent instead of being silently retried. Multi-file publication is not a filesystem transaction.

`PIJIT_PLAN_DISABLE_REUSE=1` is the ablation/control: same outer plan policy and validation, but inner inference always generates. It still persists validated code, allowing comparison of reuse with the outer policy held fixed. Model-generated contract descriptions can differ across calls; the current retrieval and rejection cache are bounded engineering mechanisms, not a universal intent or semantic equivalence solver.

SQLite storage, migration, explicit retention maintenance and local scaling measurements: [indexed plan book](../../docs/PLAN_BOOK_STORAGE.md).

### Generic single-plan mode

`--plan-only` now means **general Pi tools inside one public plan**, without a
fixed task validator or Python-only restriction:

```sh
node /absolute/TAIR/integrations/pijit/launch.mjs --plan-only
```

The existing fused engine classifies the first native operation, an applicable
stored-content entry, or a final reply. It generates the remaining plan in the
same request. Pi receives only `plan({steps:[{name,arguments}, ...]})` and executes
native read/write/edit/bash/grep/find/ls implementations locally, sequentially,
stopping at the first failure. Ordinary tools are not exposed as outer tool calls.
No extra outer model request constructs a task description for an inner planner.

Known operations can share one plan; a read/search whose results determine an
edit needs another plan after those results return. A final reply is rendered as
text, not another executable tool. At most eight steps fit in one plan, and the
per-subtool argument budget is 2,048 tokens. Updated servers allow 17,408 total plan tokens; older servers retain a clearly reported 2,048-total compatibility mode. See [budget and rollout status](../../docs/PLAN_TOKEN_BUDGET.md). This does not promise one request
for a whole arbitrary task or an internal multi-decision engine state machine.

Successful complete plans admit their write content into a separate
`tool-plan-codebook.sqlite3`. The model can select immutable content and bind a
new destination, avoiding regeneration. Reads, shell commands and tests execute
again; their old outputs are never replayed. Stored evidence explicitly says
**execution succeeded; semantic correctness unverified**. Failed plans do not
admit their partial writes; those already executed file changes are not rolled
back. This content cache is separate from the trusted Python-module codebook.

Only the outer plan emits Pi tool-call events. Nested operations use native Pi
implementations, not separate outer events; compatibility with third-party
per-tool permission/audit extensions is not established. This mode is not an OS
sandbox. Image transport remains unsupported by the current text provider.

The old task-specific research mode remains available explicitly as
`--plan-only --verified-modules`, with `PIJIT_PLAN_VERIFY_ARGV` required. Its
fixed UTF-8 demonstration is not the default and must not be used as a validator
for arbitrary tasks.

Real end-to-end cases, failed pilots and limits: [generic plan](../../docs/GENERIC_PLAN.md).

Two opt-in research variants are **not production recommendations**:

- `PIJIT_COMPACT_CATALOG=1`: retrieve at most two entries and place the decision
  catalog after conversation history. The 21-task paired run passed both arms,
  but TAIR took 270.32 s versus native 213.85 s. Leave this off; see
  [the negative result](../../docs/COMPACT_CATALOG_EVALUATION.md).
- `PIJIT_REUSE_ROUTING=1`: classify at most two stored-content entries or general
  generation, then produce the complete plan without first-tool classification.
  All seven inner tools remain available. This changes model behavior and is
  not a semantics-preserving transport optimization; see
  [evaluation and limitations](../../docs/REUSE_ROUTING_EVALUATION.md).

Neither flag changes user defaults or proves that a retrieved entry satisfies
new constraints. Classification scores are not calibrated correctness scores.

For a matched **generic-plan ablation**, `PIJIT_PLAN_DISABLE_REUSE=1` suppresses
both content and template candidates while keeping successful-write admission
active. The launcher preserves this explicit setting; it no longer overwrites
it with `0` in plan-only mode. This does not clear any stored entries or disable
plan execution. The default remains reuse enabled.

`benchmark_expanded_reuse.py --ablation --empty-book` runs native multi-tool,
generic plan without reuse, and the same plan with reuse from separate empty
experimental states. It checks the effective setting in runtime traces and
waits for backend idleness after a timed-out task before starting the next arm.
See [the three-arm evaluation](../../docs/PLAN_REUSE_ABLATION.md).

### Experimental conditional final reply

`PIJIT_PLAN_SUCCESS_REPLY=1` lets the model append an `on_success_reply`
item to the generated plan. It is decoded into reply metadata, never executed as
an extra native tool. The original generation accounts for its tokens. After all
steps succeed, Pi may deliver that text without another inference request.

Delivery requires the exact originating conversation and tool call, the same
session, no cancellation, and no intervening user message. Read/search results
always return to the model. Bash output returns to the model unless it is empty
or exactly matches a predeclared receipt in `expected_outputs` (zero-based executed
step index and exact combined-output text, including newlines). Truncated output,
mismatched receipts, and invalid indices cannot bypass the model. Write/edit
receipts are allowed. A failure follows the
existing recovery loop. These checks do not prove task completeness or semantic
correctness, so this remains opt-in and requires independent task validation.
The conditional reply occupies one of the existing plan slots and does not
change the deployed server's argument envelope or per-step token budget.

`benchmark_expanded_reuse.py --success-reply-ablation --empty-book` compares
native tools, ordinary generic plan without reuse, and that same plan with the
conditional reply enabled. Both plan groups keep learning in separate test
books; user state is untouched. Execution logs record `planned_reply_offer`
and `planned_reply_delivered` separately from model calls.

The experimental prompt asks for an explicit completion decision on each plan: an
empty reply means continue, a nonempty reply requests conditional completion. If
the model omits this metadata, execution continues normally and the trace records
`missing_completion_decision`; omission never authorizes skipping another turn.
A strict-rejection experiment failed and is retained only in archived evidence.

`PIJIT_RECOVERY_LATEST=1` experimentally limits forced recovery classification to
an immediately preceding failed tool result. Successful subsequent operations
restore the full decision catalog; all earlier failure details remain in history,
and the continuation warns that a successful read does not resolve a failed check.
The benchmark's `--recovery-latest` applies this equally to its plan arms and
verifies the actual trace setting. Ordinary plan retains the previous routing.
When `PIJIT_PLAN_SUCCESS_REPLY=1` and no recovery override is set, latest-result
recovery is selected to avoid retaining forced recovery after successful repair.
Explicit `PIJIT_RECOVERY_LATEST=0` preserves whole-turn recovery for controlled
comparisons. Both experimental features remain disabled by default. This does
not establish general acceleration or guarantee completion; see the
[latest-result completion evaluation](../../docs/REPLY_LATEST_RECOVERY_EVALUATION.md).

A completion-only plan with a nonempty reply and no unbound output expectations
is normalized to a normal final reply. Empty continuations remain invalid.
Validation failures expose a compact message to Pi, while the failing instance,
path, and rule stay in local metrics; schema descriptions must not accidentally
trigger Pi's provider-error retry heuristic.
See [completion and recovery evaluation](../../docs/PLAN_COMPLETION_RECOVERY_EVALUATION.md).

`benchmark_expanded_reuse.py --recovery-ablation --empty-book` isolates recovery
routing with native, ordinary plan, and latest-result recovery plan arms. Reuse
and conditional replies are off in both plan arms. The 21-task comparison did
not establish an additional speed benefit from the new routing, so it remains
opt-in. See [the expanded evaluation](../../docs/RECOVERY_SCOPE_ABLATION.md).

Generic chat traces now separate `capability_negotiation` and `plan_decoding`.
`benchmarks/profile_plan_client.py` measures capability GETs and archived-plan
validation without inference or tool execution; these microbenchmarks do not
replace end-to-end measurements.

### Experimental capability negotiation cache

`PIJIT_CAPABILITIES_CACHE=1` reuses capability negotiation within a Pi session for
up to 30 seconds from the original lookup. Hits do not renew the TTL. The cache
is memory-only, scoped to endpoint/model/credentials/session, and cleared on a
new session or chat error. The bridge validates snapshot age and scope again.
It stores only server metadata; normal generation, tool execution and codebook
learning continue. A server change within the TTL can still produce an error,
which invalidates the cache; no automatic generation replay is added.

`--capabilities-ablation` compares native, ordinary plan and capability-cached
plan, with content reuse and conditional replies disabled. Real tests confirmed
nine avoided GETs in fifteen chats, but not a net task-time improvement in the
first six-task sample. The cache remains opt-in. See the
[capability cache evaluation](../../docs/CAPABILITIES_CACHE_EVALUATION.md).


### Experimental write content references

`PIJIT_WRITE_REFERENCES=1` permits ordinary write arguments to use
`content: {"stored": N}` in place of the full content string. N identifies a
non-template candidate in the current request catalog, not a persistent database
index. First actions, later actions, and general plans can all use references.
The bridge validates the wire schema, expands the selected bytes, then validates
the resulting ordinary Pi tool calls. Unknown indices and extra reference fields
are rejected. Full string generation remains available; default behavior is unchanged.

This closes a protocol restriction where selecting the native write branch made
reuse unavailable for that plan. It adds no model request and retains the existing
classification kernel, but the content reference itself is generated by the model,
not chosen by an additional classifier. Reference validity does not prove semantic
applicability. Current requirements and fresh checks remain necessary; templates
are excluded. Reuse accounting and final-content admission use the existing path.

`benchmark_expanded_reuse.py --write-references-ablation --empty-book` compares
native tools, ordinary plan with reuse, and plan with write references. Plan arms
learn independently from empty books; all other experimental switches are disabled.

See the [two-run evaluation](../../docs/WRITE_REFERENCES_EVALUATION.md) for actual
reference adoption, unchanged-query rejection, and the limits of timing attribution.

### Experimental recovery admission

`PIJIT_RECOVERY_ADMISSION=1` recovers successful write/edit steps from failed plans
when the current user task reaches a model-generated final reply after a successful
plan containing bash. It uses matching tool-call/result history and reads current
file contents, not stale generated arguments. New user tasks, unexecuted calls,
failed final results and read-only recovery do not authorize this path. Successful
mutation plans retain their normal admission. Recovered contents remain execution
observations, not semantically verified entries; no template or reuse credit is
created. The operation runs locally inside the existing bridge invocation and
adds no model request. It remains off by default. See the
[recovery admission replay](../../docs/RECOVERY_ADMISSION.md) for evidence and limits.

`benchmark_expanded_reuse.py --recovery-admission-ablation --empty-book` adds
controlled `recovery_jsonl_base`, `recovery_jsonl_repeat`, and
`recovery_jsonl_changed` tasks. The checker deliberately fails once, then verifies
the generated module; its contents and two attempts are independently checked.
Native tools are compared with two plan arms that both allow write references;
only `tair_recovered` enables recovered-content admission. These are targeted
recovery experiments, not representative general speed benchmarks. Complete-plan
reuse counters do not count a reused write followed by an intentionally failed
check; inspect step results separately before attributing reuse in this fixture.

`--warm-reuse-ablation --repeat-count N` compares native tools with two plan arms
that both enable write references and recovery admission. Only content reuse is
disabled in `tair_no_reuse`; it still learns. `repeat-count` duplicates selected
repeat-phase tasks with exactly the same prompt, initial files and oracle; only
the result-directory ID changes. Each task starts with reset workspace files,
while each arm retains its own codebook. This measures repeated-task behavior,
not reuse of existing output files or a shared cross-arm cache.

Content admission now records workspace-relative `observed_paths` alongside its
execution-only evidence, grouping paths when the same bytes were written to more
than one file in that admission. Existing SQLite columns and entry identities are
unchanged; old evidence strings remain readable with unknown paths. The catalog
labels `contract` as the historical whole user task, not a proven specification
for each saved file, and shows the observed paths as context. A helper or test
file is not automatically the requested implementation. Paths do not constrain
a new destination or certify semantic compatibility; the model still has to
inspect the actual content, exports and dependencies. No new inference call is
used to produce this metadata.


An extension of reuse review to ordinary write references was evaluated and
removed after contradictory reviews still authorized incorrect content. Existing
specialized reuse review remains unchanged; see the
[reference review evaluation](../../docs/REFERENCE_REVIEW_EVALUATION.md).

Candidate descriptions and selected-branch continuations now share the same
request-local candidate number and observed paths. Persistent hash IDs remain
internal; `reuse_write` still expands only the selected candidate. This improves
referencing, not semantic authorization. The
[candidate binding probe](../../docs/CANDIDATE_BINDING_EVALUATION.md) separates
forced selection, generation fallback, and full protocol compliance.

`PIJIT_BASH_ARGV=1` optionally allows `bash.command` to be an array of literal
argument strings inside a plan, for example `["node", "-e", "console.log('ok')"]`.
The bridge quotes each argument and passes an ordinary command string to Pi's
existing bash tool. Arrays do not expand variables, globs, pipes or redirections;
use the original string form for shell syntax. This option is off by default and
adds no model request. It prevents a layer of shell quoting mistakes, but cannot
validate the generated program or its tests. `--argv-ablation` compares native
Pi, ordinary plan, and this option with reuse disabled in both plan arms.

`PIJIT_PARALLEL_CAPABILITIES=1` overlaps fresh server capability negotiation with
input tokenization and label preparation. Inference waits for all three; a failed
capability query still prevents inference, and legacy budgets remain supported.
This is independent of capability caching and off by default. When enabled,
`generation_preparation` includes waiting for capability negotiation, so that
stage overlaps `capability_negotiation` and their durations must not be added.
`--parallel-capabilities-ablation` isolates scheduling with reuse disabled.

`PIJIT_REPLY_BRANCH=1` adds an internal reply-only classification branch before
existing general continuation. The public tool remains `plan`. Selecting reply
uses only the content schema instead of the full inner-tool schema. Native tool
and content candidate indices remain stable, and the general execution fallback
remains available. During recovery the existing general replanning branch is
used. This option is off by default: early completion mistakes and changed
classification behavior need broader evaluation. `--reply-branch-ablation`
isolates this choice with content reuse disabled in both plan arms. See the
[initial evaluation](../../docs/REPLY_BRANCH_EVALUATION.md).

`--combined-reuse-ablation` evaluates four arms: native Pi, ordinary plan without
reuse, combined plan without reuse, and the same combined plan with reuse.
Combined arms enable bash argv, the dedicated reply branch, write references,
and recovery admission; only their reuse switch differs. Learning stays enabled
in both. `--repeat-count` controls repeated fixtures while preserving each arm's
isolated book. The [combined evaluation](../../docs/COMBINED_REUSE_EVALUATION.md)
distinguishes correct initial content reuse, failed following checks, and final
artifact correctness. This harness option does not change production defaults.

`PIJIT_REPAIR_FEEDBACK=1` records task-specific negative feedback at final reply:
a stored byte sequence was written before a failed bash step, the same workspace
file was explicitly modified by a later successful plan, a final bash-containing
plan succeeded, and the observed final bytes differ. The old bytes are excluded
from future candidate lists for the exact same user request. Other requests can
still retrieve them. Duplicate entry IDs with the same source cannot bypass the
filter. Check-only repairs do not reject content. This reuses the existing SQLite
rejections table, with no migration or extra inference request. The option is off
by default; disabling it also disables its retrieval filter. This is observed
replacement feedback, not proof of semantic incompatibility or correctness.
See the [offline validation](../../docs/REPAIR_FEEDBACK.md).

`--repair-feedback-ablation` compares native Pi, the combined configuration with
reuse, and that same configuration plus repair feedback. It adds repeat fixtures
for the changed JSONL and JavaScript requests; their prompt, filename and oracle
remain identical to the first changed request. `--repeat-count` repeats those
fixtures while each arm retains its own book. The
[live evaluation](../../docs/REPAIR_FEEDBACK_EVALUATION.md) confirms persisted
feedback and candidate exclusion, but does not establish a net speed benefit.

`PIJIT_DEDUP_TOOL_DESCRIPTIONS=1` shortens native-action labels in the decision
catalog to the tool name and a reference to `INNER TOOLS`, where each complete
description remains. Candidate contents and descriptions, tool schemas, branch
indices and generation continuations are unchanged. Recovery and reuse-only
routing already lack native action labels and are unchanged. The option is off
by default. `--dedup-descriptions-ablation` isolates it with reuse disabled;
see the [token profile and live evaluation](../../docs/TOOL_DESCRIPTION_DEDUP_EVALUATION.md).

The [two-run replication](../../docs/TOOL_DESCRIPTION_DEDUP_REPLICATION.md)
found check-first workflow violations in both plan variants, despite correct
final artifacts. Dedup remains off. The expanded benchmark now checks explicit
fixture workflow metadata before reporting each result: `artifact_passed`
records output correctness, `workflow_validation` records declared workflow
checks, and `passed` requires both. Historical frozen results are unchanged;
their separate audits must be consulted when comparing quality and speed.

The classifier omits historical-code reuse instructions when no candidates
are offered (including disabled reuse). Warm-candidate and recovery prompts
are unchanged. The fixed-input profile saves 79 prefix tokens; the live smoke
run does not establish a latency benefit. See the
[empty-candidate prompt evaluation](../../docs/EMPTY_CANDIDATE_PROMPT.md).

`PIJIT_FIRST_TOOL_CLASSIFICATION=0` experimentally removes native first-action
choices while preserving codebook candidates, their limit and general plan
generation. Recovery is unchanged. Unlike `PIJIT_REUSE_ROUTING`, it does not
also repeat the current request or cap candidates at two. The default remains
enabled. `--first-tool-ablation` compares this change with reuse disabled;
[two-run results](../../docs/FIRST_TOOL_CLASSIFICATION_EVALUATION.md) show lower
observed time but a remaining explicit-order failure, so do not establish
native-equivalent reliability or general acceleration.

`--first-tool-reuse-ablation` compares native, ordinary plan with reuse,
general plan without reuse, and general plan with reuse using isolated books.
The [warm-book evaluation](../../docs/FIRST_TOOL_REUSE_EVALUATION.md) verifies
four correct repeated-content hits but also a wrong hit after a requirement
change. Engine HTTP errors now retain request ID, decision index and finish
reason for diagnosing long generations; incomplete usage remains marked as such.

A structured engine HTTP 500 that explicitly reports `finish_reason=length`
now becomes `GenerationLengthError`. Pi stops instead of blindly retrying the
unchanged request; ordinary transient HTTP failures keep their retry behavior.
Raw status and consumed-token accounting remain in metrics. This does not
repair the unfinished task or stop its first overlong generation earlier.
See [length-error retry handling](../../docs/GENERATION_LENGTH_RETRY.md).
