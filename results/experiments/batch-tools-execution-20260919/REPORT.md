# Batch execution probes

Real Pi 0.85.1, mocked provider (no GPU and no speed claim).

- Failure: missing-file read fails; following write and bash steps are blocked. Neither sentinel is created.
- Sequence: write, read, then bash assertion complete successfully in order.
- Both batches use the normal Pi tool hooks and the batch-mode sequential built-in wrappers.

Raw tool results and probe assertions are preserved.
