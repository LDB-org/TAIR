"""Verify classification bypass and retained KV against per-request engine events."""
import argparse
import json
from pathlib import Path


def verify(directory, event_path):
    rows = [json.loads(line) for line in (directory/'rows.jsonl').read_text().splitlines()]
    inputs = json.loads((directory/'inputs.json').read_text())
    cases = json.loads((directory/'cases.json').read_text())
    events = [json.loads(line) for line in event_path.read_text().splitlines()]
    names = {c[0] for c in cases}
    repeats = {r['repeat'] for r in rows}
    expected = {(n, repeat, mode) for n in names for repeat in repeats for mode in ['whole', 'direct']}
    assert len(rows) == len(expected)
    assert {(r['case'], r['repeat'], r['mode']) for r in rows} == expected
    checked = []
    for row in rows:
        assert not row.get('error') and row['complete']
        if row['mode'] != 'direct':
            continue
        response = row['response']
        request_id = response['request_id']
        trace = [e for e in events if e['request_id'].startswith(request_id+'-')]
        classifications = [e for e in trace if e['event'] == 'classify']
        retire = [e for e in trace if e['event'] == 'retire_worker_slot']
        resume = [e for e in trace if e['event'] == 'resume']
        assert classifications and all(e['sampler_bypassed'] and e['runner'] == 'v2' for e in classifications)
        assert len(retire) == len(resume) == 1
        body = inputs[row['case']]['direct']
        selected = response['decision']['index']
        scores = response['decision']['logprobs']
        assert selected == max(range(len(scores)), key=scores.__getitem__)
        prefix = len(body['prompt_ids'])
        suffix = len(body['continuations'][selected])
        assert retire[0]['computed_tokens'] == resume[0]['computed_tokens'] == prefix
        assert retire[0]['block_ids'] == resume[0]['block_ids']
        assert resume[0]['prompt_tokens'] == prefix + suffix
        assert resume[0]['structured'] and resume[0]['max_tokens'] == body['max_tokens']
        assert response['decision']['control_id'] == body['candidate_ids'][selected]
        assert response['generated_argument_tokens'] == len(response['argument_token_ids'])
        checked.append({'request_id': request_id, 'prefix_tokens_reused': prefix,
                        'injected_prefill_tokens': suffix,
                        'mixed_batch': any(e['normal_rows_sampled'] for e in classifications)})
    return {'verified_calls': len(checked), 'mixed_batch_calls': sum(c['mixed_batch'] for c in checked),
            'classification_sampled_tokens': 0, 'classification_control_records': len(checked),
            'checks': checked}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('events', type=Path)
    a = p.parse_args()
    print(json.dumps(verify(a.directory, a.events), indent=2))
