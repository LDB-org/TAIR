"""Replay archived JSON with the pinned tokenizer; no inference or execution."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deploy'))
import local_tokenizer
import vllm_direct_tools as engine


def responses(value):
    if isinstance(value, dict):
        if isinstance(value.get('raw'), str) and value.get('call', {}).get('name') == 'plan':
            yield value
        for child in value.values():
            yield from responses(child)
    elif isinstance(value, list):
        for child in value:
            yield from responses(child)


def main(tokenizer, output):
    revision = hashlib.sha256((tokenizer / 'manifest.json').read_bytes()).hexdigest()
    def encode(text):
        return local_tokenizer.encode(dict(prompt=text, add_special_tokens=False), str(tokenizer), revision)
    encode('warm tokenizer')
    rows, seen = [], set()
    for name in ('plan-budget-live-20260920-a', 'plan-order-probe-20260921-a', 'plan-order-probe-20260921-b'):
        for path in sorted((ROOT / 'results/experiments' / name).glob('*.json')):
            for response in responses(json.loads(path.read_text())):
                raw = response['raw']
                digest = hashlib.sha256(raw.encode()).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                args = json.loads(raw)
                expected = engine.measure_plan_arguments(args, encode)
                assert not expected['exceeded_steps']
                archived_budget = response.get('plan_budget')
                if archived_budget:
                    assert expected['argument_tokens'] == archived_budget['argument_tokens']
                if set(args) == {'content'}:
                    continue  # Not covered by the experimental streaming check.
                profiles = []
                for chunk_size in (1, 32, 256):
                    elapsed = []
                    for _ in range(5):
                        guard = engine.StreamingPlanBudget(encode)
                        begin = time.perf_counter()
                        for end in range(chunk_size, len(raw)+chunk_size, chunk_size):
                            guard.feed(raw[:end])
                        elapsed.append(time.perf_counter()-begin)
                        assert [guard.counts[i] for i in range(len(expected['argument_tokens']))] == expected['argument_tokens']
                    profiles.append(dict(chunk_characters=chunk_size, median_seconds=statistics.median(elapsed)))
                rows.append(dict(source=str(path.relative_to(ROOT)), raw_sha256=digest,
                                 characters=len(raw), argument_tokens=expected['argument_tokens'],
                                 archived_budget_checked=bool(archived_budget), profiles=profiles))
    assert rows
    report = dict(method='Offline completed-output replay, five repetitions per chunk size; local CPU cost, not GPU latency or speedup.',
                  tokenizer_revision=revision, unique_plans=len(rows), false_rejections=0, rows=rows,
                  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), ROOT/'deploy/vllm_direct_tools.py')})
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(unique_plans=len(rows), false_rejections=0,
                         max_median_seconds=max(p['median_seconds'] for r in rows for p in r['profiles']))))


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
