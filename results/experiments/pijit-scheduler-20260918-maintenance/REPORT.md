# Scheduler 4 → 8 maintenance test (2026-09-18)

The eight-sequence candidate improved this small fixed-tool burst benchmark but
regressed full Agent task latency. The original four-sequence container has been
restored, including its configuration, six patched source files, restart policy
and active watchdog. Native generation and retained-KV tool calling both passed
real post-rollback requests. See `restoration.json` and the restored smoke records.
The timing helper is retained in source and the stopped candidate, not active in
the restored service.

## Full Agent results

Each row contains six real Pi tasks (three repeats, integer-default values 6 and
8), with identical final AST/behavior checks. Validated wall time includes Pi
startup, all recovery attempts and final validation. Tool prompts/catalogs differ
between native and preset. Native means stock Pi tools on the same patched vLLM
standard API, not an unpatched vLLM deployment.

| Scheduler | Arm | Passed | Median seconds | Total seconds | Input tokens | Generated tokens | Classification controls | Inference calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 4 | native | 6/6 | 3.828 | 27.920 | 30952 | 1322 | 0 | 18 |
| 4 | preset | 6/6 | 4.131 | 55.929 | 43114 | 399 | 24 | 24 |
| 8 | native | 6/6 | 4.471 | 42.949 | 30982 | 1350 | 0 | 18 |
| 8 | preset | 6/6 | 5.943 | 73.139 | 40919 | 371 | 23 | 23 |

Preset median increased 43.9%; native median increased 16.8%. Preset generated
fewer tokens but used more input tokens and inference calls than native. Four
preset error records at capacity 4 and three at capacity 8 remain in the evidence;
all final tasks passed after any Agent recovery. No inference usage was unknown.
This is a small fixture on a shared backend, with sequential capacity phases and
post-restart warm-up differences. It does not isolate a causal scheduler effect.

## Fixed-tool bursts

Same serialized payload and exact `reply_user({"content":"DONE"})` oracle on both
capacities; one separately recorded warm-up and two eight-request batches per
client concurrency. Tokenization is outside client HTTP timing. No retries.
All 64 formal calls passed, each generating eight argument tokens and one
classification control record. These are not full Agent throughput measurements.

| Scheduler | Client concurrency | Correct | Sum batch seconds | Correct calls/second |
|---|---:|---:|---:|---:|
| 4 | 4 | 16/16 | 17.013 | 0.940 |
| 8 | 4 | 16/16 | 4.587 | 3.488 |
| 4 | 8 | 16/16 | 7.178 | 2.229 |
| 8 | 8 | 16/16 | 4.272 | 3.745 |

At client concurrency 8, observed throughput increased 68.0%. The slow 12.765 s
capacity-4/client-4 batch is preserved. Shared traffic and only two batches per
cell prevent a stable speedup claim. Payload hashes are in the burst manifests.

## Engine and timing evidence

The server uses six RTX 5090 GPUs, TP2 × PP3, priority scheduling, a 1024-token
batch budget and 272000-token context limit. Image:
`sha256:c0dec7f60c449fc4089134dcbc2b80462e9d39622fa33dba83dfb0b1d90987dc`.
vLLM: `0.28.1rc1.dev137+g5ab628dd1`; model revision:
`6821d6ad3681a4b137b066b76094fa82ebd0a380`.
The candidate changed max-num-seqs 4 to 8 and added classification timing
telemetry. Other configuration, image, model and mounts were preserved. Peak
observed running requests reached eight; no candidate OOM or automatic restart
was observed. Some GPUs had less than 1 GiB free. This is not a long-context
memory safety test. Engine audit checks verified classification bypass and
retained KV for 57 requests per phase, including warm-up/smoke requests.

One slow candidate request spent 6.877 s in the classification endpoint although
its initial queue interval was 0.000016 s and scheduled-to-first-output interval
was 0.366 s. Its continuation endpoint took 16.569 s; the audit pause-to-resume
interval was 16.324 s. These different boundaries do not identify pure GPU time,
grammar time or scheduler queue time. API/engine handoff and output delivery need
finer tracing before attributing the long tail. Autotuner fallback warnings also
occurred after restoring capacity 4, so they are not unique evidence against 8.

## Reproduction and preservation

See `seq4/manifest.json`, `seq8/manifest.json`, their rows and source snapshots,
`burst4/` and `burst8/`, engine events, load samples and smoke records. The benchmark
entry points are `benchmarks/compare_pijit_presets.py` and
`benchmarks/benchmark_pijit_scheduler.py`; use fresh output directories.
Private Docker inspection/configuration stays on the remote host under
`/opt/openjev-toolcall/maintenance/scheduler-20260918T033422Z/` and is not archived.
Disposable tokenizer caches are excluded; raw failed/slow experiment records
are preserved. The stopped eight-sequence candidate remains available for
inspection, with restart disabled. No model weights or external datasets were
copied. The original preflight archive remains unchanged.
