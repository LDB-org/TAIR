# First-action order diagnosis

2026-09-21. In the full Agent run `empty-candidate-prompt-20260921-a`, `repair_failure-tair_no_reuse` selected the native `read` branch even though the user explicitly requested `python3 check_calc.py` first. Its recorded classification log probabilities were -0.562765 for read and -0.937765 for bash. The native-action schema then requires the selected action in `first`; generated continuation followed that choice. The immediate workflow oracle marked this failure despite the correct final artifact. This evidence locates that particular ordering violation at classification, not at tool execution.

`benchmarks/probe_plan_order.py` compares the existing classifier prompt with one additional generic instruction to honor explicit first-operation order. It does not hardcode tool names or parse request keywords. Four authored first-action requirements cover Python/JavaScript and check-first/read-first. Each arm makes one natural classification plus generation request, with identical tool schemas, context and branch continuations within a pair. Generated tools are never executed. This is not an Agent completion or speed benchmark.

Run A uses minimal context. Run B obtains the real current Pi 0.85.1 initial payload by running the plan-only integration with a capture-only bridge that returns a fixture reply without inference or tools. Each captured payload is then reused unchanged for both inference arms, with the classifier instruction as the sole intervention. The captured system prompt is real current Pi context, not a byte-for-byte recreation of the earlier failing run (temporary paths and context differ).

| Experiment | Existing prompt, first action matched | Order reminder, first action matched |
|---|---:|---:|
| Minimal context, A | 4/4 | 4/4 |
| Captured Pi context, B | 4/4 | 4/4 |

Both use the existing Yuesheng DeepSeek-V4-Flash-Vision-Exp service on six RTX 5090 GPUs, TP2/PP3, serial requests and isolated empty books. There are 16 total model requests, no semantic execution checks and no service restart. Classification log-probability margins are recorded only as diagnostic scores, not calibrated correctness probabilities. In B the Python check-first margin rises from 1.0 to 5.75, but the JavaScript read-first margin falls from 6.5 to 5.625. All actual first-action outcomes remain unchanged.

The small probe does not reproduce the earlier failure and therefore does not demonstrate its repair. The reminder is not added to the runtime default. Reliable acceptance requires repeated full-Agent evaluations with captured exact request context, both operation orders and unchanged output/flow checks. Do not infer latency improvements from these first-response timings.

Frozen evidence: `results/experiments/plan-order-probe-20260921-a` and `results/experiments/plan-order-probe-20260921-b`. The probe freezes source and records both request construction and model output. Summary: [PLAN_ORDER_PROBE.json](PLAN_ORDER_PROBE.json).
