# Exact request equality would discard the observed warm reuse benefit

An offline audit of `first-tool-reuse-ablation-20260921-a` correlates admission records with their parent chat's `plan_task`, then checks the five actual first-content reuse events independently validated in `FIRST_TOOL_REUSE_CONTENT_AUDIT.json`. Merely selecting a candidate without reusing its bytes does not count.

Requiring the entire current task string to equal the admission contract would reject all five: four correct repeated-task reuses and one incorrect changed-requirement reuse. The four correct cases change only the destination file in this benchmark. Even the second repeat uses the original base-task entry: `complete_tool_plan` excludes observed reused sources from fresh admission and updates their reuse counters instead of registering an additional contract.

Replacing the known old/new primary-file names with a shared placeholder makes the four correct contracts equal; the changed case remains different. This uses benchmark metadata and is diagnostic only. It must not be installed as a general natural-language rule, path extractor, or semantic proof. Filesystem destinations may also appear as behaviorally relevant strings, and successful execution is not independent task validation.

No runtime equality gate or contract alias learning was added. Either would need an explicit treatment of destination binding versus behavior changes and reliable validation before being advertised as a fix. The current result rejects the simple proposal rather than claiming a safer cache or speedup. Model replanning and its latency under the hypothetical gate were not measured.

Reproduce with `benchmarks/audit_exact_contract_reuse.py`; `EXACT_CONTRACT_REUSE_AUDIT.json` includes identities, contract hashes, decisions and input hashes. User codebooks and frozen experiment files are unchanged.
