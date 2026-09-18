"""Paired real Pi loops: compact generation, dynamic C4, and opt-in preset edits."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ('import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n'
          '    p.add_argument("--workers", type=int, default=4)\n    return p\n')
ARMS = {'generation': 'gen', 'c4': 'jit', 'preset': 'pre'}


def metrics(state):
    return [json.loads(line) for path in sorted(state.glob('workspaces/*/metrics.jsonl'))
            for line in path.read_text().splitlines()]


def summarize(rows):
    result = {}
    for arm in ARMS:
        items = [row for row in rows if row['arm'] == arm]
        records = [r for row in items for r in row['metrics']]
        accounting = [r['accounting'] for r in records]
        result[arm] = {
            'tasks': len(items), 'passed': sum(r['passed'] for r in items),
            'wall_seconds': sum(r['seconds'] for r in items),
            'median_seconds': statistics.median(r['seconds'] for r in items) if items else None,
            'outer_calls': sum(r['action'] == 'chat' for r in records),
            'nested_inference_requests': sum(r['accounting']['inference_requests'] for r in records
                                             if r['action'] != 'chat'),
            'preset_applied': sum(r['action'] == 'preset' and r['status'] == 'ok' for r in records),
            'cache_hits': sum(r.get('cache_hit', False) for r in records),
            'error_records': sum(r['status'] != 'ok' for r in records),
            'usage_complete': bool(items) and all(r['usage_complete'] for r in items),
            **{key: sum(a[key] for a in accounting) for key in (
                'inference_requests', 'known_input_tokens', 'known_generated_argument_tokens',
                'known_classification_control_records', 'unknown_usage_requests')},
        }
    return {'arms': result,
            'limitations': 'Small integer-default fixture with a hand-written AST/behavior oracle. '
                           'Real Pi loops including read, outer selection, parameters, local tools and reply; '
                           'shared backend; no stable speed claim. Tool catalogs/prompts differ between arms. '
                           'No automatic benchmark retries; agent recovery attempts remain in totals. '
                           'Known usage is a lower bound when a task is interrupted or records are missing.'}


def attempt(project, state, folder, arm, value, timeout):
    expected = SOURCE.replace('default=4', f'default={value}')
    expected_ast = ast.dump(ast.parse(expected))
    check = ('import ast\nfrom pathlib import Path\n'
             f'assert ast.dump(ast.parse(Path("app.py").read_text())) == {expected_ast!r}\n'
             'import app\np=app.build_parser()\n'
             f'assert p.parse_args([]).workers == {value}\n'
             'assert p.parse_args(["--workers", "23"]).workers == 23\n')
    (project / 'verify.py').write_text(check)
    (folder / 'before.py').write_bytes((project / 'app.py').read_bytes())
    before = len(metrics(state))
    env = dict(os.environ, PIJIT_STATE_DIR=str(state), PIJIT_PRESET_EDITS='1' if arm == 'preset' else '0',
               PIJIT_DISABLE_CODEBOOK='1' if arm == 'generation' else '0',
               PIJIT_VERIFY_CMD=shlex.join([sys.executable, '-B', 'verify.py']), PYTHONDONTWRITEBYTECODE='1')
    tools = 'read,compact_edit' + (',set_cli_default' if arm == 'preset' else '')
    prompt = (f'Read app.py, then change the --workers default to {value}. Preserve explicit overrides and '
              'all unrelated code. Use the available editing tools. After a successful edit, reply DONE. '
              'A configured project check runs automatically after each edit.')
    command = ['node', str(ROOT / 'integrations/pijit/launch.mjs'), '--no-session', '--mode', 'json',
               '--tools', tools, '-p', prompt]
    (folder / 'prompt.txt').write_text(prompt)
    started = time.perf_counter()
    timed_out = False
    with (folder / 'events.jsonl').open('w') as stdout, (folder / 'stderr.txt').open('w') as stderr:
        child = subprocess.Popen(command, cwd=project, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    seconds = time.perf_counter() - started
    records = metrics(state)[before:]
    events = []
    malformed = 0
    for line in (folder / 'events.jsonl').read_text().splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            malformed += 1
    assistants = [e['message'] for e in events if e.get('type') == 'message_end'
                  and e.get('message', {}).get('role') == 'assistant']
    finished = bool(assistants) and assistants[-1].get('stopReason') == 'stop'
    # Independently repeat the guarded task oracle; track this outside task wall time.
    checked_at = time.perf_counter()
    checked = subprocess.run([sys.executable, '-B', 'verify.py'], cwd=project, capture_output=True, text=True, timeout=15)
    validation = {'passed': checked.returncode == 0, 'seconds': time.perf_counter() - checked_at,
                  'stderr': checked.stderr}
    (folder / 'after.py').write_bytes((project / 'app.py').read_bytes())
    row = {'arm': arm, 'value': value, 'seconds': seconds, 'timed_out': timed_out,
           'exit_code': child.returncode, 'finished': finished, 'validation': validation,
           'passed': child.returncode == 0 and finished and validation['passed'] and not timed_out,
           'metrics': records, 'malformed_event_lines': malformed,
           'usage_complete': child.returncode == 0 and finished and not timed_out and not malformed
                             and bool(records) and all(r['accounting']['usage_complete'] for r in records)
                             and len(assistants) == sum(r['action'] == 'chat' for r in records)}
    (folder / 'result.json').write_text(json.dumps(row, indent=2))
    return row


def run(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = out / 'sources'
    sources.mkdir()
    hashes = {}
    for relative in ['benchmarks/compare_pijit_presets.py', 'integrations/pijit/bridge.py',
                     'integrations/pijit/extension.ts', 'integrations/pijit/launch.mjs',
                     'deploy/preset_edits.py', 'deploy/jit_codebook.py', 'deploy/direct_structural_protocol.py',
                     'deploy/compact_structural_protocol.py', 'deploy/structural_edit_protocol.py']:
        path = ROOT / relative
        shutil.copyfile(path, sources / path.name)
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps({
        'seed': args.seed, 'repeats': args.repeats, 'values': args.values, 'sources': hashes,
        'arms': ARMS, 'task_timeout': args.timeout,
        'timing': 'Pi process start through exit, including outer and inner inference, verification, '
                  'read/edit tools and final reply. Fixtures/tunnel/setup and independent post-check excluded.',
        'pairing': 'Same source per paired task; separate projects and codebooks. Reset intended source '
                   'between tasks so a failed arm cannot contaminate later input. Cold codebooks per repeat.',
    }, indent=2))
    rng = random.Random(args.seed)
    rows = []
    for repeat in range(args.repeats):
        projects = {arm: out / f'repeat-{repeat}' / short for arm, short in ARMS.items()}
        for project in projects.values():
            project.mkdir(parents=True)
        previous = 4
        for index, value in enumerate(args.values):
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                project = projects[arm]
                (project / 'app.py').write_text(SOURCE.replace('default=4', f'default={previous}'))
                folder = out / f'{repeat}-{index}-{arm}'
                folder.mkdir()
                row = attempt(project, out / f'state-{repeat}-{ARMS[arm]}', folder, arm, value, args.timeout)
                row.update(repeat=repeat, index=index, order=arms)
                rows.append(row)
                with (out / 'rows.jsonl').open('a') as stream:
                    stream.write(json.dumps(row) + '\n')
                print(json.dumps({k: row[k] for k in ('repeat', 'value', 'arm', 'passed', 'seconds', 'usage_complete')}), flush=True)
            previous = value
    result = summarize(rows)
    (out / 'summary.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--url', default=os.environ.get('PIJIT_URL'))
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--values', type=int, nargs='+', default=[6, 8])
    parser.add_argument('--seed', type=int, default=20260919)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    if not args.url or args.repeats < 1 or args.timeout <= 0:
        parser.error('Provide a URL, positive repeats and timeout')
    os.environ['PIJIT_URL'] = args.url
    result = run(args)
    print(json.dumps(result, indent=2))
    sys.exit(0 if all(a['passed'] == a['tasks'] and a['usage_complete'] for a in result['arms'].values()) else 1)
