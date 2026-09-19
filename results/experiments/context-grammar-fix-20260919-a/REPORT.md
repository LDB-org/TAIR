# Context-plan grammar repair verification

The bridge no longer adds oldText.minLength to edit schemas. Observed paths and
nonempty edit lists remain constrained; the stock Pi executor rejects empty spans.

- Deployed host: rs-yuesheng-gpu-public; container: vllm-deepseek-v4-sm120-situ.
- Installed xgrammar 0.2.3: 18/18 complete-plan matcher expectations passed.
- Both stock array and legacy flat edit formats covered. Plain text, quotes,
  newline, backslash, tab, Unicode and empty strings accepted by decoder schema.
  Unobserved paths and empty plans rejected. Python jsonschema agrees on all 18.
- Stock Pi 0.85.1: six exact replacements passed; empty oldText rejected with file unchanged.
- Repository pytest: 292 passed in 1.84 seconds.

CPU grammar matching only on remote host; no inference requests, model loading,
service installation or restart. The Pi execution check used temporary local files.
No Agent speed or success-rate measurement was performed after this fix.

Reproduce the full-schema matcher check (exit 0 means all expectations match):

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes rs-yuesheng-gpu-public \
  'docker exec -i vllm-deepseek-v4-sm120-situ python3 -' \
  < results/experiments/context-grammar-fix-20260919-a/deployed-grammar-check.py
```

`cases.json` contains schemas built by the patched bridge from the installed Pi
edit schema and a legacy schema. `build-grammar-check.py` records their construction;
its absolute paths describe this verification environment. `edit-tool-check.mjs`
records the actual edit execution check; its package path is environment-specific.
`deployed-grammar-check.py` embeds the cases and requires only xgrammar.

The previous 120-attempt experiment is preserved unchanged. Retry-loop handling
and generated CSV semantics were not changed in this repair.
