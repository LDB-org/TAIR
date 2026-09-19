# Expanded full-Agent comparison

Ten synthetic task families, two independent repeats, restored cold/warm pairs, three interleaved arms: 120 attempts. The seven added workloads cover new modules/CLI documentation, nested packages, quoted CSV, JSON configuration, exception boundaries, cross-file behavior, and an 84-file project with 80 unrelated modules. This is broader controlled coverage, not a real-repository or public coding benchmark.

## All attempts (failures retained)

| Arm | Basic checks passed | After test-quality audit | Total seconds | p50 seconds | p95 seconds | Max seconds | Recorded inference requests | Complete usage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 40/40 | 40/40 | 555.69 | 13.21 | 20.51 | 32.13 | 334 | 40/40 |
| batched | 38/40 | 36/40 | 402.96 | 9.69 | 13.46 | 20.20 | 148 | 40/40 |
| contextual | 24/40 | 23/40 | 2229.15 | 9.93 | 180.17 | 180.20 | 1004 | 32/40 |

Basic checks preserve the original run criteria. Requested-test quality is an additional stricter post-run review, reported separately; the per-family and common-success tables use this audited criterion. A missing required CLI test can therefore make an originally passing basic-oracle row fail this complete-task review; A null requested-test audit means no additional test-quality review was applicable or performed for that row. Raw rows.jsonl is preserved and base_passed is retained in expanded-analysis.json. Latency covers startup, model/tool calls, tests, recovery, final reply and an independent oracle including a unittest rerun. Fixture reset and post-run audits are excluded. A fast failed task is not an equivalent completed task. p95 uses linear interpolation over all attempts (40 per arm), not a production-tail estimate.

## Token and codebook accounting

| Arm | Generated tokens (known) | Control records (known) | Input tokens (known) | Inner edits | Edit hits | Tokenizer HTTP requests |
|---|---:|---:|---:|---:|---:|---:|
| native | 48009 | 0 | 820405 | 0 | 0 | 0 |
| batched | 24958 | 148 | 464524 | 3 | 0 | 326 |
| contextual | 78889 | 998 | 9693951 | 5 | 2 | 1342 |

Incomplete usage, if present, is explicitly recorded in expanded-analysis.json and cannot be treated as a zero-cost request. Recorded inference/token counts are lower bounds for arms containing incomplete tasks: a killed in-flight request may not have emitted a final trace record. Plans are generated; only inner supported edits use the existing learned codebook.

## Per family (passed / attempts; total seconds)

| Family | Native | Prior batched | Contextual |
|---|---:|---:|---:|
| properties | 4/4; 35.22s | 4/4; 33.29s | 4/4; 31.83s |
| alias | 4/4; 28.12s | 4/4; 29.93s | 4/4; 26.96s |
| summary_bug | 4/4; 63.20s | 4/4; 50.50s | 4/4; 38.48s |
| multifile_feature | 4/4; 69.94s | 2/4; 54.98s | 0/4; 588.51s |
| nested_package | 4/4; 43.52s | 4/4; 41.00s | 3/4; 379.73s |
| quoted_csv | 4/4; 59.50s | 2/4; 39.13s | 0/4; 31.78s |
| json_config | 4/4; 81.89s | 4/4; 28.61s | 0/4; 720.57s |
| exception_boundary | 4/4; 36.90s | 4/4; 38.03s | 4/4; 29.45s |
| cross_file_behavior | 4/4; 50.32s | 4/4; 49.57s | 0/4; 341.96s |
| wide_project | 4/4; 87.09s | 4/4; 37.93s | 4/4; 39.88s |

## Same completed tasks only

All three arms passed 23 matching (repeat, family, cold/warm) tuples. This subset omits harder failures and is descriptive, not a replacement for the all-attempt success rates.

| Arm | Matched tasks | Total seconds | p50 | p95 |
|---|---:|---:|---:|---:|
| native | 23 | 283.23 | 9.99 | 19.35 |
| batched | 23 | 218.07 | 9.17 | 12.98 |
| contextual | 23 | 366.23 | 8.76 | 71.77 |

## Failed attempts

- 0-multifile_feature-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 0-multifile_feature-batched-1: oracle=True, test integrity=True, requested-test audit=False, timeout=False, complete usage=True.
- 0-multifile_feature-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 0-quoted_csv-batched-1: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 0-quoted_csv-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 0-quoted_csv-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 0-json_config-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 0-json_config-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 0-cross_file_behavior-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 0-cross_file_behavior-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 1-multifile_feature-contextual-1: oracle=True, test integrity=True, requested-test audit=False, timeout=False, complete usage=True.
- 1-multifile_feature-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 1-multifile_feature-batched-2: oracle=True, test integrity=True, requested-test audit=False, timeout=False, complete usage=True.
- 1-nested_package-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 1-quoted_csv-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 1-quoted_csv-batched-1: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 1-quoted_csv-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.
- 1-json_config-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 1-json_config-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 1-cross_file_behavior-contextual-1: oracle=False, test integrity=True, requested-test audit=None, timeout=True, complete usage=False.
- 1-cross_file_behavior-contextual-2: oracle=False, test integrity=True, requested-test audit=None, timeout=False, complete usage=True.

## Controls and limitations

Same running 6 x RTX 5090 backend and Pi 0.85.1; no service restart or patch deployment. Native uses the ordinary tools API on the patched service and retains parallel_tool_calls=false. No comparison with a separate unpatched engine or enabled native parallel tools is implied. Tool catalogs, prompts, grammar and control granularity differ.

Code/runtime state is separate by arm and repeat. Warm pairs restore the original project while retaining only that arm runtime state; every Agent session is new. Execution is sequential across tasks with seeded interleaving, no replacement of failed attempts, and a 180-second per-Agent limit. Oracles are outside the Agent workspace. The seven new oracles reject the initial buggy projects and accept offline reference implementations before GPU execution. Original tests and designated unrelated files are protected by separate checks.

This suite deliberately includes supported and unsupported edits, generated new files, nested paths and discovery beyond a 64-entry root inventory. It does not establish generalization to arbitrary repositories, multi-user throughput, long-context limits, long-term codebook growth or correctness of admission. Same-task warm pairs do not establish transfer to unseen edits.

Source snapshots, raw events, final projects, independent oracle results, traces, per-repeat/cold-warm breakdowns and checksums accompany this report. Runtime was held fixed for the entire suite.

## Deployed grammar incompatibility

A CPU-only matcher probe of installed xgrammar 0.2.3 found 3 mismatches across ten checks. Legal nonempty strings containing a double quote, newline or backslash are accepted without minLength and rejected with minLength=1. Python jsonschema independently accepts these strings.

The added oldText.minLength=1 constraint therefore removes valid exact-match spans from the generated language on this deployment. This is a concrete contributor to quote-free/truncated edits and repeated failures; other tools or simpler spans can sometimes recover. CSV semantic errors remain a separate finding. See grammar-compatibility.json, grammar-jsonschema-validation.json, and sources/probe_json_string_grammar.py. No service update or runtime fix was applied during the suite, and this probe issued no model requests.
