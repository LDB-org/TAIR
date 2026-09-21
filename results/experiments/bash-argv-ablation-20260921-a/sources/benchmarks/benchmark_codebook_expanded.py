"""Cross-process, typed and multi-operation codebook evaluation on an existing engine."""
import argparse
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import sys
import time

from benchmark_codebook_reuse import ROOT, bridge
from benchmark_native_codebook import native

CLI = '''import argparse

def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--timeout', type=float, default=1.5, help='Timeout')
    p.add_argument('--host', default='localhost')
    p.add_argument('--verbose', action='store_true', default=False)
    p.add_argument('--token', default='', required=False)
    return p

def checksum(values):
    return sum(values) % 65536
'''


def cli_check(option, prop, value, aliases=()):
    return ('p=app.build_parser()\n'
            f'a=next(a for a in p._actions if {option!r} in a.option_strings)\n'
            f'assert a.{prop} == {value!r} and type(a.{prop}) is {type(value).__name__}\n'
            'assert len(p._actions)==6\nassert app.checksum([65536,3])==3\n'
            'parsed=p.parse_args(["--workers","9","--timeout","0.5","--host","explicit","--token","provided"])\n'
            'assert (parsed.workers,parsed.timeout,parsed.host,parsed.token)==(9,0.5,"explicit","provided")\n' +
            ''.join(f'assert p.parse_args([{alias!r},"0.25","--token","x"]).timeout==0.25\n' for alias in aliases))


def workloads():
    cases = []
    properties = [
        ('integer', '--workers', 'default', [7, 11, 13]),
        ('float', '--timeout', 'default', [2.75, 3.125, 4.5]),
        ('string', '--host', 'default', ['edge.local', 'cache.internal', '备用节点']),
        ('boolean', '--verbose', 'default', [True, False, True]),
        ('help', '--timeout', 'help', ['Wait duration', '等待秒数', 'Connection deadline']),
        ('required', '--token', 'required', [True, False, True]),
    ]
    for family, option, prop, values in properties:
        tasks = [f'Change {option} {prop} to {json.dumps(value, ensure_ascii=False)}.' for value in values]
        tasks[1] = f'Update the {prop} value for {option} to {json.dumps(values[1], ensure_ascii=False)}.'
        if family == 'help':
            tasks[1] = '将 --timeout 的帮助文本改为 "等待秒数"。'
        cases.append({'name': family, 'source': CLI, 'tasks': tasks,
                      'checks': [cli_check(option, prop, v) for v in values],
                      'variant_continues': family in ('boolean', 'required')})
    cases.append({'name': 'alias', 'source': CLI,
                  'tasks': ['Add alias -t to --timeout.', 'Add alias -u to --timeout.', 'Add alias -v to --timeout.'],
                  'checks': [cli_check('--timeout', 'default', 1.5, ['-t']),
                             cli_check('--timeout', 'default', 1.5, ['-u']),
                             cli_check('--timeout', 'default', 1.5, ['-u', '-v'])]})
    cases.extend([
        {'name': 'return_guard', 'source': 'def safe_divide(a, b):\n    return a / b\n',
         'tasks': ['In safe_divide, return None immediately when b == 0.',
                   'In safe_divide, return 0 immediately when b == 0.'],
         'checks': ['assert app.safe_divide(7,0) is None\nassert app.safe_divide(9,3)==3\n',
                    'assert app.safe_divide(7,0)==0\nassert app.safe_divide(9,3)==3\n']},
        {'name': 'raise_guard', 'source': 'def connect(timeout):\n    return timeout * 2\n',
         'tasks': ['In connect, raise ValueError with message "negative" when timeout < 0.',
                   'In connect, raise ValueError with message "too small" when timeout < 1.'],
         'checks': ['assert app.connect(2)==4\ntry:\n app.connect(-1)\nexcept ValueError as e:\n assert str(e)=="negative"\nelse:\n raise AssertionError("missing exception")\n',
                    'assert app.connect(2)==4\ntry:\n app.connect(0)\nexcept ValueError as e:\n assert str(e)=="too small"\nelse:\n raise AssertionError("missing exception")\n']},
        {'name': 'catch', 'source': 'def parse_count(text):\n    value = int(text)\n    return value\n',
         'tasks': ['In parse_count, catch ValueError from value = int(text) and return 0.',
                   'In parse_count, catch ValueError from value = int(text) and return -1.'],
         'checks': ['assert app.parse_count("bad")==0\nassert app.parse_count("19")==19\n',
                    'assert app.parse_count("bad")==-1\nassert app.parse_count("19")==19\n']},
        {'name': 'multiple_edits', 'source': CLI,
         'tasks': ['Change --workers default to 7 and --timeout default to 2.75.',
                   'Change --workers default to 11 and --timeout default to 3.125.'],
         'checks': [cli_check('--workers', 'default', 7) + cli_check('--timeout', 'default', 2.75),
                    cli_check('--workers', 'default', 11) + cli_check('--timeout', 'default', 3.125)]},
    ])
    return cases


def phases(case):
    source, tasks, checks = case['source'], case['tasks'], case['checks']
    steps = [('cold', source, tasks[0], checks[0]), ('repeat', source, tasks[0], checks[0]),
             ('variant', None if case.get('variant_continues') else source, tasks[1], checks[1])]
    if len(tasks) > 2:
        steps.append(('continuous', None, tasks[2], checks[2]))
    steps.extend([('comment_change', source + '# deployment note\n', tasks[1], checks[1]),
                  ('code_change', source + 'SOURCE_VERSION = 2\n', tasks[1], checks[1])])
    return steps


def worker(root):
    payload = json.load(sys.stdin)
    b = bridge(root, 'worker_bridge')
    b.STATE = Path(payload['state'])
    os.environ['PIJIT_URL'] = payload['url']
    os.environ['PIJIT_DISABLE_CODEBOOK'] = '1' if payload['arm'] == 'native' else '0'
    os.environ['PIJIT_VERIFY_CMD'] = payload['verify']
    for key in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_TOKENIZER_REVISION'):
        os.environ.pop(key, None)
    project = Path(payload['cwd'])
    result = native(b, project, payload['task']) if payload['arm'] == 'native' else b.run({
        'action': 'edit', 'cwd': str(project), 'path': 'app.py', 'task': payload['task']})
    print(json.dumps(result))


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cases = workloads()
    (out / 'manifest.json').write_text(json.dumps({'workloads': cases, 'repeats': args.repeats, 'seed': 920,
        'arms': ['native', 'previous', 'expanded'], 'legacy_root': str(args.legacy_root),
        'method': 'one fresh Python worker per edit; independent codebook per family/repeat/arm persisted across phases; random arm order; continuous phases use each arm actual prior source; no retries; same behavior oracle; wall excludes worker startup, process_wall reports it separately'}, ensure_ascii=False, indent=2))
    shutil.copyfile(__file__, out / Path(__file__).name)
    rng = random.Random(920)
    with (out / 'rows.jsonl').open('x') as stream:
        for repeat in range(args.repeats):
            for case in cases:
                for phase, source, task, check in phases(case):
                    arms = ['native', 'previous', 'expanded']
                    rng.shuffle(arms)
                    for arm in arms:
                        root = out / f'{repeat}-{case["name"]}-{arm}'
                        project = root / 'project'
                        project.mkdir(parents=True, exist_ok=True)
                        app = project / 'app.py'
                        if source is not None:
                            app.write_text(source)
                        before = app.read_text()
                        oracle = root / 'oracle.py'
                        oracle.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()))\nimport app\n' + check)
                        payload = {'url': args.url, 'arm': arm, 'state': str(root / 'state'),
                                   'cwd': str(project), 'task': task,
                                   'verify': shlex.join([sys.executable, '-B', str(oracle)])}
                        implementation = args.legacy_root.resolve() if arm == 'previous' else ROOT
                        started = time.perf_counter()
                        child = subprocess.run([sys.executable, __file__, '--worker', str(implementation)],
                                               input=json.dumps(payload), text=True, capture_output=True, timeout=600)
                        if child.returncode:
                            result = {'status': 'worker_error', 'error': child.stderr, 'wall_seconds': time.perf_counter()-started}
                        else:
                            result = json.loads(child.stdout)
                        row = {'repeat': repeat, 'family': case['name'], 'phase': phase, 'arm': arm,
                               'source': before, 'task': task, 'correct': result['status']=='ok', 'result': result,
                               'process_wall_seconds': time.perf_counter()-started, 'after': app.read_text()}
                        stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                        stream.flush()
                        state = root / 'state' / 'workspaces'
                        for book in state.glob('*/codebook.json'):
                            shutil.copyfile(book, out / f'{repeat}-{case["name"]}-{phase}-{arm}-book.json')
                        print(repeat, case['name'], phase, arm, row['correct'], round(result['wall_seconds'], 3),
                              result.get('cache_hit'), result.get('error'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--legacy-root', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
    elif args.out is None or args.legacy_root is None:
        parser.error('--out and --legacy-root are required')
    else:
        main(args)
