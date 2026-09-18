# DeepSeek long-output experiment

The same patched DeepSeek deployment was tested with longer argument values.
This is a controlled long-output reproduction test, not a long-running autonomous
Pi agent task. No server restart or engine change was made for this experiment.

Evidence: `results/experiments/pi-deepseek-long-20260918-a/`.

## Workload and result

Three predefined tasks, two repetitions per method, randomized interleaving
(seed 20260921), temperature zero, 2048 output-token limit for both methods:

- Write a complete standard-library Python CSV reporting program.
- Replace a 16-service Python configuration block with another multiline block.
- Reply with a fixed 36-line report, preserving all content and the final newline.

The payloads were fixed before inference. The exact-match check includes the tool,
path, content, indentation, and final newlines. Neither method's output was repaired.

| Metric | Whole tool-call JSON | Direct classification + arguments |
| --- | ---: | ---: |
| Completed, correct-tool calls | 6/6 | 6/6 |
| Exact tool and arguments | 4/6 | 2/6 |
| Generated tokens, including termination | 5463 | 5406 |
| Internal classification control records | 0 | 6 |
| Sum of client latencies | 94.323 s | 110.310 s |
| Median client latency | 15.899 s | 14.365 s |

Generated tokens decreased **1.04%**, or **0.93%** if the six internal control IDs
are also counted. The sum of latencies increased **16.95%**, while the median
decreased **9.65%**. This inconsistency, shared-server queueing, unequal content
accuracy, and the small sample prevent a stable speed claim in either direction.

| Task | Whole tokens, two calls | Direct tokens, two calls | Whole total time | Direct total time |
| --- | ---: | ---: | ---: | ---: |
| Python write | 1305 | 1284 | 20.564 s | 28.730 s |
| Multiline edit | 1892 | 1870 | 31.798 s | 25.830 s |
| Long reply | 2266 | 2252 | 41.962 s | 55.750 s |

Only one paired repetition had both outputs exactly correct: Python write,
repeat 0. It saved 10 generated tokens but took 0.624 seconds longer with the
direct method. This is a post-hoc subset, not an independent speed benchmark.

## Content failures and execution checks

These diagnostics supplement, and do not replace, the predefined exact score:

- **Python write:** both direct outputs exactly matched the source, compiled,
  and passed JSON and Markdown execution checks using a three-row CSV fixture.
  One whole-JSON output also passed. The other inserted `1` before an indented
  statement and failed Python compilation.
- **Edit:** both direct outputs and one whole-JSON output omitted the final
  newline in `oldText` and `newText`, failing exact argument matching. All four
  edits nevertheless applied uniquely to the fixture and produced the exact
  expected final file, which compiled. This was a literal fixture application,
  not an invocation of Pi's tool executor.
- **Reply:** both direct outputs incorrectly included the closing `END_REPORT`
  marker as an additional line. Both whole-JSON replies were exact. The marker
  was not stripped for scoring.

Only generated Python whose AST matches the known, trusted fixture is executed;
all other outputs receive syntax inspection without arbitrary execution. The
diagnostic script retains errors and records every row's outcome.

Valid JSON and the right tool category did not prevent invalid code or unwanted
text inside string values. This is a content-correctness limitation, not evidence
of a tool-call JSON parsing failure.

## Why token savings shrink

Independent tokenization of identical expected values, using the deployed
tokenizer and a fixed JSON serialization, gives these counts without EOS:

| Task | Whole JSON | Arguments only | Wrapper saved |
| --- | ---: | ---: | ---: |
| Python write | 651 | 641 | 10 (1.54%) |
| Multiline edit | 947 | 938 | 9 (0.95%) |
| Long reply | 1132 | 1121 | 11 (0.97%) |

The current engine integration removes the tool name and outer wrapper from
generated text. Argument keys, string escaping, indentation, and all content
remain generated. The saved wrapper is approximately constant in size, so its
fraction falls as the payload grows. Classification alone does not compress
the long values.

## Engine verification and scope

All six direct requests passed the independent engine-event verifier, including
mixed batches. Classification rows bypassed normal sampling. The same scheduler
request retained its KV blocks across worker-slot retirement and continuation.
Preserved prefixes were 1031, 1370, and 1600 tokens, respectively, thus exercising
chunked prefill beyond the configured 1024-token batch budget. The continuation
retained the selected schema and updated the output limit to 2048.

The model, vLLM version, image, patch hash, and topology are the same as in
`DEEPSEEK_DIRECT_ENGINE_EXPERIMENT.md`; live identity is recorded in this run's
`live-manifest.json`. The generator, benchmark, verifier, diagnostic script, and
engine helper are snapshotted alongside rows and checksums. Published headline
results remain unchanged.

The experiment establishes that the retained-KV classification path works on
these longer inputs. It does **not** establish significant long-output compression,
stable acceleration, general code-generation accuracy, or production readiness.
