"""Complete accounting for direct option readout and cached arguments."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(root):
    manifest = json.loads((root/'manifest.json').read_text())
    rows = [json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()]
    modes = manifest['metadata']['methods']
    expected = {(c[0], n, mode) for c in manifest['cases']
                for n in range(manifest['metadata']['repeats']) for mode in modes}
    assert len(rows) == len(expected)
    assert {(r['case'],r['repeat'],r['mode']) for r in rows} == expected
    summary = {}
    for mode in modes:
        xs = [r for r in rows if r['mode'] == mode]
        result = {'n':len(xs),'tool_correct':sum(r['tool_correct'] for r in xs),
                  'exact_call':sum(r['exact_call'] for r in xs),'complete':sum(r['complete'] for r in xs),
                  'output_tokens_including_eos':sum(r['output_tokens_including_eos'] for r in xs),
                  'total_seconds':sum(r['seconds'] for r in xs),'median_seconds':statistics.median(r['seconds'] for r in xs),
                  'prefill_processed_tokens':sum(r['prefill_processed_tokens'] for r in xs),
                  'generation_seconds':sum(r['generation_seconds'] for r in xs),
                  'forward_calls':sum(len(r['forwards']) for r in xs)}
        if mode != 'whole':
            result.update(same_cache_objects=sum(r['decision']['same_cache_object'] for r in xs),
                          classification_sampled_tokens=sum(r['decision']['classification_sampled_tokens'] for r in xs),
                          classification_seconds=sum(r['forwards'][0]['seconds'] for r in xs),
                          argument_prefill_seconds=sum(r['forwards'][1]['seconds'] for r in xs))
        summary[mode] = result
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path)
    args = p.parse_args();result = summarize(args.root)
    with (args.root/'summary.json').open('x') as output: json.dump(result,output,indent=2)
    print(json.dumps(result,indent=2))
