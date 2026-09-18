"""Same-engine comparison of plain JSON, constrained JSON, and typed fields."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics

import schema_toolcall as base


class VllmSession:
    structured = False

    def __init__(self, model, tokenizer):
        self.model, self.tokenizer = model, tokenizer
        self.transcript = ""
        self.trace = []
        self.forward_calls = 0
        self.input_tokens = 0

    def prompt(self, messages):
        text = self.transcript + self.tokenizer.apply_chat_template(
            messages if not self.transcript else [messages[-1]],
            tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        self.trace.append({"prompt": text, "sha256": hashlib.sha256(text.encode()).hexdigest()})
        return text

    def request(self, text, parameters):
        result = self.model.generate([text], parameters, use_tqdm=False)[0]
        self.forward_calls += 1
        self.input_tokens += len(result.prompt_token_ids)
        self.trace[-1]["finish_reason"] = result.outputs[0].finish_reason
        return result.outputs[0]

    def choose(self, messages, values):
        from vllm import SamplingParams
        labels = "ABCDEFGHIJKLMNOP"[:len(values)]
        messages[-1]["content"] += "\nSelect one value. Reply with its letter only.\n" + "\n".join(
            f"{label}: {value}" for label, value in zip(labels, values)
        )
        text = self.prompt(messages)
        ids = self.tokenizer.encode(text, add_special_tokens=False)
        slots = []
        for label in labels:
            token = self.tokenizer.encode(label, add_special_tokens=False)
            if len(token) != 1 or self.tokenizer.decode(token) != label:
                raise ValueError("Option must be an exact single token")
            if self.tokenizer.encode(text + label, add_special_tokens=False) != ids + token:
                raise ValueError("Option token boundary changed")
            slots.extend(token)
        result = self.request(text, SamplingParams(
            temperature=0, max_tokens=1, allowed_token_ids=slots, logprobs=len(slots),
        ))
        if len(result.token_ids) != 1 or result.token_ids[0] not in slots:
            raise ValueError("Classification did not return a declared slot")
        selected = slots.index(result.token_ids[0])
        self.trace[-1]["returned_logprobs"] = {
            str(key): value.logprob for key, value in result.logprobs[0].items()
        }
        messages.append({"role": "assistant", "content": labels[selected]})
        if self.tokenizer.eos_token != "<|im_end|>":
            raise ValueError("This adapter requires Qwen ChatML")
        self.transcript = text + labels[selected] + self.tokenizer.eos_token + "\n"
        return values[selected]

    def generate(self, messages, limit):
        from vllm import SamplingParams
        from vllm.sampling_params import StructuredOutputsParams
        params = SamplingParams(
            temperature=0, max_tokens=limit,
            structured_outputs=StructuredOutputsParams(json=base.SCHEMA) if self.structured else None,
        )
        result = self.request(self.prompt(messages), params)
        return result.text, len(result.token_ids), result.finish_reason == "stop"


def main():
    from vllm import LLM
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists() or args.repeats < 1:
        parser.error("Require a new output path and positive repeats")
    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        parser.error("Require nonempty cases with unique IDs")
    settings = dict(dtype="bfloat16", max_model_len=4096, max_num_seqs=1,
                    gpu_memory_utilization=0.55, enforce_eager=True,
                    enable_prefix_caching=True, trust_remote_code=False, seed=0)
    engine = LLM(model=args.model, revision=args.revision, **settings)
    tokenizer = engine.get_tokenizer()
    base.Session = VllmSession
    modes = ["json", "json_schema", "hybrid"]

    def one(case, mode):
        if not engine.reset_prefix_cache():
            raise RuntimeError("Cannot clear cross-request prefix cache")
        VllmSession.structured = mode == "json_schema"
        row = base.run(engine, tokenizer, case, "hybrid" if mode == "hybrid" else "json", 128)
        row["mode"] = mode
        row["request_count"] = row.pop("forward_calls")
        row["submitted_prompt_tokens"] = row.pop("processed_input_tokens")
        return row

    for mode in modes:
        one(base.CASES[0], mode)
    records = []
    for repeat in range(args.repeats):
        for index, case in enumerate(cases):
            offset = (index + repeat) % len(modes)
            for mode in modes[offset:] + modes[:offset]:
                row = {"repeat": repeat, **one(case, mode)}
                records.append(row)
                print(json.dumps({key: row[key] for key in ["repeat", "case_id", "mode", "seconds", "valid", "exact_match"]}), flush=True)
    summary = {}
    for mode in modes:
        rows = [row for row in records if row["mode"] == mode]
        summary[mode] = {"runs": len(rows), "median_seconds": statistics.median(row["seconds"] for row in rows)}
        for key in ["valid", "exact_match", "discrete_correct", "generated_tokens_including_eos", "request_count"]:
            summary[mode][key] = sum(row[key] for row in rows)
    report = {
        "schema": "openjev-schema-toolcall-vllm-v1", "model": args.model, "revision": args.revision,
        "versions": {name: importlib.metadata.version(name) for name in ["vllm", "torch", "transformers"]},
        "environment": {name: os.environ.get(name) for name in ["CUDA_VISIBLE_DEVICES", "VLLM_USE_V2_MODEL_RUNNER", "VLLM_WORKER_MULTIPROC_METHOD", "VLLM_USE_FLASHINFER_SAMPLER"]},
        "engine_settings": settings, "schema_definition": base.SCHEMA,
        "cases": cases, "summary": summary, "records": records,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol_runner_sha256": hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest(),
        "limits": ["No tools executed", "Eager batch-one desktop experiment, not production throughput",
                   "Prefix cache reset outside timing before every independent call; retained between hybrid fields",
                   "Classification is one allowed-token greedy engine request, not a custom classification head",
                   "Timing includes host orchestration, requests, validation and serialization; excludes initialization/warmup",
                   "Submitted prompt tokens include cached prefixes and are not fresh compute counts"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
