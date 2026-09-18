"""Frozen two-arm, two-session Pi experiment on a new numerical utility."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CHECK = '''import json, sys, subprocess
sys.path.insert(0, '/work')
from statistics_app import summarize_numbers
for values in [[], [0], [-4,-2], [3,3,1], [0.25,-1,2.5], [3,-1,3,0.5]]:
    before = list(values)
    expected = dict(count=len(values), total=sum(values), min=min(values) if values else None, max=max(values) if values else None)
    assert summarize_numbers(values) == expected, (values, summarize_numbers(values))
    assert values == before
result = subprocess.run([sys.executable, 'statistics_app.py'], capture_output=True, text=True, timeout=10)
assert result.returncode == 0 and json.loads(result.stdout) == dict(count=4,total=5.5,min=-1,max=3)
tests = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_statistics_app'], capture_output=True, text=True, timeout=20)
assert tests.returncode == 0, tests.stdout + tests.stderr
print(json.dumps({'behavior_checks': 7, 'model_tests': tests.stderr}))
'''


def validate(root, check):
    command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
               '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
               '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
               '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
               '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
               '--ro-bind', str(root / 'workspace'), '/work', '--ro-bind', str(check), '/check.py',
               '--chdir', '/work', 'python3', '/check.py']
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    return {'passed': result.returncode == 0, 'returncode': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}


def main(args):
    args.out.mkdir(); sources = args.out / 'sources'; sources.mkdir()
    for relative in ['benchmarks/evaluate_pi_named.py', 'deploy/pi_engine_protocol.py', 'integrations/pi/run_scanner.mjs',
                     'benchmarks/data/pi-named-task.txt', 'benchmarks/data/pi-named-fixture/statistics_app.py']:
        shutil.copyfile(ROOT / relative, sources / Path(relative).name)
    check = args.out / 'check.py'; check.write_text(CHECK)
    manifest = {'modes': args.modes, 'repeats': 2, 'concurrency': 2,
                'max_turns': 14, 'policy': 'No native fallback, no prompt tuning after launch, all costs retained',
                'limitations': 'One new task, two runs per mode, shared server; not stable speed or production proof.'}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    def run(mode, index):
        root = args.out / f'{mode}-{index}'
        command = ['node', str(ROOT / 'integrations/pi/run_scanner.mjs'), '--out', str(root),
                   '--pi-root', args.pi_root, '--host', args.host, '--worker', args.worker,
                   '--mode', mode, '--all-tools', 'true', '--max-turns', '14',
                   '--fixture', str(ROOT / 'benchmarks/data/pi-named-fixture'),
                   '--prompt', str(ROOT / 'benchmarks/data/pi-named-task.txt')]
        with (args.out / f'{mode}-{index}.log').open('x') as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=660)
        validation = validate(root, check)
        summary = json.loads((root / 'summary.json').read_text()) if (root / 'summary.json').exists() else {}
        required = {'read','bash','edit','write','grep','find','ls','powershell','reply_user'}
        passed = result.returncode == 0 and validation['passed'] and set(summary.get('executed_tools', [])) == required and summary.get('all_assistant_output_is_toolcall', False)
        row = {'mode': mode, 'repeat': index, 'returncode': result.returncode, 'passed': passed,
               'validation': validation, 'summary': summary}
        (root / 'acceptance.json').write_text(json.dumps(row, ensure_ascii=False, indent=2))
        print(mode, index, 'passed', passed, flush=True)
        return row
    for mode in manifest['modes']:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda index: run(mode, index), [0, 1]))
        with (args.out / 'waves.jsonl').open('a') as output:
            output.write(json.dumps({'mode': mode, 'seconds': time.perf_counter()-start, 'rows': rows}, ensure_ascii=False)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=lambda v: Path(v).resolve())
    p.add_argument('--pi-root', required=True)
    p.add_argument('--host', default='rs-yuesheng-gpu-vps')
    p.add_argument('--worker', required=True)
    p.add_argument('--modes', nargs='+', default=['engine_named', 'engine_raw'], choices=['engine_raw', 'engine_named', 'engine_named_bounded'])
    main(p.parse_args())
