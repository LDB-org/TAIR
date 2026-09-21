"""Recheck stored artifacts, admission history and per-request GPU event evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from benchmark_adaptive_plan import check_module


def audit(out):
    manifest = json.loads((out/'manifest.json').read_text())
    rows = [json.loads(line) for line in (out/'rows.jsonl').read_text().splitlines()]
    events = [json.loads(line) for line in (out/'engine-events.jsonl').read_text().splitlines()]
    assert len(rows) == len(manifest['jobs']) * manifest['repeats'] * 2
    checks = []
    for row in rows:
        assert row['passed'] and row['inference_requests'] == 1
        folder = out/'attempts'/f"{row['repeat']}-{row['stage']}-{row['arm']}"
        assert json.loads((folder/'result.json').read_text()) == row
        kinds = manifest['jobs'][row['stage']][1]
        before = json.loads((folder/'book-before.json').read_text())
        after = json.loads((folder/'book-after.json').read_text())
        assert len(before) == row['book_before'] and len(after) == row['book_after']
        if row['stage'] == 0:
            assert before == []
        else:
            previous = out/'attempts'/f"{row['repeat']}-{row['stage']-1}-{row['arm']}"/'book-after.json'
            assert before == json.loads(previous.read_text())
        before_ids = {e['id'] for e in before}
        assert {e['id'] for e in after} - before_ids == set(row['admitted'])
        for entry in after:
            assert hashlib.sha256(entry['source'].encode()).hexdigest() == entry['source_sha256']
            assert entry['verification']
        assert set(kinds) == {s['path'] for s in row['plan']['arguments']['steps']}
        for step in row['plan']['arguments']['steps']:
            path = folder/'project'/step['path']
            assert path.read_text() == step['content']
            check_module(path, kinds[step['path']])
            if step['op'] == 'reuse':
                entry = next(e for e in before if e['id'] == step['entry_id'])
                assert step['content'] == entry['source']
                assert entry['contract'] == manifest['contracts'][kinds[step['path']]]
            else:
                assert any(e['source'] == step['content'] and e['contract'] == manifest['contracts'][kinds[step['path']]] for e in after)
        if row['arm'] != 'engine':
            assert row['generated_tokens'] == row['response']['usage']['completion_tokens']
            continue
        response = row['response']
        request_id = response['request_id']
        related = [e for e in events if e['request_id'].startswith(request_id+'-') or e['request_id'] == request_id]
        classifications = [e for e in related if e['event'] == 'classify']
        pause = [e for e in related if e['event'] == 'retire_worker_slot']
        resume = [e for e in related if e['event'] == 'resume']
        assert classifications and all(e['sampler_bypassed'] for e in classifications)
        assert len(pause) == len(resume) == 1
        assert pause[0]['block_ids'] == resume[0]['block_ids']
        assert pause[0]['computed_tokens'] == resume[0]['computed_tokens'] > 0
        assert resume[0]['structured'] and response['same_engine_session']
        assert row['generated_tokens'] == len(response['argument_token_ids'])
        assert row['controls'] == response['classification_control_records'] == 1
        checks.append(dict(request_id=request_id, sampler_bypassed=True, retained_kv=True,
                           classifications=len(classifications), computed_tokens=pause[0]['computed_tokens']))
    summary = json.loads((out/'summary.json').read_text())
    grouped = {}
    for group, stages in [('new_contract', [0,2,6,8]), ('warm', [1,3,5,7,9]), ('mixed', [4])]:
        grouped[group] = {}
        for arm in summary:
            selected = [r for r in rows if r['arm']==arm and r['stage'] in stages]
            grouped[group][arm] = dict(attempts=len(selected), **{key:sum(r.get(key,0) for r in selected)
                for key in ['seconds','preparation_seconds','inference_seconds','generated_tokens','controls','logical_input_tokens','reuse_steps']})
    result = dict(attempts=len(rows), artifacts_passed=len(rows), engine_sessions_verified=len(checks),
                  classification_abandoned=sum(r.get('classification_abandoned',False) for r in rows),
                  final_engine_books={str(r):len(json.loads((out/'books'/f'{r}-engine.json').read_text())['entries']) for r in range(manifest['repeats'])},
                  engine_evidence=checks, all=summary, groups=grouped)
    (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    args = parser.parse_args()
    result = audit(args.out)
    print(json.dumps({k:v for k,v in result.items() if k!='engine_evidence'},indent=2))
