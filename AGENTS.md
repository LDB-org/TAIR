# Repository instructions

- Work from the repository root in an isolated environment installed with `pip install -e '.[test]'`.
- Run `pytest -q` and `python benchmarks/verify_archive.py` after changes.
- Preserve frozen files in `results/experiments/` byte for byte, including failed runs. Use new output directories for experiments; never overwrite old evidence.
- Keep generated-token counts, classification control records, input tokens, behavior correctness, fallback costs, and timing boundaries separate.
- Do not turn token reductions into unsupported speed claims or schema validity into semantic correctness claims.
- The vLLM patch is experimental and version-specific. Do not install it or restart a service during ordinary repository validation.
- Do not commit model weights, caches, credentials, or external evaluation datasets. API clients do not load a GPU model; expose exactly one CUDA GPU per independent local scorer process.
- Preserve upstream license notices and exact model/engine revisions. The `openjev_phase1` module name is retained for compatibility with historical experiments.
