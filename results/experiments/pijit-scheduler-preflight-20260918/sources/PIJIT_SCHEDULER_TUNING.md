# pijit scheduler tuning: prepared, not deployed

Live preflight on 2026-09-18 confirmed the shared six-GPU engine uses TP2 x PP3,
`--max-num-seqs 4`, `--max-num-batched-tokens 1024`, priority scheduling, and a
272000-token maximum context. The per-request-metrics flag is present.

All 20 one-second load snapshots had four running sequences and waiting requests.
KV pool usage ranged from 7.75% to 25.18%. This supports investigating sequence
capacity; it does not establish that eight sequences fit activation memory or
improve end-to-end performance. Raw snapshots are in
`results/experiments/pijit-scheduler-preflight-20260918/`.

## Prepared change

- Candidate changes the sequence limit from 4 to 8. Token scheduling budget,
  priority policy, model, parallel layout, ports and existing mounts stay fixed.
- `deploy/vllm_direct_tools.py` snapshots queued, scheduled and first-output
  engine timestamps at classification. Streaming continuation mutates the same
  stats object, so reading it only at completion would mix timing boundaries.
- `integrations/pijit/bridge.py` retains this timing separately from HTTP time,
  server endpoint time and classification control counts. Missing or reordered
  timestamps remain unknown rather than becoming zero.
- This local code is tested but is not active on the shared server.

The original container inspection/configuration and six patched source files are
backed up on the remote host under:
`/opt/openjev-toolcall/maintenance/scheduler-20260918T033422Z/`.
The directory is private; original inspect/configuration may contain credentials
and is not copied into this repository. `proposed-command.json` changes exactly
one sequence-limit argument; `proposed-helper.py` contains the timing addition.
The sanitized proposal records source hashes and confirms `applied: false`.

## Maintenance and acceptance

Applying the candidate requires restarting the shared model service. It has active
traffic, so a maintenance-window confirmation is pending. No service was stopped,
no live helper was overwritten, and no scheduling limit was changed by preflight.

After confirmation:

1. Retain the current four-sequence baseline evidence and record current load.
   Check the backed-up container/config/source hashes still match before changes.
2. Coordinate the existing watchdog and preserve the original container as a
   rollback target. Reproduce its configuration and patched sources; do not start
   from an unpatched image alone. Apply the candidate limit and timing helper.
3. Validate native inference and retained-KV tool calling, then rerun the same
   seeded native/preset task comparison with unchanged client controls and oracle.
   Preserve startup/warm-up records separately from formal samples, as well as
   every failed or slow formal request.
4. Compare full task time, classification queue and post-scheduling intervals,
   correct-task throughput, errors, generated tokens, input tokens, and memory.
   Client preparation remains the already-tested optimized implementation.
5. Roll back for OOM, engine errors, correctness loss, or performance regression;
   restore the watchdog and verify native and tool-call service behavior again.

Changing scheduling capacity affects batching and activation memory. A busy
shared-server A/B is not an isolated load experiment; adding telemetry and
reloading the engine also need to be disclosed. No speedup is claimed before
these checks have actually completed.
