# TAIR architecture

The system separates decisions, free-form content, structure and execution.

## Ownership

| Component | Owns |
| --- | --- |
| Harness | Task/context assembly, permissions, execution and the agent loop |
| Candidate/schema builder | Runtime tool table, source targets, supported slots and value types |
| Inference engine | Candidate-logit selection, retained-KV continuation, constrained argument generation |
| Protocol runtime | Snapshot validation, parameter decoding, deterministic source transformation |
| Tool executor | Actual Pi tool invocation or isolated edit application |

The Pi candidate experiment contains `read`, `bash`, `edit`, `write`, `grep`,
`find`, `ls`, `powershell`, and an explicit `reply_user`. Returning a tool-call
object is not the same as implementing or authorizing those tools. The combined
structural experiment narrows the candidates to editing operations; it does not
move filesystem execution into the model server.

## Direct classification and generation

The request declares candidate token IDs, tools with parameter schemas, a
classification prompt and deterministic continuation tokens for each option.
`deploy/vllm_direct_tools.py` reads the candidate logits and takes argmax. The V2
hook excludes classification rows from ordinary sampling and preserves ordinary
rows in mixed batches. A control ID travels through vLLM's output transport; it
is counted separately from generated argument tokens.

The server selects the corresponding continuation and schema, and resumes the
same engine request. Scheduler KV blocks remain allocated. Worker-slot metadata
is retired at the pause boundary to avoid exhausting V2 worker slots. The resume
hook updates the output budget and structured-output state. Continuation tokens
are injected as known input and cost prefill computation; this is not a fused
single-kernel operation. XGrammar constrains generation, then JSON/schema
validation gates construction of the final call object. Incomplete output fails.

V1 compatibility code is included, but the live DeepSeek evidence is for V2.
The source patch targets an exact vLLM development version and is not an upstream
supported plugin interface. `benchmarks/verify_deepseek_direct_engine.py` and
`verify_direct_structural.py` inspect per-request worker events for the claimed
classification and cache path.

## Compact structural protocol

`compact_structural_protocol.py` derives named targets from source and narrows
candidate scope with lexical task retrieval. `direct_structural_protocol.py`
constructs source-bound schemas for `arg`, `kw`, `return_if`, `raise_if`, `catch`
and `mixed`. For a single operation, the model emits target/value tuples and the
runtime supplies the operation name. Mixed-operation arrays retain per-edit names.

Deterministic rewriting avoids regenerating existing source and handles formatting
for the supported constructs. Source hashes prevent applying stale edits. It
still parses generated expressions and cannot prove arbitrary generated code safe
or correct. Lexical scope narrowing can omit an intended target; schema validity
and behavior correctness are different checks.

## All-classification branch

The finite probe enumerates complete keyword edits from source-derived slots and
boolean/null/integer candidates, plus NONE. One logit selection indexes a tuple.
It needs no continuation, parameter decoding loop, or parameter text generation.
This is a bounded candidate table, not learned classification heads for arbitrary
AST construction. Candidate combinations can grow rapidly; serial field-by-field
classification may cost more model steps than a compact generative answer.

## What the architecture does not establish

- Schema constraints cannot guarantee the correct operation or value was selected.
- Less output does not automatically mean lower total tokens, latency or memory.
- Keeping KV through classification avoids a second full prefill; it does not
  establish lower peak KV usage than every baseline.
- Fixed-template expansion only replaces content the runtime can determine.
- Whole-agent reliability, arbitrary schemas, broad workloads and production load
  remain outside the current evidence.
