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
labels are fetched on every call. Prompt/continuation tokenization is not cached.
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

The persistent table currently admits **single keyword edits only**. Entries are
bound to the project, file, exact source hash and normalized task wording. One
unambiguous integer can vary. Successful edits register both the original and
resulting snapshots, enabling a subsequent value change on the resulting file.
Paraphrased tasks or unrelated source changes miss the table and generate again.
A candidate must also pass direct classification with NONE, conditional score
>= 0.95 and logprob margin >= 3. These thresholds are heuristic, not calibrated
correctness probabilities. Only this nested edit inference can avoid argument
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
