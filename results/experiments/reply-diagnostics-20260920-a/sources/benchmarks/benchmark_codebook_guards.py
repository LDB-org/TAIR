"""Direct candidate-gate challenges; no candidate is applied to a file."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from benchmark_codebook_reuse import CHALLENGES, GUARD_SOURCE, ROOT, bridge

SOURCE = GUARD_SOURCE.replace('    return p', "    p.add_argument('--ratio', type=float, default=1.25)\n    p.add_argument('--flag', action='store_true', default=False)\n    return p")
EXTRA = [
    ('alias_wrong', 'Add alias -t to --timeout.', [['arg', '--timeout', '-x']], False),
    ('alias_correct', 'Add alias -t to --timeout.', [['arg', '--timeout', '-t']], True),
    ('float_wrong_type', 'Change --ratio default to 2.0.', [['kw', '--ratio', 'default', 2]], False),
    ('float_correct', 'Change --ratio default to 2.75.', [['kw', '--ratio', 'default', 2.75]], True),
    ('boolean_wrong', 'Change --flag default to true.', [['kw', '--flag', 'default', False]], False),
    ('boolean_correct', 'Change --flag default to true.', [['kw', '--flag', 'default', True]], True),
    ('unicode_correct', '将 --timeout 的帮助文本改为 "等待时间"。', [['kw', '--timeout', 'help', '等待时间']], True),
]


def worker(args):
    payload = json.load(sys.stdin)
    os.environ['PIJIT_URL'] = payload['url']
    b = bridge(args.worker.resolve(), 'guard_bridge')
    trace = {'stage_seconds': {}, 'http_requests': []}
    token = b.TRACE.set(trace)
    try:
        selected, record = b.pick_cached(SOURCE, payload['task'], [{'id': 0, 'edits': payload['edits']}])
        result = {'accepted': selected is not None, 'record': record, 'trace': trace}
    except Exception as error:
        result = {'error': str(error), 'trace': trace}
    finally:
        b.TRACE.reset(token)
    print(json.dumps(result))


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cases = CHALLENGES + EXTRA
    (out/'manifest.json').write_text(json.dumps({'source': SOURCE, 'cases': cases,
        'method': 'direct gate probes bypass retrieval; separate worker per arm/case; negatives may not be normally admissible; no edits executed; no retries'}, ensure_ascii=False, indent=2))
    with (out/'rows.jsonl').open('x') as stream:
        for name, task, edits, expected in cases:
            for arm, root in [('previous', args.legacy_root), ('expanded', ROOT)]:
                child = subprocess.run([sys.executable, __file__, '--worker', str(root)],
                    input=json.dumps({'url': args.url, 'task': task, 'edits': edits}),
                    text=True, capture_output=True, timeout=210)
                result = json.loads(child.stdout) if child.returncode == 0 else {'error': child.stderr}
                row = {'case': name, 'arm': arm, 'expected_accept': expected,
                       'correct': 'error' not in result and result['accepted'] == expected, 'result': result}
                stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                stream.flush()
                print(name, arm, row['correct'], result.get('accepted'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--legacy-root', type=Path)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    if args.worker:
        worker(args)
    elif args.out and args.legacy_root:
        main(args)
    else:
        parser.error('--out and --legacy-root are required')
