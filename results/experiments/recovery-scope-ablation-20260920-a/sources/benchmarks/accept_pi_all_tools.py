"""Independent coverage, framing and behavior acceptance for the Pi tool bridge."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('protocol', ROOT / 'deploy/pi_engine_protocol.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
CHECK = '''import json, subprocess, sys
sys.path.insert(0, '/work')
from catalog import clean_names
cases = [([], []), ([' ', '\\t'], []), ([' Ada ', 'Ada', '', ' Bob', 'Ada'], ['Ada', 'Bob']),
         (['乙', ' 甲 ', '乙', '甲'], ['乙', '甲']), (['B', 'A', 'B'], ['B', 'A'])]
for source, expected in cases:
    assert clean_names(source) == expected, (source, expected)
cli = subprocess.run([sys.executable, 'catalog.py'], capture_output=True, text=True, timeout=10)
assert cli.returncode == 0 and json.loads(cli.stdout) == ['Ada', 'Bob'], cli
tests = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_catalog'], capture_output=True, text=True, timeout=20)
assert tests.returncode == 0, tests.stdout + tests.stderr
print(json.dumps({'behavior_cases': len(cases) + 1, 'model_tests': tests.stderr}))
'''


def accept(root):
    summary = json.loads((root / 'summary.json').read_text())
    schemas = json.loads((root / 'tools.json').read_text())
    frames = [json.loads(line) for line in (root / 'inference.jsonl').read_text().splitlines()]
    messages = json.loads((root / 'messages.json').read_text())
    results = [m for m in messages if m['role'] == 'toolResult']
    expected = {'read', 'bash', 'edit', 'write', 'grep', 'find', 'ls', 'powershell', 'reply_user'}
    assert set(summary['registered_tools']) == expected
    assert set(summary['executed_tools']) == expected, 'Some tools were never exercised'
    assert summary['reply'], 'Missing reply_user'
    assert all(f.get('call') for f in frames), 'Rejected or missing call'
    assert all(f['trace'].get('usage') for f in frames), 'Missing token accounting'
    errors = [r for r in results if r.get('isError')]
    assert any(r['toolName'] == 'powershell' and 'pwsh' in json.dumps(r) for r in errors), 'Expected unavailable PowerShell error'
    for name in expected - {'powershell'}:
        assert any(r['toolName'] == name and not r.get('isError') for r in results), name
    compiled = protocol.Protocol(schemas, raw_required_tail=summary['protocol_mode'] == 'engine_raw')
    if summary['protocol_mode'] != 'native':
        assert summary['all_assistant_output_is_toolcall']
        for frame in frames:
            assert compiled.decode(frame['trace']['raw'], frame['trace']['finish_reason']) == frame['call']
    check = root / ('independent_check-' + hashlib.sha256(CHECK.encode()).hexdigest()[:12] + '.py')
    if not check.exists():
        with check.open('x') as output:
            output.write(CHECK)
    assert check.read_text() == CHECK
    command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
               '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
               '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
               '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
               '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
               '--ro-bind', str(root / 'workspace'), '/work',
               '--ro-bind', str(check), '/check.py', '--chdir', '/work', 'python3', '/check.py']
    execution = subprocess.run(command, capture_output=True, text=True, timeout=40)
    assert execution.returncode == 0, execution.stdout + execution.stderr
    result = {'status': 'passed', 'tools_registered_and_exercised': sorted(expected),
              'successful_tools': sorted(expected - {'powershell'}),
              'expected_unavailable_tool': 'powershell', 'requests': len(frames),
              'tool_error_counts': {name: sum(r['toolName'] == name for r in errors)
                                    for name in sorted({r['toolName'] for r in errors})},
              'behavior': json.loads(execution.stdout),
              'usage': {k: sum(f['trace']['usage'][k] for f in frames)
                        for k in ['prompt_tokens', 'completion_tokens', 'total_tokens']}}
    for metric in ['generation_time_ms', 'queue_time_ms']:
        values = [f['trace'].get('metrics', {}).get(metric) for f in frames]
        result[metric] = sum(values) if all(v is not None for v in values) else None
    with (root / 'acceptance.json').open('x') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=lambda p: Path(p).resolve())
    accept(parser.parse_args().root)
