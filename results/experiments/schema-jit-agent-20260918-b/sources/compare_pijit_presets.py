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
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ('import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n'
          '    p.add_argument("--workers", type=int, default=4)\n    return p\n')
ARMS = {'generation': 'gen', 'c4': 'jit', 'preset': 'pre', 'preset_before': 'old', 'native': 'nat'}


def native_metrics(path):
    events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    responses = {e['id']: e for e in events if e['event'] == 'response'}
    records = []
    for event in events:
        if event['event'] != 'request':
            continue
        response = responses.get(event['id'], {})
        usage = response.get('usage') or {}
        prompt = sum(usage.get(k, 0) for k in ('input', 'cacheRead', 'cacheWrite'))
        complete = prompt > 0 and 'output' in usage and response.get('stop_reason') in ('stop', 'toolUse')
        records.append({'action': 'chat', 'status': 'ok' if complete else 'error',
                        'native_request_id': event['id'], 'seconds': response.get('seconds'),
                        'accounting': {'usage_complete': complete, 'inference_requests': 1,
                                       'unknown_usage_requests': int(not complete),
                                       'known_input_tokens': prompt,
                                       'known_generated_argument_tokens': usage.get('output', 0),
                                       'known_classification_control_records': 0}})
    return records


def metrics(state):
    return [json.loads(line) for path in sorted(state.glob('workspaces/*/metrics.jsonl'))
            for line in path.read_text().splitlines()]


def summarize(rows):
    result = {}
    for arm in ARMS:
        items = [row for row in rows if row['arm'] == arm]
        if not items:
            continue
        records = [r for row in items for r in row['metrics']]
        accounting = [r['accounting'] for r in records]
        result[arm] = {
            'tasks': len(items), 'passed': sum(r['passed'] for r in items),
            'wall_seconds': sum(r.get('validated_seconds', r['seconds']) for r in items),
            'median_seconds': statistics.median(r.get('validated_seconds', r['seconds']) for r in items),
            'pi_loop_seconds': sum(r['seconds'] for r in items),
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


def attempt(project, state, folder, arm, value, timeout, scenario=None):
    expected = SOURCE.replace('default=4', f'default={value}')
    expected_ast = ast.dump(ast.parse(expected))
    check = ('import ast\nfrom pathlib import Path\n'
             f'assert ast.dump(ast.parse(Path("app.py").read_text())) == {expected_ast!r}\n'
             'import app\np=app.build_parser()\n'
             f'assert p.parse_args([]).workers == {value}\n'
             'assert p.parse_args(["--workers", "23"]).workers == 23\n')
    if scenario is not None:
        check = 'import os, sys\nsys.path.insert(0, os.getcwd())\n' + scenario['check']
    check_path = folder / 'oracle.py' if scenario is not None else project / 'verify.py'
    check_path.write_text(check)
    (folder / 'before.py').write_bytes((project / 'app.py').read_bytes())
    before = len(metrics(state))
    is_preset = arm in ('preset', 'preset_before')
    env = dict(os.environ, PIJIT_STATE_DIR=str(state), PIJIT_PRESET_EDITS='1' if is_preset else '0',
               PIJIT_SERIAL_PREPARATION='1' if arm == 'preset_before' else '0',
               PIJIT_DISABLE_CODEBOOK='1' if arm == 'generation' else '0',
               PIJIT_VERIFY_CMD=shlex.join([sys.executable, '-B', str(check_path)]), PYTHONDONTWRITEBYTECODE='1')
    if scenario is not None:
        env.pop('PIJIT_VERIFY_CMD', None)
    tools = 'read,compact_edit' + (',set_cli_default' if is_preset else '')
    prompt = (f'Read app.py, then change the --workers default to {value}. Preserve explicit overrides and '
              'all unrelated code. Use the available editing tools. After a successful edit, reply DONE.')
    if scenario is not None:
        prompt = scenario['prompt']
        tools = 'read,edit,write,bash,compact_edit' + (',set_cli_default' if is_preset else '')
    command = ['node', str(ROOT / 'integrations/pijit/launch.mjs'), '--no-session', '--mode', 'json',
               '--tools', tools, '-p', prompt]
    (folder / 'prompt.txt').write_text(prompt)
    started = time.perf_counter()
    timed_out = False
    # Keep Pi's auth/model profile outside archived evidence; retain only project metrics/codebooks.
    state.mkdir(parents=True, exist_ok=True)
    profile_link = state / 'agent'
    with tempfile.TemporaryDirectory(prefix='pijit-benchmark-profile-') as profile, \
            (folder / 'events.jsonl').open('w') as stdout, (folder / 'stderr.txt').open('w') as stderr:
        profile_link.symlink_to(profile, target_is_directory=True)
        try:
            if arm == 'native':
                config = {'providers': {'native-vllm': {
                    'baseUrl': os.environ['PIJIT_URL'].rstrip('/') + '/v1',
                    'api': 'openai-completions', 'apiKey': os.environ.get('PIJIT_API_KEY', 'local-placeholder'),
                    'compat': {'supportsStore': False, 'supportsDeveloperRole': False,
                               'supportsReasoningEffort': False, 'maxTokensField': 'max_tokens'},
                    'models': [{'id': '/model', 'name': 'Native vLLM', 'reasoning': False,
                                'input': ['text'], 'contextWindow': 240000, 'maxTokens': 2048}]}}}
                (Path(profile) / 'models.json').write_text(json.dumps(config))
                env.update(PI_CODING_AGENT_DIR=profile, PI_OFFLINE='1',
                           TAIR_NATIVE_TRACE=str(folder / 'native-inference.jsonl'))
                cli = str(Path(shutil.which('pi')).resolve())
                command = ['node', cli, '--no-extensions', '-e', str(ROOT / 'benchmarks/native_pi_trace.ts'),
                           '--provider', 'native-vllm', '--model', '/model', '--thinking', 'off',
                           '--no-session', '--mode', 'json', '--tools',
                           'read,edit,write,bash' if scenario is not None else 'read,edit', '-p', prompt]
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
        finally:
            profile_link.unlink()
    seconds = time.perf_counter() - started
    records = native_metrics(folder / 'native-inference.jsonl') if arm == 'native' else metrics(state)[before:]
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
    checked = subprocess.run([sys.executable, '-B', str(check_path)], cwd=project, capture_output=True, text=True, timeout=15)
    validation = {'passed': checked.returncode == 0, 'seconds': time.perf_counter() - checked_at,
                  'stderr': checked.stderr}
    (folder / 'after.py').write_bytes((project / 'app.py').read_bytes())
    row = {'arm': arm, 'value': value, 'seconds': seconds, 'timed_out': timed_out,
           'validated_seconds': seconds + validation['seconds'],
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
    for relative in ['benchmarks/compare_pijit_presets.py', 'benchmarks/native_pi_trace.ts', 'integrations/pijit/bridge.py',
                     'integrations/pijit/extension.ts', 'integrations/pijit/launch.mjs',
                     'deploy/preset_edits.py', 'deploy/jit_codebook.py', 'deploy/direct_structural_protocol.py',
                     'deploy/compact_structural_protocol.py', 'deploy/structural_edit_protocol.py']:
        path = ROOT / relative
        shutil.copyfile(path, sources / path.name)
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps({
        'seed': args.seed, 'repeats': args.repeats, 'values': args.values, 'sources': hashes,
        'arms': args.arms, 'task_timeout': args.timeout,
        'tokenizer_revision': os.environ.get('PIJIT_TOKENIZER_REVISION'),
        'preset_before': 'Same preset tools/prompts/verification; original serial preparation and no label cache. '
                         'Preset uses overlapping preparation and revision-bound label caching when configured. '
                         'All tasks include startup; each repeat starts with a cold label cache.',
        'timing': 'Reported validated wall = Pi start through exit plus identical independent final AST/behavior '
                  'check. Preset/compact paths additionally keep in-tool verification/rollback; native uses '
                  'unmodified read/edit tools. Fixture/tunnel preparation excluded. Profile startup included.',
        'native': 'Stock Pi openai-completions streaming provider and read/edit tools on the same patched '
                  'vLLM standard tools API. Harness fixes temperature 0, 2048-token budget, thinking off, '
                  'parallel tools off and unique per-request cache salt. Not an unpatched-server A/B.',
        'pairing': 'Same source per paired task; separate projects and codebooks. Reset intended source '
                   'between tasks so a failed arm cannot contaminate later input. Cold codebooks per repeat.',
    }, indent=2))
    rng = random.Random(args.seed)
    rows = []
    for repeat in range(args.repeats):
        projects = {arm: out / f'repeat-{repeat}' / ARMS[arm] for arm in args.arms}
        for project in projects.values():
            project.mkdir(parents=True)
        previous = 4
        for index, value in enumerate(args.values):
            arms = list(args.arms)
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
    parser.add_argument('--arms', nargs='+', choices=list(ARMS), default=['generation', 'c4', 'preset'])
    args = parser.parse_args()
    if not args.url or args.repeats < 1 or args.timeout <= 0 or len(set(args.arms)) != len(args.arms):
        parser.error('Provide a URL, positive repeats and timeout')
    os.environ['PIJIT_URL'] = args.url
    result = run(args)
    print(json.dumps(result, indent=2))
    sys.exit(0 if all(a['passed'] == a['tasks'] and a['usage_complete'] for a in result['arms'].values()) else 1)
