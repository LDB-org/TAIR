# Reproduction

Run commands from the repository root. Use new output paths: benchmark outputs
are create-only, and failed runs must not be overwritten. No live server request,
model download, patch installation or restart is part of ordinary validation.

## Local verification

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
python benchmarks/verify_archive.py
python examples/compact_edit.py
```

`verify_archive.py` checks every imported experimental file against its migration
hash and every original SHA256SUMS manifest. Original manifests use both root- and
experiment-relative paths; the verifier resolves each convention explicitly.
`docs/MIGRATION_MANIFEST.json` also records original runner bytes. Maintained
runners have portability edits; snapshots inside experiments remain unchanged.

The example supplies a call directly to demonstrate deterministic rewriting. It
is not an inference benchmark. Tests exercise sampler hooks using CPU tensors and
stubs; passing them does not certify a running GPU deployment.

## Recompute an existing result

These checks are read-only:

```bash
python benchmarks/verify_direct_structural.py \
  results/experiments/pi-combined-structural-20260918-a \
  results/experiments/pi-combined-structural-20260918-a/engine-events.jsonl
python - <<'PY'
import importlib.util
import json
from pathlib import Path
spec = importlib.util.spec_from_file_location('summary', 'benchmarks/summarize_direct_structural.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(json.dumps(m.summarize(Path('results/experiments/pi-combined-structural-20260918-a')), indent=2))
PY
```

The summarizer CLI creates `summary.json` exclusively and will refuse to overwrite
an existing summary. Use its function as above to recompute archived results.

## Live editing benchmarks

Prerequisites: a reachable configured model endpoint; Linux with bubblewrap and
Python 3.12 for the original isolated behavior checks; Node.js; and separately
installed Pi 0.85.1. The recorded environment used Node 24.14.0 and
`@earendil-works/pi-coding-agent`. Configure the package path explicitly:

```bash
export TAIR_ENGINE_HOST=your-ssh-host
export PI_PACKAGE_ROOT="$(npm root -g)/@earendil-works/pi-coding-agent"
python benchmarks/evaluate_direct_structural.py \
  --host "$TAIR_ENGINE_HOST" \
  --out results/experiments/my-combined-run
python benchmarks/probe_all_classification.py \
  --out results/experiments/my-finite-classification-run
python benchmarks/probe_operation_prompt.py \
  --out results/experiments/my-prompt-ablation
```

SSH scripts use Python's standard library on the remote host to call
`http://127.0.0.1:8000`, with served model name `/model`. `TAIR_ENGINE_HOST`
defaults to `localhost`; that still means SSH, not a direct local HTTP connection.
Runners that expose `--url` instead of `--host` can address the server directly.
The two probe scripts inherit the host from the environment. Snapshot filenames
and fixed seeds intentionally retain the original experiment identity.

The edit benchmarks copy the archived pristine scanner into a new workspace.
They run task checks and 17 original regressions in a private network namespace;
scanner tests use loopback or mocked sockets. This does not authorize probing
external networks. The combined benchmark permits one native fallback; the finite
probe does not. Read each manifest before comparing totals.

Capture matching `/tmp/openjev-direct-events.jsonl` events from your own server
for engine-path verification. Frozen capture scripts document the original host
layout; they are provenance artifacts, not portable deployment commands.

## Pinned vLLM source patch

The tested backend is vLLM `0.28.1rc1.dev137+g5ab628dd1`, using the V2 model runner.
The original container image is recorded in experiment manifests. Identical
version strings alone do not guarantee identical source anchors. The installer
checks exact replacement anchors and saves original/patched hashes. Use an
isolated deployment of the matching source tree; first inspect the patch and
serving settings. The local test environment above is not a vLLM installation.

The original patch was applied in three stages, each with a fresh backup directory:

```bash
python deploy/install_vllm_direct_tools.py \
  --module deploy/vllm_direct_tools.py --backup /tmp/tair-base
python deploy/install_vllm_direct_tools.py \
  --module deploy/vllm_direct_tools.py --backup /tmp/tair-v2 --v2-only
python deploy/install_vllm_direct_tools.py \
  --module deploy/vllm_direct_tools.py --backup /tmp/tair-slots --streaming-slots-only
```

Run these only inside the intended vLLM environment. The first stage installs
routing and streaming state changes plus V1 compatibility; the second adds V2
classification; the third retires paused worker slots while retaining scheduler
KV. Server restart and serving/model setup are separate operator actions. The
repository does not restart a service automatically.

Rollback the same installation in reverse order with `--rollback --backup PATH`:
slots, V2, base. Hash checks refuse to overwrite subsequently changed patched
files. The helper module is copied by installation and remains after rollback;
restored upstream files no longer import it. Existing server processes require a
restart to load restored code. This is a research patch, not a general installer.

## Optional historical model experiments

Install `.[local-model]` for the pinned Transformers-based runners. The local
logit/grammar prototype additionally used `xgrammar==0.1.29`; protocol-training
experiments used `peft==0.18.0`. See the individual reports and training manifests
for exact models, revisions and dependencies. Do not silently use newer models
or report their results as a reproduction of the frozen run.

Model weights are not included. One CUDA GPU should be visible per independent
local scorer process. API-only benchmark clients allocate no CUDA model; the
recorded DeepSeek backend was an existing six-GPU TP2 x PP3 server, not a local
single-GPU scorer.

`TAIR_ENGINE_HOST` is the canonical SSH-host setting. `ENGINE_TOOLCALL_HOST`
is still accepted as a fallback for existing scripts.
