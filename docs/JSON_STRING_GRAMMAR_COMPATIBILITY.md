# Nonempty edit spans and deployed grammar compatibility

The expanded Agent suite exposed a concrete incompatibility between the added
`oldText.minLength = 1` constraint and the installed xgrammar 0.2.3 compiler.
A CPU-only matcher probe in the existing serving container reproduced it without
loading a model, issuing inference requests, or changing the service.

| String value | JSON Schema with minLength=1 | Unconstrained string grammar | minLength=1 grammar |
|---|---|---|---|
| Plain text | valid | accepts | accepts |
| `"port": 8080` | valid | accepts | **rejects** |
| Two lines separated by a newline | valid | accepts | **rejects** |
| A path containing a backslash | valid | accepts | **rejects** |
| Empty string | invalid | accepts | rejects |

The unconstrained grammar includes the normal JSON escape production. The
length-constrained grammar instead uses a repetition of a character class that
excludes quotes, backslashes, CR and LF, without an escape alternative. A quoted
or multiline `oldText` therefore cannot be emitted verbatim through that grammar.
Python jsonschema independently accepts all three rejected nonempty values.

This explains why a decoder can keep proposing quote-free or truncated spans,
and why repeated attempts cannot produce the required exact span while that
constraint remains active. Choosing another tool or a different single-line span
can sometimes recover, so not every such task must time out. CSV newline loss
from `text.splitlines()` is an additional semantic defect and is not established
to have the same cause.

The ordinary schema unit tests did not exercise the deployed grammar compiler;
passing those tests did not establish that the decoder accepts the same language.
The experimental context flag remains off by default. The 120-attempt suite keeps
its runtime unchanged, so its negative results are attributable to the tested
revision rather than a mid-run fix.

Reproduce on the current serving container:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes rs-yuesheng-gpu-public \
  'docker exec -i vllm-deepseek-v4-sm120-situ python3 -' \
  < benchmarks/probe_json_string_grammar.py
```

The probe exits nonzero when the matcher disagrees with the expected schema
language. It checks complete accepted strings, not token counts or generated
quality. The deployed 0.2.3 run has three mismatches across ten checks.

Evidence: [compiled grammars and matcher results](../results/experiments/expanded-context-agent-20260919-a/grammar-compatibility.json),
[independent jsonschema check](../results/experiments/expanded-context-agent-20260919-a/grammar-jsonschema-validation.json),
and [reproducer](../benchmarks/probe_json_string_grammar.py).

The bridge now no longer adds `oldText.minLength` for either array or legacy flat
edit arguments. It retains observed-path restrictions and nonempty edit-list
validation, and asks for nonempty exact spans in the planning instruction.
Pi's edit executor still rejects empty spans before writing the file. Supplied
tool schemas are otherwise preserved; this fix does not strip constraints from
arbitrary third-party schemas.

The patched full `execute_plan` schemas were checked on the deployed xgrammar
0.2.3: all 18 matcher expectations passed, including escaped strings in both edit
formats and rejection of unobserved paths and empty plans. A separate stock Pi
0.85.1 execution check verified six exact replacements and empty-span rejection
without changing the file. See [repair verification](../results/experiments/context-grammar-fix-20260919-a/REPORT.md).

These checks establish grammar compatibility and edit execution, not model task
quality. The later [single-factor ablation](MECHANISM_ABLATION.md) ran 120 Agent
attempts across six families and ten configurations. The repaired context arm
passed 10/12 with no timeouts, including both JSON configuration attempts. Both
CSV attempts still failed, as did all other TAIR configurations on that family.
This is a different matrix from the original ten-family comparison, not its
replacement rerun. Repeated-failure recovery and generated CSV semantics were
not changed in the repair.
