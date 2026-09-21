# Historical first-tool classification audit

2026-09-21. `benchmarks/audit_first_action_classification.py` scans frozen full-Agent reports for the exact current `repair_failure` prompt and initial files. This is a retrospective census across different configurations and dates, not independent identically distributed trials or a general model accuracy estimate. Native Pi rows are excluded because they do not use this classifier.

47 plan trials have generic-plan decision evidence; 41 select a native first-tool branch. Of those 41, 10 select a tool other than the explicitly required `bash`. The remaining six select another branch and are not classified as native-selection errors by this audit. Tool choice alone does not prove the generated command is correct. Each row retains actual first-step arguments and source hashes.

40 native-selection trials have multi-option classification scores. A hypothetical rule routing low-margin decisions elsewhere yields:

| Winner-minus-runner-up logprob threshold | Decisions routed | Wrong native selections routed | Correct native selections routed | Wrong native selections left |
|---|---:|---:|---:|---:|
| < 0.25 | 7 | 5 | 2 | 5 |
| < 0.5 | 13 | 7 | 6 | 3 |
| < 1 | 22 | 9 | 13 | 1 |
| < 2 | 31 | 10 | 21 | 0 |
| < 4 | 40 | 10 | 30 | 0 |

These are routing counts, not corrections: no replacement plan was generated in this audit. A threshold that catches every observed native-selection error also routes most correct choices. Scores are not calibrated confidence probabilities; fitting a threshold on this one repeated fixture would not establish general safety or speed.

This supports testing whether the first-tool decision is needed at all, while retaining classification among codebook candidates and general generation. It does not support removing codebook classification, replacing semantic selection with keywords, or deploying a threshold. See [machine-readable evidence](FIRST_ACTION_CLASSIFICATION_AUDIT.json).
