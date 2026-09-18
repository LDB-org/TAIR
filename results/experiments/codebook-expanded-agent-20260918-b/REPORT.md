# Full Agent validation after compact-routing clarification

This run uses real Pi 0.85.1, three small coding tasks, cold/warm rounds, and three
arms: stock native provider/tools, TAIR with its codebook disabled (`generation`),
and TAIR with its default expanded codebook (`c4`). Every arm starts a fresh Agent
session for each task. Warm rounds restore original files at the same project path
while retaining only runtime codebook state. Schema actions, exact replay, preset
tools, local deterministic routing, directory guard and tokenizer caches are off.

The prior Agent diagnostic showed ordinary edit/write was selected exclusively.
The revised provider instructions explicitly identify compact-supported edits and
allow up to eight related changes in one compact call. Tool description and `/jit`
status text now match the expanded codebook. Ordinary edits remain available for
unsupported changes, tests and new files. This change does not force every task
through a compact operation or remove the normal tool path.

## Results

| Metric | Native | TAIR generation | TAIR learned codebook |
|---|---:|---:|---:|
| Fully completed tasks | 6/6 | 6/6 | 6/6 |
| Total validated task wall time | 69.552 s | 72.569 s | 73.453 s |
| Outer inference calls | 38 | 38 | 36 |
| Nested edit inference calls | 0 | 2 | 2 |
| Accepted codebook reuse | 0 | 0 | 1 |
| Generated tokens | 6,129 | 2,521 | 2,633 |
| Classification controls | 0 | 40 | 38 |
| Input tokens | 84,781 | 109,880 | 103,882 |

All 18 implementation behavior checks and task-integrity checks passed; usage is
complete. The learned-codebook arm was 5.6% slower than native in total task wall
time, despite fewer generated tokens. This experiment does **not** demonstrate
whole-Agent acceleration. Lower generated output is not lower total computation.

The five-property configuration task used one compact edit and its warm repeat
reused the learned multi-edit array. That task's learned-codebook wall time was
14.203 s cold and 12.621 s warm; native was 8.936 s and 8.987 s. The alias task still
chose normal edit, and the summary repair appropriately needed ordinary source and
test edits. Thus only two nested compact calls occurred in the six learned-codebook
tasks; the local edit-path gains affect a small portion of the full loop.

Inspection also observed attempts to read a directory followed by recovery through
listing commands, plus repeated outer context preparation. These are concrete next
optimization targets. This run deliberately leaves optional directory/local-route
shortcuts off to measure the default classification-driven path. Shared backend,
different tool catalogs, one cold/warm pair per scenario: timings are exploratory,
not stable throughput or tail-latency estimates.

## Correctness and preserved evidence

Tasks cover five CLI property changes, adding an alias while preserving defaults,
and repairing duplicate counts/empty input/negative and floating values while
adding tests. The first two tasks forbid test edits. The last explicitly requests
new tests; the corrected harness checks existing test-method ASTs remain intact
and additional tests exist, alongside the independent behavioral oracle. It does
not equate adding tests with changing the original assertions. The earlier
diagnostic's raw rows and separate adjudication are retained in its own directory.

Task wall time includes Pi startup, planning, tools, model work, agent recovery,
in-loop tests, final reply, and independent final oracle. Fixture reset and SSH
tunnel setup are excluded. Codebook admission within this Agent run is compile-only
because the original scenario harness validates complete tasks externally; the
final passing result must not be treated as proof that every entry was independently
behavior-validated when admitted.

`rows.jsonl`, `summary.json`, per-task event logs, native request traces, source
snapshots and final projects preserve the observations. Source snapshots match the
current implementation. Pi was installed under `/tmp/tair-pi-0.85.1` without changing
the user's global installation or profile. The temporary loopback SSH tunnel was
closed when the run finished; no model service was restarted or patched.

```sh
PIJIT_PYTHON=/path/to/test-venv/bin/python \
python benchmarks/benchmark_codebook_agent.py \
  --url http://127.0.0.1:FORWARDED_PORT \
  --out results/experiments/NEW_AGENT_RUN --repeats 1 --timeout 120
```

Use Pi 0.85.1 on PATH. Run against the existing compatible engine; all runtime
optimization flags listed above are cleared by this benchmark.
