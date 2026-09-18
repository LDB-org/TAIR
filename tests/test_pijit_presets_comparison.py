import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'preset_comparison', Path(__file__).parents[1] / 'benchmarks/compare_pijit_presets.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def test_summary_counts_outer_inner_and_failed_work_separately():
    def record(action, requests, generated, status='ok'):
        return {'action': action, 'status': status, 'accounting': {
            'inference_requests': requests, 'known_input_tokens': requests * 100,
            'known_generated_argument_tokens': generated, 'known_classification_control_records': requests,
            'unknown_usage_requests': int(status == 'error')}}
    rows = [
        {'arm': 'generation', 'passed': True, 'seconds': 3, 'usage_complete': True,
         'metrics': [record('chat', 1, 30), record('edit', 1, 10), record('chat', 1, 8)]},
        {'arm': 'preset', 'passed': True, 'seconds': 2, 'usage_complete': True,
         'metrics': [record('chat', 1, 40), record('preset', 0, 0), record('chat', 1, 8)]},
        {'arm': 'c4', 'passed': False, 'seconds': 5, 'usage_complete': False,
         'metrics': [record('chat', 1, 30), record('edit', 2, 0, 'error')]},
    ]
    result = c.summarize(rows)['arms']
    assert result['generation']['inference_requests'] == 3
    assert result['generation']['known_generated_argument_tokens'] == 48
    assert result['preset']['outer_calls'] == 2
    assert result['preset']['nested_inference_requests'] == 0
    assert result['preset']['preset_applied'] == 1
    assert result['c4']['inference_requests'] == 3
    assert result['c4']['passed'] == 0 and result['c4']['wall_seconds'] == 5
    assert not result['c4']['usage_complete']


@pytest.mark.parametrize('arm', ['preset', 'preset_before'])
def test_runtime_profile_is_not_archived(tmp_path, monkeypatch, arm):
    project, state, folder = (tmp_path / name for name in ('project', 'state', 'case'))
    project.mkdir()
    folder.mkdir()
    (project / 'app.py').write_text(c.SOURCE)
    real_popen = c.subprocess.Popen
    class FakePi:
        returncode = 0
        def __init__(self, command, **kwargs):
            assert kwargs['env']['PIJIT_PRESET_EDITS'] == '1'
            assert kwargs['env']['PIJIT_SERIAL_PREPARATION'] == str(int(arm == 'preset_before'))
            assert command[command.index('--tools') + 1] == 'read,compact_edit,set_cli_default'
            assert (state / 'agent').is_symlink()
            (state / 'agent' / 'auth.json').write_text('private profile fixture')
            (project / 'app.py').write_text(c.SOURCE.replace('default=4', 'default=6'))
            kwargs['stdout'].write(json.dumps({'type': 'message_end', 'message': {
                'role': 'assistant', 'stopReason': 'stop'}}) + '\n')
            records = state / 'workspaces' / 'fixture'
            records.mkdir(parents=True)
            (records / 'metrics.jsonl').write_text(json.dumps({
                'action': 'chat', 'accounting': {'usage_complete': True}}) + '\n')
        def wait(self, **kwargs):
            return 0
    def popen(command, **kwargs):
        return FakePi(command, **kwargs) if command[0] == 'node' else real_popen(command, **kwargs)
    monkeypatch.setattr(c.subprocess, 'Popen', popen)
    row = c.attempt(project, state, folder, arm, 6, 5)
    assert row['passed'] and row['usage_complete']
    assert not (state / 'agent').exists() and not (state / 'agent').is_symlink()
    assert not list(tmp_path.rglob('auth.json'))


def test_native_usage_includes_cached_input_and_preserves_missing_responses(tmp_path):
    trace = tmp_path / 'trace.jsonl'
    events = [{'event': 'request', 'id': 'one'},
              {'event': 'response', 'id': 'one', 'stop_reason': 'toolUse',
               'usage': {'input': 100, 'cacheRead': 50, 'cacheWrite': 0, 'output': 20}},
              {'event': 'request', 'id': 'timeout'}]
    trace.write_text(''.join(json.dumps(e) + '\n' for e in events))
    records = c.native_metrics(trace)
    assert len(records) == 2
    assert records[0]['accounting']['known_input_tokens'] == 150
    assert records[0]['accounting']['known_generated_argument_tokens'] == 20
    assert records[0]['accounting']['known_classification_control_records'] == 0
    assert records[0]['accounting']['usage_complete']
    assert not records[1]['accounting']['usage_complete']
    assert records[1]['accounting']['unknown_usage_requests'] == 1
