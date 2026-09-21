# Same-request correction after a forced wrong native classification

2026-09-21. Experimental native branches accepted either their original `first/rest` arguments, a general `steps` plan, or a final `content` reply. This allowed the generation stage to reject the selected first tool without another model request. Decoding retained native tool schema validation, eight-step bounds, reply behavior and conditional-completion support. Five local tests passed for these paths; this proved format support, not model adoption.

Two paired component experiments tested Python/JavaScript requirements to run a specified check first or read a specified file before any command. The wrong native branch was deliberately forced by allowing only its existing classification label. Baseline could not correct that first native action through its original schema; candidate could emit a general plan. Each case and arm used one model request with real captured Pi 0.85.1 context, an empty isolated codebook and identical user requirements. Generated tools were not executed. This tests robustness to a supplied wrong decision, not natural classification accuracy or Agent completion.

A added an escape instruction after the existing selected-tool instruction. B replaced that instruction with an explicit provisional-tool description and required evaluating the requested order before choosing the output format.

| Run | Baseline first action matched | Fallback first action matched | Fallback envelope actually used | Baseline / fallback input tokens |
|---|---:|---:|---:|---:|
| A | 0/4 | 0/4 | 0/4 | 11961 / 16501 |
| B | 0/4 | 0/4 | 0/4 | 11957 / 16537 |

All eight candidate requests retained `first/rest`; none adopted the legal correction path. Read-first fixtures explicitly forbid a preceding command, so generating `bash: cat ...` does not satisfy their requirement. The added general schema costs roughly 1135–1145 additional logical input tokens per tested request. These results provide no quality or latency benefit. They do not prove every possible same-request correction scheme will fail.

The runtime implementation, environment switch and temporary tests were removed after B. Current `deploy/tool_plan.py` and `integrations/pijit/bridge.py` were checked byte-for-byte against their pre-experiment frozen versions. The candidate implementations remain in frozen experiment sources for reproduction. Nothing was deployed or pushed; user codebooks were untouched. The existing service was DeepSeek-V4-Flash-Vision-Exp on six RTX 5090 GPUs, TP2/PP3, with one request at a time.

`probe_plan_order.py --forced-fallback` now requires an explicit `--bridge` pointing to a frozen candidate implementation, so it cannot silently test the reverted runtime as if fallback still existed. For example, pass `results/experiments/native-fallback-probe-20260921-b/sources/integrations/pijit/bridge.py`, `--pi-context`, the pinned `--tokenizer`, and a fresh `--out` directory.

Evidence caveat: A inherited an incorrect generic method sentence saying natural classification and identical schemas. Its `forced_fallback=true`, recorded `forced_index`, captured schemas and source show the actual forced-decision intervention described above. B corrects the method sentence. Frozen A remains unchanged; the correction is also recorded in [NATIVE_FALLBACK_PROBE.json](NATIVE_FALLBACK_PROBE.json).
