"""Report all expanded attempts, including failures and unexpected cache decisions."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def summarize(rows):
    accounts = [r.get('response', {}).get('accounting', {}) for r in rows]
    return dict(n=len(rows), passed=sum(r['passed'] for r in rows),
                seconds=sum(r['seconds'] for r in rows),
                median_seconds=statistics.median(r['seconds'] for r in rows),
                hits=sum(r.get('response', {}).get('cache_hit', False) for r in rows),
                **{key: sum(a.get(key, 0) for a in accounts) for key in
                   ['inference_requests', 'known_input_tokens', 'known_generated_argument_tokens',
                    'known_classification_control_records']})


def report(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    rows = [json.loads(s) for s in (folder / 'rows.jsonl').read_text().splitlines()]
    specs = {c['name']: c for c in manifest['cases']}
    assert len(rows) == len(specs) * len(manifest['arms']) * manifest['repeats']
    assert len(rows) == len({(r['case'], r['arm'], r['repeat']) for r in rows})
    source_checks = []
    for path in (folder / 'sources').rglob('*.py'):
        relative = path.relative_to(folder / 'sources')
        assert path.read_bytes() == (ROOT / relative).read_bytes(), str(relative)
        source_checks.append(dict(path=str(relative), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    failures, unexpected = [], []
    for i, row in enumerate(rows):
        response = row.get('response', {})
        account = response.get('accounting', {})
        assert account.get('usage_complete'), (i, 'Incomplete accounting')
        hit = response.get('cache_hit', False)
        if not row['passed']:
            failures.append(dict(attempt=i, **row))
        expected = row['arm'] == 'safe_book' and specs[row['case']]['expect_reuse']
        if hit != expected:
            unexpected.append(dict(attempt=i, case=row['case'], repeat=row['repeat'],
                                   arm=row['arm'], expected=expected, actual=hit))
        if hit:
            assert account['inference_requests'] == 0
            assert account['known_generated_argument_tokens'] == account['known_classification_control_records'] == 0
            assert (folder / 'attempts' / str(i) / 'book-before.json').exists()
        if row['arm'] == 'generate':
            assert not hit and response.get('admitted', 0) == 0
        if row['arm'] == 'safe_book' and row['case'].startswith('different_path'):
            project = (folder / 'workspace' / 'other').resolve()
            key = hashlib.sha256(str(project).encode()).hexdigest()[:20]
            book = folder / 'state' / f"{row['repeat']}-safe_book" / 'workspaces' / key / 'codebook.json'
            entries = json.loads(book.read_text())
            assert all(e['path'] == str(project / 'app.py') for e in entries)
            count = response['retrieval']['book_entries']
            assert (count == 0 and not hit) if row['case'] == 'different_path' else (count > 0 and hit)
        if row['arm'] == 'safe_book' and not specs[row['case']]['verify']:
            assert not hit and response.get('admitted', 0) == 0
            before = folder / 'attempts' / str(i) / 'book-before.json'
            after = before.with_name('book-after.json')
            assert before.read_bytes() == after.read_bytes()
    summaries = {}
    for scope in ['all', 'expected_warm', 'cold_or_rejected']:
        group = [r for r in rows if scope == 'all' or
                 specs[r['case']]['expect_reuse'] == (scope == 'expected_warm')]
        summaries[scope] = {arm: summarize([r for r in group if r['arm'] == arm])
                            for arm in manifest['arms']}
    percase = {name: {arm: summarize([r for r in rows if r['case'] == name and r['arm'] == arm])
                      for arm in manifest['arms']} for name in specs}
    repeats = [{arm: summarize([r for r in rows if r['repeat'] == repeat and r['arm'] == arm])
                for arm in manifest['arms']} for repeat in range(manifest['repeats'])]
    ids = [q['request_id'] for r in rows for q in r.get('response', {}).get('requests', [])
           if q['request_id'].startswith('openjev-')]
    events = [json.loads(s) for s in (folder / 'engine-events.jsonl').read_text().splitlines()]
    assert all(any(e.get('request_id', '').startswith(i) and e.get('sampler_bypassed') for e in events) for i in ids)
    assert (folder / 'server-before.txt').read_bytes() == (folder / 'server-after.txt').read_bytes()
    return dict(attempts=len(rows), summaries=summaries, percase=percase, repeats=repeats,
                failures=failures, unexpected_reuse_decisions=unexpected,
                source_checks=source_checks, generation_requests_verified=len(ids),
                scope=manifest['scope'],
                saved_fraction={scope: 1 - arms['safe_book']['seconds'] / arms['generate']['seconds']
                                for scope, arms in summaries.items()})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    data = report(args.folder)
    args.out.write_text(json.dumps(data, indent=2))
    print(json.dumps({k: v for k, v in data.items() if k not in ['percase', 'source_checks', 'failures']}, indent=2))
