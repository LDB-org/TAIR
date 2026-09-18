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

The engine must already support `/tokenize`, `/v1/openjev/toolcall`, and
`/v1/completions` with the repository's direct-classification patch. This is not
a drop-in client for arbitrary OpenAI-compatible servers. It supports at most
15 ordinary tools plus `reply_user`, text input, and up to 2,048 generated argument
tokens per call. Images fail explicitly. Compact source files are limited to
200 KB and must be inside the current project. Schema support remains subject
to the pinned vLLM/XGrammar implementation.

`metrics.jsonl` records completed calls and nested edit inference separately.
Outer-call and nested-call costs both matter. Error/aborted calls may consume
engine work without a final usage record; these logs are not billing-grade or
complete benchmark accounting. The adapter's preparation includes multiple
HTTP tokenizer requests, so reduced generation is not a latency guarantee.

## Installation elsewhere

Install Pi 0.85.1 and the repository environment (`pip install -e '.[test]'`).
Run `node /absolute/path/TAIR/integrations/pijit/launch.mjs`, or create
a `pijit` shell launcher for that command. The extension uses Pi's documented
[provider and tool extension interface](https://github.com/earendil-works/pi/tree/main/packages/coding-agent/docs),
without patching its core. Automatic extension discovery is disabled for this
profile; additional extensions can be loaded explicitly with `-e`.
