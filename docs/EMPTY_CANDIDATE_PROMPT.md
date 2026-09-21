# Empty-candidate classification prompt

2026-09-21. The generic plan classifier previously received guidance about comparing stored implementations, historical contracts and requirement changes even when its catalog contained no codebook candidates. The bridge now includes that paragraph only when candidates are available. This also covers explicitly disabled reuse and empty retrieval results. No additional flag, request, tool, schema or routing branch is introduced.

The fixed-input comparison uses the frozen bridge from `tool-description-dedup-20260921-b`, the real Pi 0.85.1 catalog and the pinned DeepSeek tokenizer. Empty and reuse-disabled contexts each drop from 1236 to 1157 prefix tokens (79 fewer). Warm-candidate and recovery requests remain identical, including their classification prompts. Tool schemas, preceding messages and generation continuations remain identical in all four contexts. The probe does not run inference or establish invariant model behavior.

Reproduce with:

```sh
python benchmarks/profile_empty_candidate_prompt.py /path/to/pinned-tokenizer docs/EMPTY_CANDIDATE_PROMPT_PROFILE.json
```

The live smoke experiment `empty-candidate-prompt-20260921-a` runs Python JSONL creation, JavaScript deduplication and failure-first repair against native Pi, plan with reuse disabled, and plan with reuse enabled starting from isolated empty books. It uses the existing Yuesheng six-RTX-5090 DeepSeek-V4-Flash-Vision-Exp service, TP2/PP3, Pi 0.85.1 and concurrency one. Runtime sources are frozen throughout. This is a current-path smoke comparison, not a paired old/new ablation; observed latency differences cannot be attributed to the 79-token change.

| Current-path smoke, three tasks | Native | Plan, reuse disabled | Plan, reuse enabled |
|---|---:|---:|---:|
| Artifact checks | 3/3 | 3/3 | 3/3 |
| Including explicit workflow checks | 3/3 | 2/3 | 3/3 |
| Wall seconds | 25.909 | 31.244 | 24.757 |
| Generated tokens | 2507 | 2298 | 1581 |
| Logical input tokens | 32936 | 33448 | 29382 |
| Inference requests | 12 | 9 | 8 |

No arm executed a content reuse. Enabled reuse accumulated candidates during the run, so its later prompts differ from the disabled arm; these are not identical repeated samples. The disabled arm incurred a shell quoting error, then an import-path error in its generated JSONL test script, and violated check-first order on repair. All arms have one expected initial repair-check failure. The new immediate validator correctly marks the workflow violation failed despite a correct final artifact. There were no timeouts or unfinished assistant turns.

The 79-token structural reduction is established; a net latency or reliability benefit from that change is not. Retain this minimal removal of inapplicable prompt text, but do not promote the larger description-dedup experiment or claim generic acceleration. Remaining work includes classifier order adherence and avoiding generated-command failures. Full validation: 588 tests passed; archive verification passed (2853 imported files, 68399 original checksum entries). See [measurement details](EMPTY_CANDIDATE_PROMPT_EVALUATION.json) and [fixed-input profile](EMPTY_CANDIDATE_PROMPT_PROFILE.json).
