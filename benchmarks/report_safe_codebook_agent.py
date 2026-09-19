"""Full Agent timing, editing costs and independently rechecked repository artifacts."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def aggregate(rows):
    records = [m for r in rows for m in r['metrics']]
    edits = [m for m in records if m['action'] == 'edit']
    return dict(tasks=len(rows), passed=sum(r['passed'] for r in rows),
                artifacts_passed=sum(r['validation']['passed'] for r in rows),
                seconds=sum(r['validated_seconds'] for r in rows),
                median_seconds=statistics.median(r['validated_seconds'] for r in rows),
                timeouts=sum(r['timed_out'] for r in rows),
                usage_complete=all(r['usage_complete'] for r in rows),
                tool_errors=sum(r['tool_errors'] for r in rows),
                outer_requests=sum(m['accounting']['inference_requests'] for m in records if m['action'] == 'chat'),
                edit_requests=sum(m['accounting']['inference_requests'] for m in edits),
                edit_bridge_seconds=sum(m['wall_seconds'] for m in edits),
                cache_hits=sum(m.get('cache_hit', False) for m in edits),
                bound_hits=sum(m.get('bound_reuse_hit', False) for m in edits),
                exact_hits=sum(m.get('exact_reuse_hit', False) for m in edits),
                **{key: sum(m['accounting'][key] for m in records) for key in
                   ['inference_requests', 'known_input_tokens', 'known_generated_argument_tokens',
                    'known_classification_control_records', 'unknown_usage_requests']})


def report(folder, *, verify_current_sources=True):
    rows = [json.loads(s) for s in (folder / 'rows.jsonl').read_text().splitlines()]
    manifest = json.loads((folder / 'manifest.json').read_text())
    planned = sum(manifest['rounds_by_case'].values()) * len(manifest['arms']) * manifest['repeats']
    assert len(rows) == planned == len({(r['case'], r['arm'], r['repeat'], r['round']) for r in rows})
    configs = manifest['configurations']
    on, off = configs['hybrid'], configs['hybrid_no_book']
    assert {k for k in on.keys() | off.keys() if on.get(k) != off.get(k)} == {'PIJIT_DISABLE_CODEBOOK'}
    assert on['PIJIT_SAFE_CODEBOOK'] == off['PIJIT_SAFE_CODEBOOK'] == '1'
    for relative, digest in manifest['source_sha256'].items():
        if verify_current_sources:
            assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
        assert hashlib.sha256((folder / 'sources' / relative).read_bytes()).hexdigest() == digest, relative
    assert (folder / 'server-before.txt').read_bytes() == (folder / 'server-after.txt').read_bytes()
    audits = []
    for row in rows:
        path = folder / f"{row['repeat']}-{row['case']}-{row['arm']}-{row['round']}"
        run = subprocess.run([sys.executable, '-B', str((path / 'oracle.py').resolve())],
                             cwd=path / 'project-after', capture_output=True, text=True, timeout=30,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        scope_ok = True
        if row['case'] == 'cpython_md5_positive_buffer':
            before, after = (ast.parse((path / name).read_text()) for name in ['before.py', 'after.py'])
            for tree in [before, after]:
                tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == 'main')]
            scope_ok = ast.dump(before) == ast.dump(after)
        audits.append(dict(case=row['case'], arm=row['arm'], repeat=row['repeat'], round=row['round'],
                           passed=run.returncode == 0 and scope_ok, only_requested_scope=scope_ok,
                           error=run.stderr if run.returncode else ''))
        assert (run.returncode == 0) == row['validation']['passed'], 'Artifact result changed'
        row['passed'] &= scope_ok
        for record in row['metrics']:
            if record.get('cache_hit'):
                assert configs[row['arm']]['PIJIT_DISABLE_CODEBOOK'] == '0'
                assert record['accounting']['inference_requests'] == 0
                assert record['accounting']['known_generated_argument_tokens'] == 0
        if row['arm'] == 'native_multi':
            native = [json.loads(s) for s in (path / 'native-inference.jsonl').read_text().splitlines()]
            assert all(e['payload']['parallel_tool_calls'] for e in native if e['event'] == 'request')
    scopes = {'all': rows, 'warm': [r for r in rows if r['round'] > 1],
              'cold': [r for r in rows if r['round'] == 1],
              'new_tasks': [r for r in rows if r['case'].startswith('rich_') or r['case'] in ['cpython_untabify_default', 'cpython_md5_positive_buffer']]}
    summaries = {scope: {arm: aggregate([r for r in items if r['arm'] == arm]) for arm in manifest['arms']}
                 for scope, items in scopes.items()}
    percase = {case: {arm: aggregate([r for r in rows if r['case'] == case and r['arm'] == arm])
                      for arm in manifest['arms']} for case in manifest['cases']}
    repeats = [{arm: aggregate([r for r in rows if r['repeat'] == repeat and r['arm'] == arm])
                for arm in manifest['arms']} for repeat in range(manifest['repeats'])]
    ids = {q['request_id'] for r in rows for m in r['metrics'] for q in m.get('http_requests', [])
           if (q.get('request_id') or '').startswith('openjev-')}
    events = [json.loads(s) for s in (folder / 'engine-events.jsonl').read_text().splitlines()]
    assert all(any(e.get('request_id', '').startswith(i) and e.get('sampler_bypassed') for e in events) for i in ids)
    return dict(attempts=len(rows), summaries=summaries, percase=percase, repeats=repeats,
                artifact_audits=audits, engine_requests_verified=len(ids),
                failures=[{k: r[k] for k in ['arm', 'case', 'repeat', 'round', 'timed_out', 'finished',
                                             'protected_changes', 'test_integrity']} for r in rows if not r['passed']],
                limitations=f"{len(rows)} full Agent attempts on {len(manifest['cases'])} finite tasks in the pinned {manifest.get('repository_suite', 'cpython')} repository suite. No hidden oracle in Agent context or runtime verification command. Generic unbound edits are not learned without project verification. Warm fixtures restore original source. Shared already-patched backend; native uses ordinary tools API. Not a production hit-rate or universal speed estimate.")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--frozen-sources', action='store_true',
                   help='Verify archived source hashes without requiring the current checkout to match')
    args = p.parse_args()
    data = report(args.folder, verify_current_sources=not args.frozen_sources)
    args.out.write_text(json.dumps(data, indent=2))
    print(json.dumps({k: v for k, v in data.items() if k not in ['percase', 'artifact_audits']}, indent=2))
