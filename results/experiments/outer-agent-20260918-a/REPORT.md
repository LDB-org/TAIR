# Outer Agent overhead optimization: matched cold/warm comparison

36/36 complete task attempts passed the existing external behavior checks, including
recovery costs. Three selected small Python tasks, two independent repeats, three
arms, two rounds. Native = stock Pi on the same patched vLLM. Previous = expanded
schema/JIT/local routing. Optimized = previous plus continuation-token caching and
directory-read guard. Model, scheduler, output budget and task prompts are unchanged.
No server restart, model change, excluded warmup, discarded formal sample or retry.

## Complete task time

Arithmetic means, including process startup, Agent planning, tools, project tests,
recovery and final answer, plus the independent final task oracle. Preparation of
fixtures is excluded. Round two restores original files at the same absolute path,
retains runtime caches/codebook, and uses a fresh Agent session. Baselines also get
both rounds. Cold continuation calibration is included in first-round timing.

| All tasks | Previous | Optimized | Native |
|---|---:|---:|---:|
| First round (6 attempts each) | 13.013 s | 11.016 s | 10.889 s |
| Second round (6 attempts each) | 11.207 s | 10.953 s | 10.415 s |
| Both rounds (12 attempts each) | 12.110 s | 10.984 s | 10.652 s |

Optimized uses 9.3% less time than previous across all formal attempts, but is still
3.1% slower than native. The second round alone improves only 2.3% versus previous
and remains 5.2% slower than native. This is an observed small-sample result, not a
statistically established general Agent speedup.

| Second-round task (2 repeats each) | Previous | Optimized | Native |
|---|---:|---:|---:|
| Five CLI properties | 9.721 s | 8.330 s | 9.477 s |
| Add CLI alias | 8.653 s | 6.651 s | 8.190 s |
| General summary bug | 15.245 s | 17.879 s | 13.578 s |

Both covered tasks improved in each independent repeat. General summary repair
regressed in the second round: one optimized attempt took 19.737 s and recovered
from an exact-text edit mismatch in test_app.py by reading and editing again. It
remains in all totals. More tool/planning steps can outweigh preparation savings.
Both rounds and all task types are reported to avoid selecting only favorable runs.
The independent summary oracle checks selected behavior, not exhaustive quality;
its added tests and generated source are retained for review.

## Evidence for the mechanisms

For a second-round five-property task, tokenize HTTP requests fell from 35 to 4,
outer inference requests from 5 to 4, and mean preparation time from 1.945 to 1.120 s.
Alias preparation fell from 2.116 to 1.148 s with the same 35-to-4 tokenize reduction.
The scope here is client preparation, not GPU kernel time. Native does not use this
client's separate tokenize calls, so zero native client-preparation records must
not be interpreted as zero tokenization or prefill work.

Across all optimized tasks, continuation-cache hits = 56; admission rejections = 0.
Eight selected directory reads were converted to quoted read-only listings before
execution. Previous had 11 tool errors, optimized had one (the retained exact-text
edit failure), native had zero. A directory guard does not remove the already-paid
model call that selected read; it avoids the failed execution and recovery round.

Each custom arm retains 12/12 covered second-round JIT edit hits. Audit verified
157 model classifications against server sampler-bypass events and all 24 JIT
edits made zero HTTP/model requests. Cache reuse changes preparation work, not the
intended input tokens: a separate live probe checked exact token equivalence for
short, long and Chinese histories against full tokenization. Calibration is tied
to this pinned tokenizer/template and is not proof for arbitrary deployments.

Previous generated 5296 argument tokens over all tasks; optimized generated 5487.
Despite slightly more generated output, optimized was faster on aggregate. Input
counts were 213570 vs 189819. Controls, inputs, output and timing are kept separate
in analysis.json and raw rows. This optimization is not attributed to token count
reduction alone. No isolated cache-only/guard-only full-Agent ablation was run, so
the aggregate speed change is for the combined optimization.

## Environment and preservation

Tokenizer/config hashes were verified live and are retained in the preparation
probe archive. All runtime sources stayed unchanged during this formal run.
Runtime caches/profile files were temporary and are excluded from the archive.
Source snapshots, all raw events, learned codebooks, metrics and final files are
retained. The proxy and CyberEdge services remain frozen; final engine running/
waiting counters are zero and restart count is zero. A one-second monitor began
after run start and observed running/waiting at most one; this cannot rule out
subsecond queue waits or attribute every observed request to a user.
