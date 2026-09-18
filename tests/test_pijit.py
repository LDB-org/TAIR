import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('pijit_bridge', Path(__file__).parents[1] / 'integrations/pijit/bridge.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
SOURCE = 'import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n    p.add_argument("--workers", type=int, default=4)\n    return p\n'


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(b, 'STATE', tmp_path / 'state')
    monkeypatch.delenv('PIJIT_VERIFY_CMD', raising=False)
    monkeypatch.delenv('PIJIT_DISABLE_CODEBOOK', raising=False)
    cwd = tmp_path / 'project'
    cwd.mkdir()
    (cwd / 'app.py').write_text(SOURCE)
    return cwd


def generated(number):
    return {'call': {'name': 'kw', 'arguments': [['--workers', 'default', number]]},
            'input_tokens': 100, 'generated_argument_tokens': 12,
            'classification_control_records': 1, 'request_id': 'test'}


def task(project, number=6):
    return {'cwd': str(project), 'path': 'app.py', 'task': f'Change --workers default to {number}.'}


def test_cold_generation_then_classified_reuse_on_updated_snapshot(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    first = b.edit(task(project))
    assert first['applied'] and not first['cache_hit'] and first['admitted'] == 2
    assert 'semantic correctness unverified' in first['validation']
    def pick(source, instruction, options):
        assert options[0]['edits'] == [['kw', '--workers', 'default', 8]]
        return options[0], {'input_tokens': 60, 'generated_argument_tokens': 0, 'classification_control_records': 1}
    monkeypatch.setattr(b, 'pick_cached', pick)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('A hit must not generate arguments'))
    second = b.edit(task(project, 8))
    assert second['cache_hit'] and second['generated_argument_tokens'] == 0
    assert 'default=8' in (project / 'app.py').read_text()
    assert Path(second['backup']).read_text() != (project / 'app.py').read_text()


def test_changed_source_cannot_hit_old_entry(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    with (project / 'app.py').open('a') as f:
        f.write('# unrelated source change\n')
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('Stale source must miss'))
    monkeypatch.setattr(b, 'infer', lambda *args: generated(8))
    assert not b.edit(task(project, 8))['cache_hit']


def test_different_task_does_not_use_candidate_even_at_same_source(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('Different wording must not reuse'))
    payload = task(project)
    payload['task'] = 'Make --workers default 6.'
    assert not b.edit(payload)['cache_hit']


def test_failed_project_check_rolls_back_and_does_not_admit(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'exit 1')
    with pytest.raises(ValueError, match='verification failed'):
        b.edit(task(project))
    assert (project / 'app.py').read_text() == SOURCE
    assert not (b.paths(project) / 'codebook.json').exists()


def test_concurrent_modification_is_not_overwritten(project, monkeypatch):
    def infer(*args):
        (project / 'app.py').write_text(SOURCE + '# edited externally\n')
        return generated(6)
    monkeypatch.setattr(b, 'infer', infer)
    with pytest.raises(ValueError, match='Source changed'):
        b.edit(task(project))
    assert (project / 'app.py').read_text().endswith('# edited externally\n')


def test_path_escape_and_non_python_rejected(project):
    for name in ('../outside.py', 'app.ts'):
        payload = task(project)
        payload['path'] = name
        with pytest.raises(ValueError, match='Python file within'):
            b.edit(payload)


def test_incomplete_prefix_rejected(monkeypatch):
    monkeypatch.setattr(b, 'tokenize_label', lambda _: [10])
    monkeypatch.setattr(b, 'tokenize', lambda messages: [1, 2] if len(messages) == 2 else [8, 9])
    with pytest.raises(ValueError, match='prefix'):
        b.infer([{'role': 'user', 'content': 'test'}], [{'name': 'tool', 'parameters': {'type': 'object'}}])


def test_preparation_overlaps_labels_and_messages_without_changing_request(monkeypatch):
    from threading import Event
    label_started, message_started = Event(), Event()
    def label(_):
        label_started.set()
        assert message_started.wait(2), 'Message tokenization must overlap label tokenization'
        return [10]
    def tokenize(messages):
        message_started.set()
        assert label_started.wait(2), 'Label tokenization must overlap message tokenization'
        return [1, 2] if len(messages) == 2 else [1, 2, 10, 3]
    tools = [{'name': 'tool', 'parameters': {'type': 'object'}}]
    def post(route, payload):
        assert route == '/v1/openjev/toolcall'
        assert payload == {'prompt_ids': [1, 2], 'candidate_ids': [10],
                           'continuations': [[10, 3]], 'tools': tools, 'max_tokens': 2048}
        return {'decision': {'index': 0}}
    monkeypatch.setattr(b, 'tokenize_label', label)
    monkeypatch.setattr(b, 'tokenize', tokenize)
    monkeypatch.setattr(b, 'post', post)
    assert b.infer([{'role': 'user', 'content': 'test'}], tools)['input_tokens'] == 4


@pytest.mark.parametrize('ids', [[[10], [10]], [[10, 11]], [[]]])
def test_invalid_labels_rejected(ids):
    with pytest.raises(ValueError, match='distinct single tokens'):
        b.validate_labels(ids)


def test_label_cache_is_revision_bound_and_shared_by_bridge_instances(project, monkeypatch):
    monkeypatch.setenv('PIJIT_URL', 'http://localhost:8000')
    monkeypatch.setenv('PIJIT_TOKENIZER_REVISION', 'tokenizer-sha-a')
    monkeypatch.delenv('PIJIT_SERIAL_PREPARATION', raising=False)
    monkeypatch.setattr(b, 'tokenize_label', lambda label: [ord(label)])
    assert b.labels(2) == [65, 66]
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    monkeypatch.setattr(fresh, 'STATE', b.STATE)
    monkeypatch.setattr(fresh, 'tokenize_label', lambda _: pytest.fail('Cached labels must avoid HTTP'))
    assert fresh.labels(2) == [65, 66]
    monkeypatch.setenv('PIJIT_TOKENIZER_REVISION', 'tokenizer-sha-b')
    monkeypatch.setattr(fresh, 'tokenize_label', lambda label: [ord(label) + 100])
    assert fresh.labels(2) == [165, 166]
    monkeypatch.setenv('PIJIT_SERIAL_PREPARATION', '1')
    monkeypatch.setattr(fresh, 'tokenize_label', lambda label: [ord(label) + 200])
    assert fresh.labels(2) == [265, 266]


def test_corrupt_label_cache_is_refetched_and_no_revision_disables_cache(project, monkeypatch):
    monkeypatch.setenv('PIJIT_URL', 'http://localhost:8000')
    monkeypatch.setenv('PIJIT_TOKENIZER_REVISION', 'tokenizer-sha')
    monkeypatch.delenv('PIJIT_SERIAL_PREPARATION', raising=False)
    monkeypatch.setattr(b, 'tokenize_label', lambda label: [ord(label)])
    assert b.labels(2) == [65, 66]
    cached, = (b.STATE / 'tokenizer-labels').glob('*.json')
    cached.write_text('[[65], [65]]')
    assert b.labels(2) == [65, 66]
    assert json.loads(cached.read_text()) == [[65], [66]]
    monkeypatch.delenv('PIJIT_TOKENIZER_REVISION')
    monkeypatch.setattr(b, 'tokenize_label', lambda label: [ord(label) + 100])
    assert b.labels(2) == [165, 166]


def test_image_is_not_silently_dropped():
    with pytest.raises(ValueError, match='image transport'):
        b.text_content([{'type': 'image', 'data': 'abc'}])


def test_low_confidence_falls_back_to_generation(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    monkeypatch.setattr(b, 'pick_cached', lambda *args: (None, {
        'input_tokens': 30, 'generated_argument_tokens': 0, 'classification_control_records': 1}))
    monkeypatch.setattr(b, 'infer', lambda *args: generated(8))
    result = b.edit(task(project, 8))
    assert not result['cache_hit']
    assert result['fallback_reason'] == 'none_or_low_confidence'
    assert result['classification_control_records'] == 2
    assert result['generated_argument_tokens'] == 12


def test_verifier_mutation_not_admitted(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    monkeypatch.setenv('PIJIT_VERIFY_CMD', "printf '# changed by verifier\\n' >> app.py")
    with pytest.raises(ValueError, match='admission skipped'):
        b.edit(task(project))
    assert not (b.paths(project) / 'codebook.json').exists()
    assert '# changed by verifier' in (project / 'app.py').read_text()


@pytest.mark.parametrize('scores,selected,reasons', [
    ([-0.25, -1.5], 0, ['low_conditional_probability', 'low_margin']),
    ([-8, -0.01], 1, ['selected_none']),
    ([-0.01, -8], 0, []),
])
def test_candidate_decision_explains_none_and_gate_rejection(monkeypatch, scores, selected, reasons):
    monkeypatch.setattr(b, 'tokenize', lambda _: [1, 2])
    monkeypatch.setattr(b, 'labels', lambda _: [10, 11])
    monkeypatch.setattr(b, 'post', lambda *args: {'id': 'classification', 'choices': [{
        'token_ids': [[10, 11][selected]],
        'logprobs': {'top_logprobs': [{f'token_id:{i}': score for i, score in zip([10, 11], scores)}]}}]})
    candidate = {'id': 7, 'edits': [['kw', '--workers', 'default', 8]]}
    accepted, record = b.pick_cached(SOURCE, 'Change default to 8.', [candidate])
    decision = record['decision']
    assert decision['selected_index'] == selected
    assert decision['selected_candidate'] == ([candidate, None][selected])
    assert decision['rejection_reasons'] == reasons
    assert decision['scores'] == scores
    assert decision['candidates'] == [candidate, None]
    assert bool(accepted) == (not reasons)


def test_disabled_codebook_neither_reads_nor_changes_existing_entries(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    book = b.paths(project) / 'codebook.json'
    before = book.read_bytes()
    monkeypatch.setenv('PIJIT_DISABLE_CODEBOOK', '1')
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('Baseline must not classify cache'))
    monkeypatch.setattr(b, 'infer', lambda *args: generated(8))
    result = b.edit(task(project, 8))
    assert result['admitted'] == 0 and not result['cache_hit']
    assert result['fallback_reason'] == 'codebook_disabled'
    assert book.read_bytes() == before


def test_failed_verification_logs_spent_inference_and_rollback(project, monkeypatch):
    def infer(*args):
        b.TRACE.get()['http_requests'].append({
            'route': '/v1/openjev/toolcall', 'status': 'ok', 'usage_complete': True,
            'input_tokens': 100, 'generated_argument_tokens': 12, 'classification_control_records': 1})
        return generated(6)
    monkeypatch.setattr(b, 'infer', infer)
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'exit 1')
    result = b.run(dict(task(project), action='edit', session_id='session', parent_tool_call_id='call'))
    assert result['status'] == 'error' and result['rolled_back'] and not result['applied']
    assert not result['cache_hit']
    assert result['accounting']['known_generated_argument_tokens'] == 12
    assert result['accounting']['usage_complete']
    assert result['stage_seconds']['verification'] > 0
    saved = json.loads((b.paths(project) / 'metrics.jsonl').read_text())
    assert saved['status'] == 'error' and saved['session_id'] == 'session'
    assert saved['parent_tool_call_id'] == 'call'
    assert (project / 'app.py').read_text() == SOURCE
    assert not (b.paths(project) / 'codebook.json').exists()


def test_failed_http_request_has_unknown_usage_and_is_not_lost(project, monkeypatch):
    monkeypatch.setenv('PIJIT_URL', 'http://localhost:1')
    def fail(*args, **kwargs):
        raise TimeoutError('test timeout')
    monkeypatch.setattr(b.urllib.request, 'urlopen', fail)
    monkeypatch.setattr(b, 'chat', lambda _: b.post('/v1/openjev/toolcall', {}))
    result = b.run({'action': 'chat', 'cwd': str(project)})
    assert result['status'] == 'error'
    assert result['accounting']['inference_requests'] == 1
    assert result['accounting']['unknown_usage_requests'] == 1
    assert not result['accounting']['usage_complete']
    assert result['http_requests'][0]['seconds'] > 0
    assert result['http_requests'][0]['error_type'] == 'TimeoutError'


@pytest.mark.parametrize('timing', [None, {'initial_queue_seconds': 4., 'scheduled_to_first_output_seconds': .2}])
def test_engine_classification_timing_is_preserved_when_available(project, monkeypatch, timing):
    monkeypatch.setenv('PIJIT_URL', 'http://localhost:1')
    decision = {'index': 0}
    if timing is not None:
        decision['timing'] = timing
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps({'decision': decision, 'generated_argument_tokens': 2,
                               'classification_control_records': 1}).encode()
    monkeypatch.setattr(b.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    monkeypatch.setattr(b, 'chat', lambda _: b.post('/v1/openjev/toolcall', {
        'prompt_ids': [1, 2], 'continuations': [[3]]}))
    result = b.run({'action': 'chat', 'cwd': str(project)})
    assert result['http_requests'][0]['classification_timing'] == timing
    assert result['accounting']['usage_complete']


def test_parallel_tokenization_is_in_same_trace(project, monkeypatch):
    monkeypatch.setenv('PIJIT_URL', 'http://localhost:1')
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"tokens": [1]}'
    monkeypatch.setattr(b.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    monkeypatch.setattr(b, 'chat', lambda _: {'tokens': b.parallel(b.tokenize, [[], [], []])})
    result = b.run({'action': 'chat', 'cwd': str(project)})
    assert len(result['http_requests']) == 3
    assert result['accounting']['inference_requests'] == 0
    assert b.TRACE.get() is None


def preset(project, **overrides):
    return dict({'action': 'preset', 'cwd': str(project), 'path': 'app.py',
                 'option': '--workers', 'expected_default': 4, 'value': 8}, **overrides)


def test_preset_uses_no_model_and_does_not_admit_cache(project, monkeypatch):
    monkeypatch.setattr(b, 'post', lambda *args: pytest.fail('Preset must not request inference'))
    result = b.run(preset(project))
    assert result['status'] == 'ok' and result['applied'] and not result['cache_hit']
    assert result['accounting']['inference_requests'] == 0
    assert result['stage_seconds']['preset_binding'] > 0
    assert (project / 'app.py').read_text() == SOURCE.replace('default=4', 'default=8')
    assert Path(result['backup']).read_text() == SOURCE
    assert not (b.paths(project) / 'codebook.json').exists()


@pytest.mark.parametrize('changes', [
    {'expected_default': 5}, {'value': True}, {'value': '8'}, {'option': '--missing'},
])
def test_preset_rejects_stale_wrong_type_or_absent_target_without_write(project, changes):
    result = b.run(preset(project, **changes))
    assert result['status'] == 'error' and not result['applied']
    assert (project / 'app.py').read_text() == SOURCE


@pytest.mark.parametrize('source', [
    SOURCE.replace('    return p', '    p.add_argument("--workers", type=int, default=4)\n    return p'),
    SOURCE.replace('argparse.ArgumentParser()', 'custom_parser()'),
    SOURCE.replace('type=int', 'type=str'),
    SOURCE.replace('default=4', 'default=compute()'),
    SOURCE.replace('default=4', '**options'),
    SOURCE.replace('def build_parser():', 'def build_parser(int):'),
    SOURCE.replace('    return p', '    return p') + '\nint = str\n',
])
def test_preset_rejects_ambiguous_and_unsupported_source(project, source):
    (project / 'app.py').write_text(source)
    assert b.run(preset(project))['status'] == 'error'
    assert (project / 'app.py').read_text() == source


def test_preset_preserves_unicode_crlf_comments_and_accepts_alias(project):
    source = SOURCE.replace('"--workers",', '"-w", "--workers", help="并发数",').replace(
        'default=4)', 'default=-4)  # keep me').replace('\n', '\r\n')
    (project / 'app.py').write_bytes(source.encode())
    result = b.run(preset(project, expected_default=-4))
    assert result['status'] == 'ok'
    assert (project / 'app.py').read_bytes() == source.replace('default=-4', 'default=8').encode()


def test_preset_project_failure_rolls_back(project, monkeypatch):
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'exit 1')
    result = b.run(preset(project))
    assert result['status'] == 'error' and result['rolled_back'] and not result['applied']
    assert (project / 'app.py').read_text() == SOURCE


def test_preset_concurrent_change_is_not_overwritten(project, monkeypatch):
    original = b.presets.set_cli_default
    def external_change(*args):
        result = original(*args)
        (project / 'app.py').write_text(SOURCE + '# external\n')
        return result
    monkeypatch.setattr(b.presets, 'set_cli_default', external_change)
    result = b.run(preset(project))
    assert result['status'] == 'error'
    assert (project / 'app.py').read_text().endswith('# external\n')
