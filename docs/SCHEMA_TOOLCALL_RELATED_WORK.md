# Schema-directed classification and generation: prior-art check

Checked 2026-09-18 against primary repositories, documentation, and papers.
This is a targeted literature search, not an exhaustive novelty determination.

## Finding

The broad combination already has explicit precedents: finite-choice selection,
free-text generation, host-controlled structure, and interleaved execution.
It should not be described as a new invention on the strength of that
combination alone. The expanded search below found Thimble as an especially close specialized
tool-runtime implementation; Jsonformer remains a direct field-generation precedent.

## Closest code

### Jsonformer

- Repository: https://github.com/1rgs/jsonformer
- Inspected implementation: https://github.com/1rgs/jsonformer/blob/main/jsonformer/main.py

`generate_boolean` runs a forward pass and compares the final-position logits
for `true` and `false`. `generate_string` calls autoregressive generation.
`generate_value` dispatches by schema type, and `generate_object` populates a
Python dictionary. Thus direct categorical readout plus generated values plus
program-owned object construction already exists here.

Scope matters: the implementation supports a JSON Schema subset, assumes
single-token boolean representations, and uses a simple quote-based string
termination/extraction method. Its existence does not establish correctness
for arbitrary escaped strings, schemas, tool execution, or agent workflows.

### Guidance

- Repository and examples: https://github.com/guidance-ai/guidance
- Selection API: https://guidance.readthedocs.io/en/latest/generated/guidance.select.html
- Grammar backend: https://github.com/guidance-ai/llguidance

Provides `select` and `gen`, composition with Python control flow, named
captures, and fast-forwarding of deterministic grammar text. Selecting finite
values, generating variable content, and avoiding model generation of fixed
structure are therefore existing capabilities. A general `select` over strings
is not necessarily the same computation as one forward pass over single-token
labels; tokenization and the selection procedure matter.

## Relevant papers

### LMQL — Prompting Is Programming: A Query Language for Large Language Models

- PLDI 2023; preprint first submitted 2022-12-12.
- Paper: https://arxiv.org/abs/2212.06094
- Author publication page: https://www.sri.inf.ethz.ch/publications/beurerkellner2023prompting
- Project: https://lmql.ai/
- Evaluation artifacts: https://github.com/lmql-lang/lmql

Combines programming/control flow, constrained output variables, and an
optimizing runtime. Relevant to the proposed schema-to-execution layer.

### SGLang — Efficient Execution of Structured Language Model Programs

- Preprint 2023; inspected 2024 revision.
- Paper: https://arxiv.org/html/2312.07104v2
- Repository: https://github.com/sgl-project/sglang

Explicitly combines `select`, `gen`, state manipulation, and parallel branches.
Its runtime uses RadixAttention for prefix reuse; its compressed-FSM method
skips deterministic decoding segments via jump-forward decoding. The paper also
discusses tokenization boundaries and distorted choice probabilities. This is
prior work on the method; it is not a claim that every current SGLang backend
still enables the historical jump-forward implementation.

### XGrammar and XGrammar-2

- XGrammar, 2024: https://arxiv.org/abs/2411.15100
- XGrammar-2, 2026: https://arxiv.org/abs/2601.04426
- Repository: https://github.com/mlc-ai/xgrammar

Efficient grammar-constrained generation; XGrammar-2 adds dynamic structural
dispatch and cross-grammar reuse for agent workloads. These are essential
baselines for format validity and engine integration. Low grammar overhead
does not mean eliminating the model's autoregressive generation cost.

### Tool Calling is Linearly Readable and Steerable in Language Models

- Submitted 2026-05-08.
- Paper: https://arxiv.org/html/2605.07990v1

Studies reading and steering tool identity in internal representations, with
arguments subsequently generated autoregressively. This is particularly close
to a model-internal selection-plus-generation proposal, although its goal is
analysis and intervention rather than a schema-driven object runtime.

The authors distinguish schema conformity from argument correctness, and
report fragile multi-turn transfer. On instruction-tuned models, their cosine
readout can underperform ordinary generation. The reported scope must not be
converted into a guarantee of reliable execution. No official implementation
repository for this paper was confirmed in this search.

## Implications for the experiment

For a fixed prompt, identical single-token candidates, and greedy decoding,
direct argmax over candidate logits selects the same token as greedy decoding
with all other tokens masked out. Calling the former classification does not
by itself establish a new algorithm or a speed advantage over an optimized
one-token engine path.

Possible research contributions still need to be demonstrated rather than
assumed: better decision accuracy for runtime-defined schemas, efficient
switching between selection and generation without repeated instructions,
correct token/cache boundaries, robust typed event/object output, and faster
end-to-end task completion at matched quality. Merely removing JSON punctuation
or wrapping existing `select`/`gen` calls is not enough to establish novelty.

The local prototype now includes protocol LoRA experiments, but remains a
Python orchestration implementation using an existing LM head, not an engine-native
typed-object protocol or a dedicated classification head. It should be compared with Jsonformer/Guidance-style
field execution and optimized schema-constrained generation before making
novelty or performance claims.


## Expanded GitHub/arXiv search: engine and tool-specific work

Checked 2026-09-18. Repository descriptions and paper results are author claims;
this search did not independently run or audit their benchmarks.

- **Thimble**: https://github.com/nikshepsvn/thimble . A 48M specialist with
  schema-owned structure, discrete decision points, value generation, and a
  tool-name readout. The C implementation contains choice scoring, a bilinear
  name head, forced context feeding and decoding:
  https://github.com/nikshepsvn/thimble/blob/master/cengine/thimble.c . This is
  substantial architectural overlap, not just a semantic router. Its documented
  scope is primarily extractive command-to-call work, not general prose.
- **ToolkenGPT**, NeurIPS 2023: https://arxiv.org/abs/2305.11554 ;
  https://github.com/Ber666/ToolkenGPT . Learns tool embeddings, selects a tool
  token, then completes arguments. It does not establish our host-owned field
  structure contract.
- **ToolGen**, ICLR 2025: https://arxiv.org/abs/2410.03439 ;
  https://github.com/Reason-Wang/ToolGen . Represents tools as unique tokens and
  trains retrieval/calling through generation; overlaps discrete tool choice
  followed by arguments, with learned tool inventory representation.
- **ToolSpec**, April 2026: https://arxiv.org/abs/2604.13519 . Schema-aware FSM
  drafting alternates fixed structure and variable-field speculation, with
  historical-call retrieval and target-model verification. It accelerates the
  existing generated token stream; this differs from constructing typed objects
  outside that stream. An official code repository was not confirmed here.
- **Natural Language Tools**, October 2025:
  https://arxiv.org/html/2510.14453v1 . Separates selection and response, but emits
  YES/NO text parsed with string/regex logic. Evaluation is parameterless tool
  selection, so it is not evidence of safe parameter construction.

### vLLM versus SGLang versus the intended design

vLLM already constrains inside inference, not solely in an agent harness.
Current documentation describes choice/JSON/grammar/structural-tag constraints
and strict tool-calling modes. Its tool interfaces still accommodate generated
text and model-specific parsers. Moving a parser into the engine alone is not
our distinction:
https://docs.vllm.ai/en/latest/features/tool_calling/ .

SGLang has both a serving runtime and a frontend language. Its official frontend
example selects a tool with `gen(..., choices=...)`, then branches to argument
`gen(...)`: https://docs.sglang.io/docs/references/frontend/frontend_tutorial .
Choice scoring includes sequence-normalized and first-token variants:
https://docs.sglang.io/docs/references/frontend/choices_methods . Thus we cannot
claim SGLang only generates full JSON. Historical compressed-FSM jump-forward
and llguidance fast-forward also predate our attempt to skip structural decode;
this does not assert every current serving path enables them.

Our intended engineering target is a schema-compiled field execution protocol
inside a serving engine, with typed object/event outputs and reply_user as a
mandatory action. The local experiment has only two tools, one enum, and one
string, orchestrated as three requests; an engine-native implementation remains
future work. Single-token classification through restricted LM logits is
mathematically the same argmax as greedy masked generation under the same
prompt and candidate set. Distinction must come from field protocol, cache/state
management, training and measured end-to-end execution, not the label
"classification". Such a runtime can be implemented on vLLM or SGLang rather
than replacing their batching and GPU kernels. These are engineering positioning
judgments inferred from the inspected sources, not proof of unique novelty.
