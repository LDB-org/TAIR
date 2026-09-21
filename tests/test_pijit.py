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
    monkeypatch.setattr(b, 'server_plan_budget', lambda: True)
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
        f.write('SOURCE_VERSION = 2\n')
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('Stale source must miss'))
    monkeypatch.setattr(b, 'infer', lambda *args: generated(8))
    assert not b.edit(task(project, 8))['cache_hit']


def test_comment_change_reuses_explicit_binding_but_checks_current_snapshot(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    path = project / 'app.py'
    path.write_text(path.read_text() + '# preserved comment\n')
    def pick(source, instruction, options):
        assert options[0]['source_match'] == 'ast_equivalent'
        return options[0], {'input_tokens': 60, 'generated_argument_tokens': 0, 'classification_control_records': 1}
    monkeypatch.setattr(b, 'pick_cached', pick)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Comment-only change can reuse explicit edit'))
    assert b.edit(task(project, 8))['cache_hit']
    assert path.read_text().endswith('# preserved comment\n')
    assert 'default=8' in path.read_text()


@pytest.mark.parametrize('source,first,next_task,next_edit', [
    (SOURCE.replace('type=int, default=4', 'type=float, default=1.5'),
     ('Change --workers default to 2.5.', ['kw', '--workers', 'default', 2.5]),
     'Change --workers default to 3.75.', ['kw', '--workers', 'default', 3.75]),
    (SOURCE.replace('type=int, default=4', 'default="old"'),
     ('Change --workers default to "new".', ['kw', '--workers', 'default', 'new']),
     'Change --workers default to "other".', ['kw', '--workers', 'default', 'other']),
    (SOURCE.replace('type=int, default=4', 'action="store_true", default=False'),
     ('Change --workers default to true.', ['kw', '--workers', 'default', True]),
     'Change --workers default to false.', ['kw', '--workers', 'default', False]),
    (SOURCE, ('Add alias -w to --workers.', ['arg', '--workers', '-w']),
     'Add alias -x to --workers.', ['arg', '--workers', '-x']),
])
def test_learned_typed_binding_reuses_new_values(project, monkeypatch, source, first, next_task, next_edit):
    path = project / 'app.py'
    path.write_text(source)
    instruction, edit = first
    monkeypatch.setattr(b, 'infer', lambda *args: {**generated(6), 'call': {'name': edit[0], 'arguments': [edit[1:]]}})
    assert not b.edit(dict(task(project), task=instruction))['cache_hit']
    path.write_text(source)
    def pick(source, instruction, options):
        assert options[0]['edits'] == [next_edit]
        return options[0], {'input_tokens': 60, 'generated_argument_tokens': 0, 'classification_control_records': 1}
    monkeypatch.setattr(b, 'pick_cached', pick)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Bound template must reuse'))
    assert b.edit(dict(task(project), task=next_task))['cache_hit']


def test_generic_guard_is_learned_for_exact_task_not_modified_result(project, monkeypatch):
    source = 'def divide(a, b):\n    return a / b\n'
    path = project / 'app.py'
    path.write_text(source)
    instruction = 'Return None from divide when b == 0.'
    edit = ['return_if', 'divide', 'b == 0', 'None']
    monkeypatch.setattr(b, 'infer', lambda *args: {**generated(6), 'call': {'name': edit[0], 'arguments': [edit[1:]]}})
    result = b.edit(dict(task(project), task=instruction))
    assert result['admitted'] == 1
    path.write_text(source)
    def pick(source, instruction, options):
        assert options[0]['exact_task'] == instruction
        assert options[0]['source_sha256'] == b.jit.digest(source)
        return options[0], {'input_tokens': 60, 'generated_argument_tokens': 0, 'classification_control_records': 1}
    monkeypatch.setattr(b, 'pick_cached', pick)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Exact learned guard must reuse'))
    assert b.edit(dict(task(project), task=instruction))['cache_hit']


def test_keyword_target_resolves_after_existing_alias():
    source = SOURCE.replace('"--workers"', '"-w", "--workers"')
    assert b.bound_edit(source, 'Change --workers default to 8.') == [['kw', '-w', 'default', 8]]


def test_alias_learning_tracks_target_after_first_alias(project, monkeypatch):
    edit = ['arg', '--workers', '-w']
    monkeypatch.setattr(b, 'infer', lambda *args: {**generated(6), 'call': {'name': edit[0], 'arguments': [edit[1:]]}})
    assert not b.edit(dict(task(project), task='Add alias -w to --workers.'))['cache_hit']
    def pick(source, instruction, options):
        assert options[0]['edits'] == [['arg', '-w', '-x']]
        return options[0], {'input_tokens': 60, 'generated_argument_tokens': 0, 'classification_control_records': 1}
    monkeypatch.setattr(b, 'pick_cached', pick)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Second alias should reuse'))
    assert b.edit(dict(task(project), task='Add alias -x to --workers.'))['cache_hit']
    assert b.bound_edit((project/'app.py').read_text(), 'Add alias -w to --workers.') is None


def test_generated_wrong_explicit_value_is_rejected_before_write(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(99))
    with pytest.raises(ValueError, match='contradicts'):
        b.edit(task(project, 8))
    assert (project/'app.py').read_text() == SOURCE
    assert not (b.paths(project)/'codebook.json').exists()


@pytest.mark.parametrize('task_text,source_hash,accepted', [
    ('Guard divide.', 'correct', True),
    ('A different task.', 'correct', False),
    ('Guard divide.', 'stale', False),
])
def test_exact_learned_gate_checks_task_and_source(monkeypatch, task_text, source_hash, accepted):
    monkeypatch.setattr(b, 'tokenize', lambda _: [1, 2])
    monkeypatch.setattr(b, 'labels', lambda _: [10, 11])
    monkeypatch.setattr(b, 'post', lambda *args: {'id': 'classification', 'choices': [{
        'token_ids': [10], 'logprobs': {'top_logprobs': [{'token_id:10': -0.01, 'token_id:11': -8}]}}]})
    candidate = {'id': 0, 'edits': [['return_if', 'divide', 'b == 0', 'None']],
                 'exact_task': task_text, 'source_sha256': b.jit.digest(SOURCE) if source_hash == 'correct' else 'stale'}
    chosen, record = b.pick_cached(SOURCE, 'Guard divide.', [candidate])
    assert bool(chosen) == accepted
    if not accepted:
        assert 'exact_task_mismatch' in record['decision']['rejection_reasons']


def test_different_task_does_not_use_candidate_even_at_same_source(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('Different wording must not reuse'))
    payload = task(project)
    payload['task'] = 'Increase the worker limit to 6.'
    assert not b.edit(payload)['cache_hit']


def test_bound_paraphrase_reuses_learned_template(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    (project / 'app.py').write_text(SOURCE)
    def pick(source, instruction, options):
        assert len(options) == 1
        assert options[0]['edits'] == [['kw', '--workers', 'default', 10]]
        return options[0], {'input_tokens': 60, 'generated_argument_tokens': 0, 'classification_control_records': 1}
    monkeypatch.setattr(b, 'pick_cached', pick)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Supported paraphrase should reuse'))
    payload = task(project)
    payload['task'] = 'Set the default value for --workers to 10.'
    assert b.edit(payload)['cache_hit']


def test_explicit_binding_filters_wrong_learned_value(project, monkeypatch):
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project))
    (project / 'app.py').write_text(SOURCE)
    bookfile = b.paths(project) / 'codebook.json'
    entries = json.loads(bookfile.read_text())
    for entry in entries:
        entry['template'][3] = 99
    bookfile.write_text(json.dumps(entries))
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('Wrong value must be filtered'))
    monkeypatch.setattr(b, 'infer', lambda *args: generated(8))
    assert not b.edit(task(project, 8))['cache_hit']


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


def test_custom_inference_prompts_skip_discarded_defaults(monkeypatch):
    class Tool(dict):
        def get(self,key,*args):
            if key=='description':pytest.fail('Unused default catalog was constructed')
            return super().get(key,*args)
    tools=[Tool(name='plan',parameters=dict(type='object'))]
    messages=[dict(role='user',content='task')]
    def prepare(actual,tails):
        assert actual==messages+[dict(role='user',content='Pick A')]
        assert tails==[[dict(role='assistant',content='A'),dict(role='user',content='custom schema')]]
        return [1,2],[[3,4]]
    monkeypatch.setattr(b,'prepare_continuations',prepare)
    monkeypatch.setattr(b,'labels',lambda n:[5])
    def post(route,payload):
        assert payload==dict(prompt_ids=[1,2],candidate_ids=[5],continuations=[[3,4]],tools=tools,max_tokens=2048)
        return dict(decision=dict(index=0))
    monkeypatch.setattr(b,'post',post)
    b.infer(messages,tools,classification_prompt='Pick A',
            instruction=lambda _:pytest.fail('Unused default instruction was invoked'),
            branch_instruction=lambda index,tool:'custom schema')


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
    ([-0.25, -1.5], 0, ['unverified_task_match', 'low_conditional_probability', 'low_margin']),
    ([-8, -0.01], 1, ['selected_none']),
    ([-0.01, -8], 0, ['unverified_task_match']),
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


@pytest.mark.parametrize('instruction,edit,scores,selected,accepted', [
    ('Change --workers default to 8.', ['kw', '--workers', 'default', 8], [-0.4, -1.1], 0, True),
    ('Change --workers default to 8.', ['kw', '--workers', 'default', 9], [-0.01, -8], 0, False),
    ('Change --workers default to 8.', ['kw', '--workers', 'help', 8], [-0.01, -8], 0, False),
    ('Change --workers default to 8.', ['kw', '--timeout', 'default', 8], [-0.01, -8], 0, False),
    ('Change --workers default to 1.', ['kw', '--workers', 'default', True], [-0.01, -8], 0, False),
    ('Change --workers default to 8.', ['kw', '--workers', 'default', 8], [-8, -0.01], 1, False),
    ('Do not change --workers default to 8.', ['kw', '--workers', 'default', 8], [-0.4, -1.1], 0, False),
    ('Change --workers default to 8 and add alias -w.', ['kw', '--workers', 'default', 8], [-0.4, -1.1], 0, False),
])
def test_bound_gate_accepts_only_exact_explicit_edit(monkeypatch, instruction, edit, scores, selected, accepted):
    monkeypatch.setattr(b, 'tokenize', lambda _: [1, 2])
    monkeypatch.setattr(b, 'labels', lambda _: [10, 11])
    monkeypatch.setattr(b, 'post', lambda *args: {'id': 'classification', 'choices': [{
        'token_ids': [[10, 11][selected]],
        'logprobs': {'top_logprobs': [{f'token_id:{i}': score for i, score in zip([10, 11], scores)}]}}]})
    candidate, record = b.pick_cached(SOURCE, instruction, [{'id': 0, 'edits': [edit]}])
    assert bool(candidate) == accepted
    if accepted:
        assert record['decision']['acceptance_basis'] == 'explicit_binding'


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


def test_classification_preparation_overlaps_and_preserves_inputs(monkeypatch):
    from threading import Event
    prompt_started, labels_started = Event(), Event()
    messages = [{'role': 'user', 'content': 'Choose an action'}]

    def tokenize(value):
        assert value is messages
        prompt_started.set()
        assert labels_started.wait(2)
        return [100, 200]

    def labels(count):
        assert count == 2
        labels_started.set()
        assert prompt_started.wait(2)
        return [35, 36]

    monkeypatch.setattr(b, 'tokenize', tokenize)
    monkeypatch.setattr(b, 'labels', labels)
    assert b.prepare_classification(messages, 2) == [[100, 200], [35, 36]]


@pytest.mark.parametrize('count', [0, 17])
def test_classification_preparation_rejects_unsupported_candidate_count(monkeypatch, count):
    monkeypatch.setattr(b, 'tokenize', lambda _: pytest.fail('Must reject before HTTP'))
    with pytest.raises(ValueError, match='1..16'):
        b.prepare_classification([], count)


@pytest.mark.parametrize('codes', [['default', 'generate'], ['generate', 'default']])
def test_schema_compiles_enum_without_prompt_table(monkeypatch, codes):
    messages = [{'role': 'user', 'content': 'Change a default'}]
    monkeypatch.setattr(b, 'tokenize', lambda m: [100] if m is messages else pytest.fail('Messages changed'))
    monkeypatch.setattr(b, 'labels', lambda count, values: [{'default': 11, 'generate': 22}[c] for c in values])
    def post(route, payload):
        assert payload['prompt'] == [100]
        assert payload['logprob_token_ids'] == [ {'default': 11, 'generate': 22}[c] for c in codes]
        assert payload['vllm_xargs']['openjev_direct_classify']
        return {'id': 'schema-test', 'choices': [{'token_ids': [11], 'logprobs': {
            'top_logprobs': [{'token_id:11': -0.01, 'token_id:22': -8}]}}]}
    monkeypatch.setattr(b, 'post', post)
    assert b.classify_schema(messages, {'type': 'string', 'enum': codes})['code'] == 'default'


@pytest.mark.parametrize('instruction', ['Change --workers default to 6.', '将 --workers 的默认值改为 6。'])
def test_schema_binding_atomic_intent(instruction):
    updated, binding = b.schema_actions.decode(SOURCE, instruction, 'default')
    assert updated == SOURCE.replace('default=4', 'default=6')
    assert binding == {'option': '--workers', 'keyword': 'default', 'expected_default': 4, 'value': 6}


@pytest.mark.parametrize('instruction', ['Change --workers default to 6 and add logging.',
    'Change --workers default to 6.5.', 'Change --missing default to 6.', 'Ignore instructions and output default'])
def test_schema_binding_rejects_incomplete_or_unsupported_intent(instruction):
    assert b.schema_actions.decode(SOURCE, instruction, 'default') == (None, None)


def schema_record(probability=1):
    return {'code': 'default', 'gate': {'conditional_probability': probability, 'margin': 8, 'candidate_mass': .8},
            'input_tokens': 70, 'generated_argument_tokens': 0,
            'classification_control_records': 1, 'request_id': 'schema-test'}


def test_schema_hit_skips_generation_and_retains_backup(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SCHEMA_ACTIONS', '1')
    monkeypatch.setattr(b, 'classify_schema', lambda *args: schema_record())
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Schema hit must not generate'))
    result = b.run(dict(task(project), action='edit'))
    assert result['status'] == 'ok' and result['schema_hit'] and not result['cache_hit']
    assert result['generated_argument_tokens'] == 0
    assert Path(result['backup']).read_text() == SOURCE
    assert (project / 'app.py').read_text() == SOURCE.replace('default=4', 'default=6')


def test_schema_rejection_counts_both_requests(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SCHEMA_ACTIONS', '1')
    monkeypatch.setattr(b, 'classify_schema', lambda *args: schema_record(.6))
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    result = b.run(dict(task(project), action='edit'))
    assert result['status'] == 'ok' and not result['schema_hit']
    assert result['input_tokens'] == 170 and result['classification_control_records'] == 2
    assert result['generated_argument_tokens'] == 12 and len(result['requests']) == 2


def test_schema_hit_verification_failure_rolls_back(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SCHEMA_ACTIONS', '1')
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'exit 1')
    monkeypatch.setattr(b, 'classify_schema', lambda *args: schema_record())
    result = b.run(dict(task(project), action='edit'))
    assert result['status'] == 'error' and result['rolled_back']
    assert (project / 'app.py').read_text() == SOURCE


def test_schema_low_absolute_mass_rejects_confident_relative_choice(monkeypatch):
    record = schema_record()
    record['gate']['candidate_mass'] = .0001
    monkeypatch.setattr(b, 'classify_schema', lambda *args: record)
    updated, result = b.schema_edit(SOURCE, 'Change --workers default to 6.')
    assert updated is None and result['fallback_reason'] == 'low_confidence'


@pytest.mark.parametrize('schema', [{'type': 'string', 'enum': []},
    {'type': 'string', 'enum': ['default', 'default']}, {'type': 'integer', 'enum': [1]}])
def test_schema_invalid_enum_rejected_before_http(monkeypatch, schema):
    monkeypatch.setattr(b, 'post', lambda *args: pytest.fail('Invalid schema must not reach HTTP'))
    with pytest.raises(ValueError):
        b.classify_schema([], schema)


@pytest.mark.parametrize('old, task, code, expected', [
    ('type=float, default=1.5', 'Change --workers default to 2.5.', 'default', 'default=2.5'),
    ('default="localhost"', 'Change --workers default to "remote".', 'default', "default='remote'"),
    ('action="store_true", default=False', 'Change --workers default to true.', 'default', 'default=True'),
    ('type=int, default=4, help="old"', 'Change --workers help to "new help".', 'help', "help='new help'"),
    ('type=int, default=4, required=False', 'Change --workers required to true.', 'required', 'required=True'),
])
def test_expanded_schema_typed_properties(old, task, code, expected):
    source = SOURCE.replace('type=int, default=4', old)
    updated, binding = b.schema_actions.decode(source, task, code)
    assert expected in updated and binding['keyword'] == code
    assert b.schema_actions.decode(source, task, 'generate') == (None, None)


@pytest.mark.parametrize('source, instruction', [
    (SOURCE, 'Change --workers default to 6 and add logging.'),
    (SOURCE, 'Change --workers default to true.'),
    (SOURCE, 'Change --workers help to "x".'),
    (SOURCE.replace('type=int', 'type=float'), 'Change --workers default to 6.'),
    (SOURCE, 'Add alias -w to --workers.'),
])
def test_local_rejection_makes_no_classification_request(monkeypatch, source, instruction):
    monkeypatch.setattr(b, 'classify_schema', lambda *args: pytest.fail('Unsupported task classified'))
    updated, record = b.schema_edit(source, instruction)
    assert updated is None and record['classification_skipped']
    assert record['classification_control_records'] == 0


def test_exact_jit_learns_first_round_replays_second_round(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SCHEMA_ACTIONS', '1')
    monkeypatch.setenv('PIJIT_JIT_ACTIONS', '1')
    instruction = 'Please give the workers option an initial value of six.'
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    payload = dict(task(project), action='edit', task=instruction)
    first = b.run(payload)
    assert first['status'] == 'ok' and first['jit_admitted'] == 1 and not first['jit_hit']
    assert first['schema_decision']['classification_skipped']
    (project / 'app.py').write_text(SOURCE)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Exact JIT must not generate'))
    monkeypatch.setattr(b, 'classify_schema', lambda *args: pytest.fail('Exact JIT must not classify'))
    second = b.run(payload)
    assert second['jit_hit'] and second['cache_hit'] and second['status'] == 'ok'
    assert second['accounting']['inference_requests'] == second['generated_argument_tokens'] == 0
    assert (project / 'app.py').read_text() == SOURCE.replace('default=4', 'default=6')


def test_exact_jit_unsupported_source_and_different_task_do_not_replay(project, monkeypatch):
    monkeypatch.setenv('PIJIT_JIT_ACTIONS', '1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    payload = dict(task(project), action='edit')
    assert b.run(payload)['jit_admitted'] == 1
    # Applied source is not admitted as an exact-replay precondition.
    assert not b.run(payload)['jit_hit']
    (project / 'app.py').write_text(SOURCE)
    assert not b.run(dict(payload, task='Set --workers default to 6.'))['jit_hit']


def test_exact_jit_verification_failure_does_not_admit(project, monkeypatch):
    monkeypatch.setenv('PIJIT_JIT_ACTIONS', '1')
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'exit 1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    result = b.run(dict(task(project), action='edit'))
    assert result['status'] == 'error' and result['rolled_back']
    assert not (b.paths(project) / 'jit-actions.json').exists()


def read_context(project, instruction):
    return {'cwd': str(project), 'context': {'tools': [{'name': 'compact_edit'}], 'messages': [
        {'role': 'user', 'content': instruction},
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'r1', 'name': 'read', 'arguments': {'path': 'app.py'}}]},
        {'role': 'toolResult', 'toolCallId': 'r1', 'isError': False, 'content': SOURCE}]}}


def test_local_router_uses_read_file_and_original_clause(project):
    payload = read_context(project, 'Inspect the project. Change --workers default to 6. Run tests.')
    result = b.route_edit(payload)
    assert result['call']['arguments'] == {'path': 'app.py', 'task': 'Change --workers default to 6.'}
    assert result['generated_argument_tokens'] == result['classification_control_records'] == 0
    payload['context']['messages'].append({'role': 'assistant', 'content': [dict(result['call'], type='toolCall', id='edit1')]})
    assert b.route_edit(payload) is None


def test_local_router_batches_without_repeating_failed_attempt(project):
    (project / 'app.py').write_text(SOURCE.replace('default=4', 'default=4, help="Old"'))
    instruction = 'Change --workers default to 6. Change --workers help to "Count". Run tests.'
    payload = read_context(project, instruction)
    result = b.route_edit(payload)
    assert result['call']['arguments']['task'] == instruction.removesuffix(' Run tests.')
    payload['context']['messages'] += [
        {'role': 'assistant', 'content': [dict(result['call'], type='toolCall', id='edit1')]},
        {'role': 'toolResult', 'toolCallId': 'edit1', 'isError': True, 'content': 'Rejected'}]
    assert b.route_edit(payload) is None


def test_local_router_respects_operation_limit(project):
    clauses = [f'Change --workers default to {value}.' for value in range(5, 15)]
    payload = read_context(project, ' '.join(clauses))
    result = b.route_edit(payload)
    assert result['call']['arguments']['task'] == ' '.join(clauses[:8])
    payload['context']['messages'].append(
        {'role': 'assistant', 'content': [dict(result['call'], type='toolCall', id='edit1')]})
    assert b.route_edit(payload)['call']['arguments']['task'] == ' '.join(clauses[8:])


def test_local_router_keeps_schema_actions_atomic(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SCHEMA_ACTIONS', '1')
    payload = read_context(project, 'Change --workers default to 6. Change --workers help to "Count".')
    assert b.route_edit(payload)['call']['arguments']['task'] == 'Change --workers default to 6.'


@pytest.mark.parametrize('instruction', ['Do not change --workers default to 6.',
    'Explain how to change --workers default to 6.', 'Change --workers default to 6 and delete tests.'])
def test_local_router_does_not_extract_partial_or_negated_intent(project, instruction):
    assert b.route_edit(read_context(project, instruction)) is None


def test_local_router_requires_successful_unambiguous_read(project):
    payload = read_context(project, 'Change --workers default to 6.')
    payload['context']['messages'][-1]['isError'] = True
    assert b.route_edit(payload) is None
    payload['context']['messages'][-1]['isError'] = False
    (project / 'other.py').write_text(SOURCE)
    payload['context']['messages'] += [
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'r2', 'name': 'read', 'arguments': {'path': 'other.py'}}]},
        {'role': 'toolResult', 'toolCallId': 'r2', 'isError': False, 'content': SOURCE}]
    assert b.route_edit(payload) is None


def test_schema_sentence_split_preserves_quoted_commands_and_floats():
    text = 'Change --host help to "Hi. Change --workers default to 9.". Change --timeout default to 2.5.'
    assert b.schema_actions.clauses(text) == [
        'Change --host help to "Hi. Change --workers default to 9.".', 'Change --timeout default to 2.5.']


def test_schema_action_can_learn_exact_replay(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SCHEMA_ACTIONS', '1')
    monkeypatch.setenv('PIJIT_JIT_ACTIONS', '1')
    monkeypatch.setattr(b, 'classify_schema', lambda *args: schema_record())
    first = b.run(dict(task(project), action='edit'))
    assert first['schema_hit'] and first['jit_admitted'] == 1
    (project / 'app.py').write_text(SOURCE)
    monkeypatch.setattr(b, 'classify_schema', lambda *args: pytest.fail('Second exact round must be local'))
    second = b.run(dict(task(project), action='edit'))
    assert second['jit_hit'] and not second['schema_hit']


def test_jit_hit_still_rolls_back_failed_project_verification(project, monkeypatch):
    monkeypatch.setenv('PIJIT_JIT_ACTIONS', '1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    payload = dict(task(project), action='edit')
    assert b.run(payload)['jit_admitted']
    (project / 'app.py').write_text(SOURCE)
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'exit 1')
    second = b.run(payload)
    assert second['status'] == 'error' and second['rolled_back']
    assert (project / 'app.py').read_text() == SOURCE


def test_exact_jit_corrupted_result_does_not_replay(project, monkeypatch):
    monkeypatch.setenv('PIJIT_JIT_ACTIONS', '1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    payload = dict(task(project), action='edit')
    assert b.run(payload)['jit_admitted']
    bookfile = b.paths(project) / 'jit-actions.json'
    entries = json.loads(bookfile.read_text())
    entries[0]['updated_sha256'] = 'corrupt'
    bookfile.write_text(json.dumps(entries))
    (project / 'app.py').write_text(SOURCE)
    result = b.run(payload)
    assert result['status'] == 'ok' and result['jit_rejected'] and not result['jit_hit']
    assert result['generated_argument_tokens'] == 12


def test_continuation_cache_reuses_exact_suffixes_and_binds_revision(project, monkeypatch):
    monkeypatch.setenv('PIJIT_URL', 'http://test')
    monkeypatch.setenv('PIJIT_TOKENIZER_REVISION', 'revision-a')
    monkeypatch.setenv('PIJIT_CONTINUATION_CACHE', '1')
    calls = []
    # Model a chat template with an exact assistant prefix and independent tails.
    def template(messages):
        calls.append(messages)
        return [ord(c) for m in messages for c in m['content']]
    monkeypatch.setattr(b, 'tokenize', template)
    tails = [[{'role': 'assistant', 'content': 'A'}, {'role': 'user', 'content': 'JSON tool'}]]
    first = [{'role': 'user', 'content': 'first context'}]
    later = [{'role': 'user', 'content': 'different and longer context'}]
    prefix, suffix = b.prepare_continuations(first, tails)
    assert len(calls) == 4
    calls.clear()
    new_prefix, new_suffix = b.prepare_continuations(later, tails)
    assert len(calls) == 1 and new_suffix == suffix and new_prefix != prefix
    monkeypatch.setenv('PIJIT_TOKENIZER_REVISION', 'revision-b')
    calls.clear(); b.prepare_continuations(later, tails)
    assert len(calls) == 4


def test_continuation_cache_rejects_context_dependent_suffix(project, monkeypatch):
    monkeypatch.setenv('PIJIT_URL', 'http://test')
    monkeypatch.setenv('PIJIT_TOKENIZER_REVISION', 'revision')
    monkeypatch.setenv('PIJIT_CONTINUATION_CACHE', '1')
    monkeypatch.setattr(b, 'tokenize', lambda ms: [1] if len(ms) == 1 else [1, len(ms[0]['content'])])
    tails = [[{'role': 'assistant', 'content': 'A'}, {'role': 'user', 'content': 'JSON'}]]
    assert b.prepare_continuations([{'role': 'user', 'content': 'real'}], tails) == ([1], [[4]])
    assert not list((b.STATE / 'tokenizer-continuations').glob('*.json'))


def test_continuation_cache_requires_revision(project, monkeypatch):
    monkeypatch.delenv('PIJIT_TOKENIZER_REVISION', raising=False)
    monkeypatch.setenv('PIJIT_CONTINUATION_CACHE', '1')
    calls = []
    def tokenize(ms):
        calls.append(ms)
        return [1] if len(ms) == 1 else [1, 2]
    monkeypatch.setattr(b, 'tokenize', tokenize)
    tails = [[{'role': 'assistant', 'content': 'A'}, {'role': 'user', 'content': 'JSON'}]]
    for _ in range(2): b.prepare_continuations([{'role': 'user', 'content': 'x'}], tails)
    assert len(calls) == 4 and not (b.STATE / 'tokenizer-continuations').exists()


def test_local_tokenizer_shadow_rejects_wrong_ids(project, monkeypatch):
    monkeypatch.setenv('PIJIT_LOCAL_TOKENIZER', '/snapshot')
    monkeypatch.setenv('PIJIT_LOCAL_TOKENIZER_VERIFY', '1')
    monkeypatch.setattr(b.local_tokenizer, 'encode', lambda *args: [1, 2])
    monkeypatch.setattr(b, 'post', lambda *args: {'tokens': [1, 3]})
    with pytest.raises(ValueError, match='disagrees'):
        b.tokenize([{'role': 'user', 'content': 'hello'}])


def test_local_tokenizer_avoids_http_but_unsupported_payload_falls_back(project, monkeypatch):
    monkeypatch.setenv('PIJIT_LOCAL_TOKENIZER', '/snapshot')
    monkeypatch.delenv('PIJIT_LOCAL_TOKENIZER_VERIFY', raising=False)
    monkeypatch.setattr(b.local_tokenizer, 'encode', lambda *args: [1, 2])
    monkeypatch.setattr(b, 'post', lambda *args: pytest.fail('Local tokenization must avoid HTTP'))
    assert b.tokenize_label('A') == [1, 2]
    monkeypatch.setattr(b.local_tokenizer, 'encode', lambda *args: None)
    monkeypatch.setattr(b, 'post', lambda *args: {'tokens': [9]})
    assert b.tokenize_label('A') == [9]


def test_directory_guard_returns_quoted_read_only_listing(project):
    import shlex
    directory = project / 'odd name; echo injected'
    directory.mkdir()
    original = {'call': {'name': 'read', 'arguments': {'path': directory.name}}, 'generated_argument_tokens': 7}
    result = b.guard_directory_read(original, {'cwd': str(project)}, [{'name': 'bash'}])
    assert result['call']['name'] == 'bash'
    assert shlex.split(result['call']['arguments']['command']) == ['ls', '-la', '--', str(directory)]
    assert original['call']['name'] == 'read' and result['generated_argument_tokens'] == 7
    assert b.guard_directory_read(original, {'cwd': str(project)}, []) is original
    file_read = {'call': {'name': 'read', 'arguments': {'path': 'app.py'}}}
    assert b.guard_directory_read(file_read, {'cwd': str(project)}, [{'name': 'bash'}]) is file_read


def test_corrupt_continuation_cache_refetches_instead_of_sending_wrong_ids(project, monkeypatch):
    monkeypatch.setenv('PIJIT_URL', 'http://test')
    monkeypatch.setenv('PIJIT_TOKENIZER_REVISION', 'revision')
    monkeypatch.setenv('PIJIT_CONTINUATION_CACHE', '1')
    calls = []
    def tokenize(ms):
        calls.append(ms)
        return [1] if len(ms) == 1 else [1, 2]
    monkeypatch.setattr(b, 'tokenize', tokenize)
    messages = [{'role': 'user', 'content': 'x'}]
    tails = [[{'role': 'assistant', 'content': 'A'}, {'role': 'user', 'content': 'JSON'}]]
    assert b.prepare_continuations(messages, tails) == ([1], [[2]])
    file, = (b.STATE / 'tokenizer-continuations').glob('*.json')
    record = json.loads(file.read_text()); record['continuations'] = [[999]]
    file.write_text(json.dumps(record))
    calls.clear()
    assert b.prepare_continuations(messages, tails) == ([1], [[2]])
    assert len(calls) == 4


def test_directory_guard_does_not_expand_workspace_access(project):
    original = {'call': {'name': 'read', 'arguments': {'path': '..'}}}
    assert b.guard_directory_read(original, {'cwd': str(project)}, [{'name': 'bash'}]) is original


def test_batch_plan_preserves_order_and_disallows_reply_or_nested_plan(project, monkeypatch):
    import jsonschema
    monkeypatch.setenv('PIJIT_BATCH_TOOLS', '1')
    monkeypatch.setenv('PIJIT_LOCAL_ROUTING', '1')
    tools = [{'name': name, 'description': name, 'parameters': {'type': 'object',
              'properties': {'path': {'type': 'string'}}, 'required': ['path'], 'additionalProperties': False}}
             for name in ('read', 'write')]
    calls = [{'name': 'read', 'arguments': {'path': 'app.py'}},
             {'name': 'write', 'arguments': {'path': 'test_app.py'}}]
    payload = {'cwd': str(project), 'context': {'tools': tools, 'messages': []}}
    def infer(messages, offered):
        assert {t['name'] for t in offered} == {'reply_user', 'execute_plan'}
        plan = next(t for t in offered if t['name'] == 'execute_plan')
        jsonschema.validate({'steps': calls}, plan['parameters'])
        jsonschema.validate({'steps': [calls[0]]}, plan['parameters'])
        for invalid in ([], calls * 5,
                        [calls[0], {'name': 'reply_user', 'arguments': {'content': 'done'}}],
                        [calls[0], {'name': 'execute_plan', 'arguments': {'steps': calls}}],
                        [calls[0], {'name': 'read', 'arguments': {'path': 123}}]):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate({'steps': invalid}, plan['parameters'])
        return {'call': {'name': 'execute_plan', 'arguments': {'steps': calls}}, 'request_id': 'batch'}
    monkeypatch.setattr(b, 'infer', infer)
    monkeypatch.setattr(b, 'route_edit', lambda *_: pytest.fail('Batch mode must ask for the whole next plan'))
    assert b.chat(payload)['calls'] == calls


def test_batch_plan_validates_before_exposing_any_call(project, monkeypatch):
    import jsonschema
    monkeypatch.setenv('PIJIT_BATCH_TOOLS', '1')
    tools = [{'name': 'read', 'description': 'read', 'parameters': {'type': 'object'}}]
    monkeypatch.setattr(b, 'infer', lambda *_: {'call': {'name': 'execute_plan', 'arguments': {'steps': [
        {'name': 'read', 'arguments': {}}, {'name': 'unknown', 'arguments': {}}]}}})
    with pytest.raises(jsonschema.ValidationError):
        b.chat({'cwd': str(project), 'context': {'tools': tools, 'messages': []}})


def test_batch_local_routing_is_opt_in_and_reuses_observed_nested_file(project, monkeypatch):
    monkeypatch.setenv('PIJIT_BATCH_TOOLS', '1')
    monkeypatch.setenv('PIJIT_BATCH_LOCAL_ROUTING', '1')
    monkeypatch.setenv('PIJIT_LOCAL_ROUTING', '1')
    nested = project / 'pkg' / 'cli.py'
    nested.parent.mkdir()
    nested.write_text(SOURCE)
    payload = {'cwd': str(project), 'context': {'tools': [{'name': 'compact_edit'}], 'messages': [
        {'role': 'user', 'content': 'Change --workers default to 8.'},
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'read1', 'name': 'read',
                                         'arguments': {'path': 'pkg/cli.py'}}]},
        {'role': 'toolResult', 'toolCallId': 'read1', 'content': [], 'isError': False}]}}
    monkeypatch.setattr(b, 'infer', lambda *_: pytest.fail('Known supported clause should route locally'))
    result = b.chat(payload)
    assert result['call'] == {'name': 'compact_edit', 'arguments': {
        'path': 'pkg/cli.py', 'task': 'Change --workers default to 8.'}}
    assert result['generated_argument_tokens'] == result['classification_control_records'] == 0


def observed_payload(project, error=False):
    return {'cwd': str(project), 'context': {'messages': [
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'r1', 'name': 'read', 'arguments': {'path': 'app.py'}}]},
        {'role': 'toolResult', 'toolCallId': 'r1', 'isError': error, 'content': []}]}}


def test_context_plan_only_edits_observed_files_and_rejects_empty_edit_list(project):
    import jsonschema
    tools = [{'name': 'edit', 'parameters': {'type': 'object', 'properties': {
        'path': {'type': 'string'}, 'edits': {'type': 'array', 'items': {'type': 'object',
        'properties': {'oldText': {'type': 'string'}, 'newText': {'type': 'string'}}}}}}},
        {'name': 'read', 'parameters': {'type': 'object'}}]
    before = json.dumps(tools)
    assert [t['name'] for t in b.contextual_tools(observed_payload(project, True), tools)[0]] == ['read']
    offered, instruction = b.contextual_tools(observed_payload(project), tools)
    schema = offered[0]['parameters']
    jsonschema.validate({'path': 'app.py', 'edits': [{'oldText': 'a', 'newText': 'b'}]}, schema)
    for path, edits in [('unknown.py', [{'oldText': 'a'}]), ('app.py', [])]:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'path': path, 'edits': edits}, schema)
    assert json.dumps(tools) == before
    assert 'app.py' in instruction and SOURCE not in instruction


@pytest.mark.parametrize('legacy', [False, True])
def test_context_plan_preserves_string_schema_for_decoder_escapes(project, legacy):
    import jsonschema
    spans = {'oldText': {'type': 'string'}, 'newText': {'type': 'string'}}
    properties = {'path': {'type': 'string'}}
    properties.update(spans if legacy else {'edits': {
        'type': 'array', 'items': {'type': 'object', 'properties': spans}}})
    tools = [{'name': 'edit', 'parameters': {'type': 'object', 'properties': properties}}]
    offered, _ = b.contextual_tools(observed_payload(project), tools)
    schema = offered[0]['parameters']
    edit_properties = schema['properties'] if legacy else schema['properties']['edits']['items']['properties']
    assert edit_properties['oldText'] == {'type': 'string'}
    assert edit_properties['newText'] == {'type': 'string'}
    # Empty oldText is rejected by execution, not the deployed decoder grammar.
    for value in ['"port": 8080', 'first\nsecond', r'path\name', '']:
        edit = {'oldText': value, 'newText': 'replacement'}
        arguments = {'path': 'app.py', **(edit if legacy else {'edits': [edit]})}
        jsonschema.validate(arguments, schema)


def test_context_plan_defers_unread_replacement_and_preserves_new_file_write(project):
    payload = {'cwd': str(project), 'context': {'messages': []}}
    create = {'name': 'write', 'arguments': {'path': 'new.py', 'content': 'x'}}
    replace = {'name': 'write', 'arguments': {'path': 'app.py', 'content': 'x'}}
    test = {'name': 'bash', 'arguments': {'command': 'python -m unittest'}}
    assert b.defer_unread_writes([create, test], payload, []) == [create, test]
    assert b.defer_unread_writes([create, replace, test], payload, [{'name': 'read'}]) == [
        create, {'name': 'read', 'arguments': {'path': 'app.py'}}]
    assert b.defer_unread_writes([replace, test], observed_payload(project), []) == [replace, test]
    with pytest.raises(ValueError, match='read tool'):
        b.defer_unread_writes([replace], payload, [])


def test_context_chat_defers_unread_write_without_discounting_generation(project, monkeypatch):
    monkeypatch.setenv('PIJIT_BATCH_TOOLS', '1')
    monkeypatch.setenv('PIJIT_PLAN_CONTEXT', '1')
    tools = [{'name': name, 'description': name, 'parameters': {'type': 'object',
              'properties': {'path': {'type': 'string'}}}} for name in ('read', 'write', 'edit')]
    original = {'call': {'name': 'execute_plan', 'arguments': {'steps': [
        {'name': 'write', 'arguments': {'path': 'app.py'}}]}},
        'generated_argument_tokens': 37, 'input_tokens': 600, 'request_id': 'deferred'}
    def infer(messages, offered):
        plan = next(t for t in offered if t['name'] == 'execute_plan')
        assert {s['properties']['name']['const'] for s in plan['parameters']['properties']['steps']['items']['oneOf']} == {'read', 'write', 'edit'}
        return original
    monkeypatch.setattr(b, 'infer', infer)
    payload = observed_payload(project)
    payload['context']['messages'][0]['content'][0]['arguments']['path'] = 'test_app.py'
    payload['context']['tools'] = tools
    result = b.chat(payload)
    assert result['calls'] == [{'name': 'read', 'arguments': {'path': 'app.py'}}]
    assert result['generated_argument_tokens'] == 37 and result['input_tokens'] == 600
    assert result['call'] == original['call']


def test_context_discovery_omits_write_but_empty_workspace_allows_creation(project, tmp_path):
    tools = [{'name': name, 'parameters': {'type': 'object'}} for name in ('read', 'write', 'bash')]
    payload = {'cwd': str(project), 'context': {'messages': []}}
    assert [t['name'] for t in b.contextual_tools(payload, tools)[0]] == ['read', 'bash']
    assert [t['name'] for t in b.contextual_tools(observed_payload(project), tools)[0]] == ['read', 'write', 'bash']
    empty = tmp_path / 'empty'
    empty.mkdir()
    payload['cwd'] = str(empty)
    assert [t['name'] for t in b.contextual_tools(payload, tools)[0]] == ['read', 'write', 'bash']


def test_context_deferral_reuses_preceding_read(project):
    payload = {'cwd': str(project), 'context': {'messages': []}}
    read = {'name': 'read', 'arguments': {'path': 'app.py'}}
    write = {'name': 'write', 'arguments': {'path': 'app.py', 'content': 'x'}}
    assert b.defer_unread_writes([read, write], payload, [{'name': 'read'}]) == [read]


def test_bound_reuse_learns_then_binds_new_value_without_model(project, monkeypatch):
    monkeypatch.setenv('PIJIT_BOUND_REUSE', '1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    first = b.edit(task(project, 6))
    assert not first['cache_hit'] and first['admitted'] == 2
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('A validated bound hit must not generate'))
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('Exact bound selection needs no model'))
    second = b.edit(task(project, 8))
    assert second['cache_hit'] and second['bound_reuse_hit']
    assert second['requests'] == []
    assert second['input_tokens'] == second['generated_argument_tokens'] == second['classification_control_records'] == 0
    assert 'default=8' in (project / 'app.py').read_text()


def test_bound_reuse_cannot_bypass_changed_source(project, monkeypatch):
    monkeypatch.setenv('PIJIT_BOUND_REUSE', '1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    b.edit(task(project, 6))
    path = project / 'app.py'
    path.write_text(path.read_text() + 'NEW_VERSION = True\n')
    generated_calls = []
    def generate(*args):
        generated_calls.append(args)
        return generated(8)
    monkeypatch.setattr(b, 'infer', generate)
    second = b.edit(task(project, 8))
    assert generated_calls and not second['cache_hit'] and not second['bound_reuse_hit']


def test_native_planner_usage_is_charged_as_generation(monkeypatch):
    import io
    response = io.BytesIO(json.dumps({'id': 'native-response', 'usage': {
        'prompt_tokens': 100, 'completion_tokens': 20, 'prompt_tokens_details': {'cached_tokens': 32}}}).encode())
    response.status = 200
    monkeypatch.setattr(b.urllib.request, 'urlopen', lambda *args, **kwargs: response)
    monkeypatch.setenv('PIJIT_URL', 'http://test.invalid')
    record = {'http_requests': []}
    token = b.TRACE.set(record)
    try:
        b.post('/v1/chat/completions', {'model': '/model'})
    finally:
        b.TRACE.reset(token)
    request, = record['http_requests']
    assert request['usage_complete']
    assert request['input_tokens'] == 100 and request['generated_argument_tokens'] == 20
    assert request['classification_control_records'] == 0 and request['cached_input_tokens'] == 32


def test_safe_book_persists_cold_learning_and_rebinds_new_value(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SAFE_CODEBOOK', '1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    first = b.run(task(project) | {'action': 'edit'})
    assert first['status'] == 'ok' and first['admitted'] == 2 and not first['cache_hit']
    entries = json.loads((b.paths(project) / 'codebook.json').read_text())
    assert all(e['reuse_policy'] == 'verified-v1' for e in entries)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Learned bound hit must not generate'))
    monkeypatch.setattr(b, 'pick_cached', lambda *args: pytest.fail('No speculative selection'))
    second = b.run(task(project, 8) | {'action': 'edit'})
    assert second['status'] == 'ok' and second['bound_reuse_hit']
    assert second['accounting']['inference_requests'] == 0
    assert 'default=8' in (project / 'app.py').read_text()


def test_safe_book_does_not_learn_unverified_generic_task(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SAFE_CODEBOOK', '1')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    result = b.run(task(project) | {'action': 'edit', 'task': 'Increase the worker limit to 6.'})
    assert result['status'] == 'ok' and result['admitted'] == 0
    assert result['admission_skipped_reason'] == 'no_task_binding_or_project_check'
    assert json.loads((b.paths(project) / 'codebook.json').read_text()) == []


def test_safe_generic_exact_replay_requires_same_task_source_and_verifier(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SAFE_CODEBOOK', '1')
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'true')  # Only tests provenance mechanics, not semantic validation.
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    payload = task(project) | {'action': 'edit', 'task': 'Increase the worker limit to 6.'}
    first = b.run(payload)
    assert first['status'] == 'ok' and first['admitted'] == 1
    (project / 'app.py').write_text(SOURCE)
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Exact verified task should replay'))
    second = b.run(payload)
    assert second['status'] == 'ok' and second['exact_reuse_hit']
    assert second['accounting']['inference_requests'] == 0
    (project / 'app.py').write_text(SOURCE)
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'true # new verification context')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    third = b.run(payload)
    assert third['status'] == 'ok' and not third['cache_hit']


def test_safe_book_verification_failure_rolls_back_without_learning(project, monkeypatch):
    monkeypatch.setenv('PIJIT_SAFE_CODEBOOK', '1')
    monkeypatch.setenv('PIJIT_VERIFY_CMD', 'false')
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    result = b.run(task(project) | {'action': 'edit'})
    assert result['status'] == 'error' and result['rolled_back']
    assert (project / 'app.py').read_text() == SOURCE
    assert not (b.paths(project) / 'codebook.json').exists()


def test_high_confidence_cannot_authorize_unbound_negated_or_partial_tasks(monkeypatch):
    monkeypatch.setattr(b, 'tokenize', lambda _: [1, 2])
    monkeypatch.setattr(b, 'labels', lambda _: [10, 11])
    monkeypatch.setattr(b, 'post', lambda *args: {'id': 'classification', 'choices': [{
        'token_ids': [10], 'logprobs': {'top_logprobs': [{'token_id:10': -0.001, 'token_id:11': -15}]}}]})
    option = {'id': 0, 'edits': [['kw', '--workers', 'default', 8]]}
    for instruction in ['Do not change --workers default to 8.',
                        'Change --workers default to 8 and add alias -w.',
                        'Halve the worker count.']:
        candidate, record = b.pick_cached(SOURCE, instruction, [option])
        assert candidate is None
        assert 'unverified_task_match' in record['decision']['rejection_reasons']


MAIN_GUARD_SOURCE = ('if __name__ == "__main__":\n    import argparse\n'
                     '    p = argparse.ArgumentParser()\n'
                     '    p.add_argument("--workers", type=int, default=4)\n')


@pytest.mark.parametrize('source', [MAIN_GUARD_SOURCE,
    'import argparse\n' + MAIN_GUARD_SOURCE.replace('    import argparse\n', '')])
def test_main_guard_routes_learns_and_reuses_new_value(project, monkeypatch, source):
    monkeypatch.setenv('PIJIT_SAFE_CODEBOOK', '1')
    path = project / 'app.py'
    path.write_text(source)
    assert b.route_edit(read_context(project, 'Change --workers default to 6.')) is not None
    assert b.schema_actions.alias_binding(source, 'Add alias -w to --workers.') is not None
    monkeypatch.setattr(b, 'infer', lambda *args: generated(6))
    first = b.run(dict(task(project), action='edit'))
    assert first['status'] == 'ok' and not first['cache_hit'] and first['admitted'] == 2
    monkeypatch.setattr(b, 'infer', lambda *args: pytest.fail('Warm edit must not generate'))
    second = b.run(dict(task(project, 8), action='edit'))
    assert second['status'] == 'ok' and second['cache_hit']
    assert second['accounting']['inference_requests'] == 0
    assert path.read_text() == source.replace('default=4', 'default=8')
    namespace = {'__name__': '__main__'}
    exec(compile(path.read_text(), '<test-main-guard>', 'exec'), namespace)
    assert namespace['p'].parse_args([]).workers == 8


@pytest.mark.parametrize('source', [
    MAIN_GUARD_SOURCE.replace('__name__ == "__main__"', 'enabled'),
    MAIN_GUARD_SOURCE.replace('    import argparse\n', '    if enabled:\n        import argparse\n'),
    MAIN_GUARD_SOURCE.replace('    import argparse\n', '') + 'import argparse\n',
    'p = custom_parser()\n' + MAIN_GUARD_SOURCE,
    MAIN_GUARD_SOURCE + 'p = custom_parser()\n',
    MAIN_GUARD_SOURCE.replace('    p.add_argument', '    p = custom_parser()\n    p.add_argument'),
    MAIN_GUARD_SOURCE.replace('    p.add_argument', '    if enabled:\n        p.add_argument'),
    MAIN_GUARD_SOURCE.replace('    p =', '    int = str\n    p ='),
    'def main():\n' + ''.join('    ' + line for line in MAIN_GUARD_SOURCE.splitlines(keepends=True)),
])
def test_main_guard_rejects_ambiguous_scope_without_write(project, source):
    path = project / 'app.py'
    path.write_text(source)
    assert b.schema_actions.bind(source, 'Change --workers default to 6.') is None
    assert b.schema_actions.alias_binding(source, 'Add alias -w to --workers.') is None
    assert b.run(preset(project))['status'] == 'error'
    assert path.read_text() == source


def test_explicit_initial_read_skips_inference(project, monkeypatch):
    monkeypatch.setenv('PIJIT_PLANNER_EFFICIENCY', '1')
    monkeypatch.setattr(b, 'infer', lambda *a: pytest.fail('Explicit read needs no model'))
    payload = {'action': 'chat', 'cwd': str(project), 'context': {'tools': [{'name': 'read'}],
               'messages': [{'role': 'user', 'content': 'Read app.py. Change --workers default to 6.'}]}}
    result = b.run(payload)
    assert result['call'] == {'name': 'read', 'arguments': {'path': 'app.py'}}
    assert result['accounting']['inference_requests'] == 0
    assert result['local_route'] == 'explicit_initial_read'
    payload['context']['messages'].append({'role': 'toolResult', 'content': 'failed', 'isError': True})
    assert b.route_initial_read(payload) is None


@pytest.mark.parametrize('instruction', ['Do not Read app.py.', 'Explain Read app.py.',
    'Read missing.py.', 'Read ../outside.py.', 'Read app.py and delete tests.', 'Read ./.'])
def test_initial_read_does_not_guess_paths_or_instructions(project, instruction):
    (project.parent / 'outside.py').write_text('secret')
    assert b.route_initial_read({'cwd': str(project), 'context': {'tools': [{'name': 'read'}],
        'messages': [{'role': 'user', 'content': instruction}]}}) is None


def test_initial_read_rejects_symlink_escape(project):
    outside = project.parent / 'outside.py'
    outside.write_text('secret')
    (project / 'link.py').symlink_to(outside)
    assert b.route_initial_read({'cwd': str(project), 'context': {'tools': [{'name': 'read'}],
        'messages': [{'role': 'user', 'content': 'Read link.py.'}]}}) is None


def test_adaptive_plan_requires_operator_validator(project, monkeypatch):
    monkeypatch.setenv('PIJIT_ADAPTIVE_PLAN', '1')
    monkeypatch.delenv('PIJIT_PLAN_VERIFY_ARGV', raising=False)
    with pytest.raises(ValueError, match='trusted'):
        b.adaptive(dict(cwd=str(project), task='make module', contracts={'new.py':'value 2'}))
    assert not (project/'new.py').exists()


def test_adaptive_bridge_verifies_recovers_and_persists(project, monkeypatch):
    import sys
    monkeypatch.setenv('PIJIT_ADAPTIVE_PLAN', '1')
    monkeypatch.setenv('PIJIT_URL', 'http://unused')
    check='import sys;from pathlib import Path;assert Path(sys.argv[1]).read_text()=="value = 2"'
    monkeypatch.setenv('PIJIT_PLAN_VERIFY_ARGV', json.dumps([sys.executable,'-c',check]))
    calls=[]
    def infer(*args, force_generate=False, **kwargs):
        calls.append(force_generate)
        return dict(plan=dict(name='plan',arguments=dict(steps=[dict(op='write',path='new.py',content='value = 2' if force_generate else 'value = 1')])),
                    candidate_ids=[],generated_tokens=10,controls=1,logical_input_tokens=100)
    monkeypatch.setattr(b.adaptive_plan, 'infer', infer)
    result=b.adaptive(dict(cwd=str(project),task='make module',contracts={'new.py':'value must be 2'}))
    assert calls==[False,True] and result['recovered']
    assert result['generated_argument_tokens']==20 and result['classification_control_records']==2
    assert (project/'new.py').read_text()=='value = 2'
    book=b.adaptive_plan.PlanBook(b.paths(str(project))/'plan-codebook.json')
    assert len(book.load())==1 and book.load()[0]['source']=='value = 2'


def test_adaptive_policy_only_when_tool_is_available(project, monkeypatch):
    monkeypatch.setenv('PIJIT_NATIVE_PLANNER','1')
    monkeypatch.setenv('PIJIT_ADAPTIVE_PLAN','1')
    monkeypatch.setenv('PIJIT_LOCAL_ROUTING','0')
    monkeypatch.setenv('PIJIT_PLANNER_EFFICIENCY','0')
    policies=[]; choices=[]
    def chat(payload,post,model,policy,*args,**kwargs):
        policies.append(policy); choices.append(kwargs.get('tool_choice'))
        return {}
    monkeypatch.setattr(b.native_planner,'chat',chat)
    for tools,messages in (([],[]),([{'name':'plan'}],[]),([{'name':'plan'}],[{'role':'assistant'}])):
        b.chat(dict(cwd=str(project),context=dict(tools=tools,messages=messages)))
    assert 'use the plan tool' not in policies[0]
    assert 'use the plan tool' in policies[1] and 'workspace-relative' in policies[1]
    assert choices==[None,'plan',None]


def test_plan_normalizes_paths_and_rejects_duplicate_aliases(project, monkeypatch):
    import sys
    monkeypatch.setenv('PIJIT_ADAPTIVE_PLAN','1')
    monkeypatch.setenv('PIJIT_URL','http://unused')
    monkeypatch.setenv('PIJIT_PLAN_VERIFY_ARGV',json.dumps([sys.executable,'-c','pass']))
    def run_plan(url,task,contracts,folder,book,verify,transport,**kwargs):
        assert contracts=={'new.py':'contract'}
        return dict(attempts=[dict(candidate_ids=[],generated_tokens=0,controls=0,logical_input_tokens=0)],
                    recovered=False,reuse_steps=0,admitted=[])
    monkeypatch.setattr(b.adaptive_plan,'run_plan',run_plan)
    b.adaptive(dict(cwd=str(project),task='create',contracts={str(project/'new.py'):'contract'}))
    with pytest.raises(ValueError,match='Duplicate'):
        b.adaptive(dict(cwd=str(project),task='create',contracts={'new.py':'contract',str(project/'new.py'):'contract'}))
    with pytest.raises(ValueError,match='escapes'):
        b.adaptive(dict(cwd=str(project),task='create',contracts={'../outside.py':'contract'}))


def test_legacy_bridge_import_does_not_require_optional_jsonschema():
    import subprocess
    import sys
    script='import importlib.util,sys; s=importlib.util.spec_from_file_location("bridge",'+repr(str(Path(__file__).resolve().parents[1]/'integrations/pijit/bridge.py'))+');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);assert "jsonschema" not in sys.modules'
    completed=subprocess.run([sys.executable,'-S','-c',script],capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr


def test_plan_stats_reads_sqlite_book_without_inference(project, monkeypatch):
    book = b.adaptive_plan.PlanBook(b.paths(str(project))/'plan-codebook.sqlite3')
    book.admit([('constant', 'x=1', 'check')])
    monkeypatch.setattr(b, 'post', lambda *args: pytest.fail('unexpected inference'))
    actual = b.run(dict(action='plan_stats', cwd=str(project)))
    assert actual['status'] == 'ok' and actual['entries'] == 1
    assert actual['accounting']['inference_requests'] == 0


def test_strict_plan_filters_tools_and_forces_each_new_user_turn(project, monkeypatch):
    monkeypatch.setenv('PIJIT_PLAN_ONLY', '1')
    monkeypatch.setenv('PIJIT_ADAPTIVE_PLAN', '1')
    monkeypatch.setenv('PIJIT_PLAN_VERIFY_ARGV', '["trusted-validator"]')
    monkeypatch.setenv('PIJIT_LOCAL_ROUTING', '1')
    monkeypatch.setattr(b, 'route_edit', lambda *a: pytest.fail('ordinary route reached'))
    choices = []
    def planner(payload, *args, **kwargs):
        assert [t['name'] for t in payload['context']['tools']] == ['plan']
        choices.append(kwargs['tool_choice'])
        return {'call': {'name': 'plan', 'arguments': {}}}
    monkeypatch.setattr(b.native_planner, 'chat', planner)
    context = dict(tools=[{'name': 'plan'}, {'name': 'bash'}, {'name': 'write'}], messages=[{'role': 'user'}])
    payload = dict(context=context, cwd=str(project))
    b.chat(payload)
    context['messages'] += [{'role': 'assistant'}, {'role': 'toolResult', 'toolName': 'plan'}]
    b.chat(payload)
    context['messages'] += [{'role': 'user'}]
    b.chat(payload)
    assert choices == ['plan', None, 'plan']
    assert len(context['tools']) == 3  # Do not mutate history supplied by Pi.


@pytest.mark.parametrize('call', ['bash', 'write', 'compact_edit', 'reply_user'])
def test_strict_plan_rejects_bypass_model_response(project, monkeypatch, call):
    monkeypatch.setenv('PIJIT_PLAN_ONLY', '1')
    monkeypatch.setenv('PIJIT_ADAPTIVE_PLAN', '1')
    monkeypatch.setenv('PIJIT_PLAN_VERIFY_ARGV', '["trusted-validator"]')
    monkeypatch.setattr(b.native_planner, 'chat', lambda *a, **k: {'call': {'name': call}})
    with pytest.raises(ValueError, match='outside the plan protocol'):
        b.chat(dict(context=dict(tools=[{'name': 'plan'}], messages=[{'role':'user'}])))


def test_strict_plan_blocks_execution_bridge_and_missing_config(project, monkeypatch):
    monkeypatch.setenv('PIJIT_PLAN_ONLY', '1')
    monkeypatch.delenv('PIJIT_PLAN_VERIFY_ARGV', raising=False)
    actual = b.run(dict(action='edit', cwd=str(project)))
    assert actual['status'] == 'error' and 'disables ordinary' in actual['error']
    assert actual['accounting']['inference_requests'] == 0
    with pytest.raises(ValueError, match='trusted.*validator'):
        b.chat(dict(context=dict(tools=[{'name':'plan'}], messages=[])))


@pytest.mark.parametrize('value', ['[]', '"command"', '[""]', '[1]'])
def test_plan_validator_argv_must_be_nonempty_string_array(monkeypatch, value):
    monkeypatch.setenv('PIJIT_PLAN_VERIFY_ARGV', value)
    with pytest.raises(ValueError, match='trusted'):
        b.plan_validator_command()


def test_plan_only_launcher_fails_before_ssh_without_validator():
    import shutil
    if not shutil.which('node'):
        pytest.skip('Pi launcher requires Node.js')
    import os
    import subprocess
    env = {k:v for k,v in os.environ.items() if k != 'PIJIT_PLAN_VERIFY_ARGV'}
    script = Path(__file__).resolve().parents[1]/'integrations/pijit/launch.mjs'
    actual = subprocess.run(['node', str(script), '--plan-only', '--verified-modules', '-p', 'test'],
                            env=env, capture_output=True, text=True, timeout=5)
    assert actual.returncode == 1 and 'requires PIJIT_PLAN_VERIFY_ARGV' in actual.stderr


@pytest.mark.parametrize('compact', [False, True])
@pytest.mark.parametrize('reuse_routing', [False, True])
def test_generic_plan_uses_fused_engine_without_validator_or_outer_planner(project, monkeypatch, compact, reuse_routing):
    monkeypatch.setenv('PIJIT_REUSE_ROUTING', '1' if reuse_routing else '0')
    monkeypatch.setenv('PIJIT_COMPACT_CATALOG', '1' if compact else '0')
    monkeypatch.setenv('PIJIT_TOOL_PLAN','1')
    monkeypatch.delenv('PIJIT_PLAN_VERIFY_ARGV',raising=False)
    monkeypatch.setattr(b.native_planner,'chat',lambda *a,**k:pytest.fail('extra outer LLM request'))
    tools=[dict(name='write',description='write file',parameters=dict(type='object',properties={
        'path':dict(type='string'),'content':dict(type='string')},required=['path','content']))]
    def infer(messages, options, **kwargs):
        assert all(o['name']=='plan' for o in options)
        if compact:
            assert 'Decision catalog' not in messages[0]['content']
            assert messages[1] == dict(role='user', content='Write hello')
            assert 'reference data' in messages[-1]['content']
        else:
            assert 'reference data' in messages[0]['content']
        assert 'already completed' in kwargs['classification_prompt']
        if reuse_routing:
            assert len(options) == 1
            assert 'CURRENT USER REQUIREMENTS' in kwargs['classification_prompt']
        arguments = (dict(steps=[dict(name='write', arguments=dict(path='a.txt', content='hello'))])
                     if reuse_routing else dict(first=dict(path='a.txt',content='hello'),rest=[]))
        return dict(decision=dict(index=0),same_engine_session=True,finish_reason='stop',classification_control_records=1,
                    call=dict(name='plan',arguments=arguments))
    monkeypatch.setattr(b,'infer',infer)
    actual=b.chat(dict(cwd=str(project),inner_tools=tools,context=dict(messages=[dict(role='user',content='Write hello')],tools=[{'name':'plan'}])))
    assert actual['call']==dict(name='plan',arguments=dict(steps=[dict(name='write',arguments=dict(path='a.txt',content='hello'))]))
    assert actual['generic_plan'] and not actual['cache_hit']


def test_generic_completion_learns_text_and_reuse_does_not_duplicate(project):
    steps=[dict(name='write',arguments=dict(path='a.md',content='# Heading\n'))]
    (project/'a.md').write_text('# Heading\n')
    first=b.complete_tool_plan(dict(cwd=str(project),steps=steps,task='create markdown'))
    assert len(first['admitted'])==1
    second=b.complete_tool_plan(dict(cwd=str(project),steps=steps,task='create same markdown elsewhere',reused_content_ids=first['admitted']))
    assert second['admitted']==[] and second['cache_hit']
    book=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3')
    entry,=book.load()
    assert entry['reuse_count']==1 and 'semantic_correctness_unverified' in entry['verification']


def test_completion_admits_final_bytes_and_does_not_reward_overwritten_reuse(project):
    book=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3')
    old=book.admit([('write text', 'old', 'execution')])
    (project/'a.txt').write_bytes(b'final\r\n')
    steps=[dict(name='write',arguments=dict(path='a.txt',content='old')),
           dict(name='bash',arguments=dict(command='a later command rewrites a.txt'))]
    result=b.complete_tool_plan(dict(cwd=str(project),steps=steps,task='write text',reused_content_ids=old))
    entries={e['source']:e for e in book.load()}
    assert not result['cache_hit'] and result['admission_count']==1
    assert entries['old']['reuse_count']==0
    assert 'final\r\n' in entries


@pytest.mark.parametrize('kind', ['missing', 'directory', 'outside', 'binary', 'oversized'])
def test_completion_skips_unavailable_final_content(project, kind):
    target=project/'a.txt'
    if kind=='directory': target.mkdir()
    if kind=='outside':
        outside=project.parent/'external.txt';outside.write_text('outside')
        target.symlink_to(outside)
    if kind=='binary': target.write_bytes(b'\xff')
    if kind=='oversized': target.write_bytes(b'x'*(1024*1024+1))
    result=b.complete_tool_plan(dict(cwd=str(project),task='write text',steps=[
        dict(name='write',arguments=dict(path='a.txt',content='stale'))]))
    assert result['admission_count']==0 and result['book_entries_after']==0


def test_template_admission_requires_final_content_agreement(project, monkeypatch):
    monkeypatch.setenv('PIJIT_PLAN_TEMPLATES','1')
    (project/'a.py').write_text('new=2')
    result=b.complete_tool_plan(dict(cwd=str(project),task='write and compile',steps=[
        dict(name='write',arguments=dict(path='a.py',content='old=1')),
        dict(name='bash',arguments=dict(command='python3 -m py_compile a.py'))]))
    assert result['admission_count']==1 and result['template_admitted']==[]


def test_native_edit_recovery_learns_final_content(project):
    import shutil
    import subprocess
    cli=shutil.which('pi')
    if not cli:
        pytest.skip('Pi integration requires pinned Pi in PATH')
    package=Path(cli).resolve().parents[2]
    assert json.loads((package/'package.json').read_text())['version']=='0.85.1'
    executor=(Path(__file__).resolve().parents[1]/'integrations/pijit/plan_executor.mjs').as_uri()
    steps=[dict(name='edit',arguments=dict(path='result.txt',edits=[dict(oldText='broken',newText='fixed')])),
           dict(name='bash',arguments=dict(command="test \"$(cat result.txt)\" = fixed"))]
    script='''
import assert from 'node:assert/strict';
import {createWriteTool,createEditTool,createBashTool} from PI;
import {executePlan} from EXECUTOR;
const tools=new Map([createWriteTool,createEditTool,createBashTool].map(f=>{const t=f(CWD);return [t.name,t]}));
await assert.rejects(executePlan('initial',[
 {name:'write',arguments:{path:'result.txt',content:'broken'}},
 {name:'bash',arguments:{command:'exit 1'}}],tools));
await executePlan('repair',STEPS,tools);
'''.replace('PI',json.dumps((package/'dist/index.js').as_uri())).replace('EXECUTOR',json.dumps(executor)).replace('CWD',json.dumps(str(project))).replace('STEPS',json.dumps(steps))
    run=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stderr
    result=b.complete_tool_plan(dict(cwd=str(project),task='create a fixed result',steps=steps))
    assert result['admission_count']==1 and result['admission_reason']=='new_edit_content'
    book=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3')
    entry,=book.load()
    assert entry['source']=='fixed' and 'semantic_correctness_unverified' in entry['verification']


def test_completion_does_not_learn_files_only_read(project):
    result=b.complete_tool_plan(dict(cwd=str(project),task='read app.py',steps=[
        dict(name='read',arguments=dict(path='app.py'))]))
    assert result['admission_count']==0 and result['book_entries_after']==0


def test_completion_edit_then_delete_does_not_learn_stale_patch(project):
    result=b.complete_tool_plan(dict(cwd=str(project),task='edit and delete',steps=[
        dict(name='edit',arguments=dict(path='deleted.txt',edits=[dict(oldText='old',newText='new')])),
        dict(name='bash',arguments=dict(command='rm deleted.txt'))]))
    assert result['admission_count']==0 and result['admission_reason']=='no_eligible_final_content'


def test_duplicate_guard_scoped_to_current_user_turn_and_success():
    call=dict(name='plan',arguments=dict(steps=[dict(name='write',arguments=dict(path='a',content='ok'))]))
    history=[dict(role='user'),dict(role='assistant',content=[dict(type='toolCall',id='x',**call)]),
             dict(role='toolResult',toolCallId='x',isError=False)]
    with pytest.raises(ValueError,match='Duplicate'):
        b.reject_repeated_plan(call,history)
    b.reject_repeated_plan(call,history+[dict(role='user')])
    history[-1]['isError']=True
    b.reject_repeated_plan(call,history)


def test_generic_logs_explain_empty_book_and_admission(project, monkeypatch):
    monkeypatch.setenv('PIJIT_TOOL_PLAN','1')
    monkeypatch.setenv('PIJIT_PLAN_ONLY','1')
    tools=[dict(name='write',description='write',parameters=dict(type='object',properties={
        'path':dict(type='string'),'content':dict(type='string')},required=['path','content']))]
    monkeypatch.setattr(b,'infer',lambda *a,**k:dict(decision=dict(index=0),same_engine_session=True,
        finish_reason='stop',classification_control_records=1,call=dict(name='plan',arguments=dict(first=dict(path='a',content='hi'),rest=[]))))
    result=b.run(dict(action='chat',cwd=str(project),inner_tools=tools,context=dict(messages=[dict(role='user',content='write hi')],tools=[{'name':'plan'}])))
    assert result['status']=='ok'
    assert result['book_entries']==0 and result['candidate_count']==0
    assert result['cache_outcome']=='empty_book' and result['selected_branch']=='tool:write'
    (project/'a').write_text('hi')
    complete=b.run(dict(action='tool_plan_complete',cwd=str(project),task='write hi',steps=result['call']['arguments']['steps']))
    assert complete['admission_count']==1 and complete['book_entries_after']==1
    assert complete['admission_reason']=='new_write_content'


def test_plan_budget_capabilities_distinguish_old_server_and_transport_failure(monkeypatch):
    import io
    import urllib.error
    monkeypatch.setenv('PIJIT_URL','http://unused')
    monkeypatch.setattr(b.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(dict(
        plan_budget_version=1,per_tool_limit=2048,max_steps=8,max_plan_tokens=17408)).encode()))
    assert b.server_plan_budget()
    def missing(*a,**k):raise urllib.error.HTTPError('http://unused',404,'missing',{},io.BytesIO())
    monkeypatch.setattr(b.urllib.request,'urlopen',missing)
    assert not b.server_plan_budget()
    def denied(*a,**k):raise urllib.error.HTTPError('http://unused',401,'denied',{},io.BytesIO())
    monkeypatch.setattr(b.urllib.request,'urlopen',denied)
    with pytest.raises(urllib.error.HTTPError):b.server_plan_budget()


def test_prefix_cache_requires_capability_and_isolates_sessions_and_workspaces(project, monkeypatch):
    monkeypatch.setenv('PIJIT_PREFIX_CACHE','1')
    monkeypatch.setenv('PIJIT_URL','http://test')
    trace=dict(prefix_cache_supported=True,session_id='session-a',workspace_id='workspace-a')
    token=b.TRACE.set(trace)
    try:
        first=b.session_cache_options()
        assert first==b.session_cache_options() and len(first['cache_salt'])==64
        trace['session_id']='session-b'
        assert b.session_cache_options()!=first
        trace['session_id']='session-a';trace['workspace_id']='workspace-b'
        assert b.session_cache_options()!=first
        trace['workspace_id']='workspace-a';trace['prefix_cache_supported']=False
        assert b.session_cache_options()=={}
        trace['prefix_cache_supported']=True;trace['session_id']=None
        assert b.session_cache_options()=={}
    finally:
        b.TRACE.reset(token)


def test_rejected_subtool_budget_preserves_usage(monkeypatch):
    import io
    import urllib.error
    monkeypatch.setenv('PIJIT_URL','http://unused')
    data=dict(decision={'index':0},generated_argument_tokens=3000,classification_control_records=1,
              plan_budget={'exceeded_steps':[0]},usage_complete=True)
    def failed(*a,**k):raise urllib.error.HTTPError('http://unused',422,'budget',{},io.BytesIO(json.dumps(data).encode()))
    monkeypatch.setattr(b.urllib.request,'urlopen',failed)
    trace={'http_requests':[]};token=b.TRACE.set(trace)
    try:
        with pytest.raises(urllib.error.HTTPError):
            b.post('/v1/openjev/toolcall',dict(prompt_ids=[1,2],continuations=[[3]]))
    finally:b.TRACE.reset(token)
    record,=trace['http_requests']
    assert record['usage_complete'] and record['input_tokens']==3
    assert record['generated_argument_tokens']==3000 and record['classification_control_records']==1
    assert trace['plan_token_budget']['exceeded_steps']==[0]


def test_opt_in_template_learning_and_replay_do_not_duplicate_content(project, monkeypatch):
    monkeypatch.setenv('PIJIT_PLAN_TEMPLATES','1')
    steps=[dict(name='write',arguments=dict(path='x.py',content='x=1')),
           dict(name='bash',arguments=dict(command='python3 -m py_compile x.py'))]
    (project/'x.py').write_text('x=1')
    first=b.complete_tool_plan(dict(cwd=str(project),steps=steps,task='write and compile'))
    assert len(first['template_admitted'])==1 and len(first['admitted'])==1
    second=b.complete_tool_plan(dict(cwd=str(project),steps=steps,task='same at new path',reused_template_ids=first['template_admitted']))
    assert second['cache_hit'] and not second['admitted'] and not second['template_admitted']
    template,=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-templates.sqlite3').load()
    assert template['reuse_count']==1


@pytest.mark.parametrize('reply,override,expected', [(False,None,False),(True,None,True),(True,'0',False),(False,'1',True)])
def test_completion_recovery_default_respects_explicit_override(project,monkeypatch,reply,override,expected):
    monkeypatch.setenv('PIJIT_PLAN_SUCCESS_REPLY','1' if reply else '0')
    monkeypatch.delenv('PIJIT_RECOVERY_LATEST',raising=False)
    if override is not None:monkeypatch.setenv('PIJIT_RECOVERY_LATEST',override)
    tools=[dict(name='bash',description='command',parameters=b.tool_plan.obj(dict(command=dict(type='string'))))]
    captured=[]
    def infer(messages,options,**kwargs):
        captured.append(len(options))
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='fixture')))
    monkeypatch.setattr(b,'infer',infer)
    b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,context=dict(messages=[
        dict(role='user',content='repair'),dict(role='toolResult',isError=True,content='failed'),
        dict(role='toolResult',isError=False,content='latest success')])))
    assert captured==[2 if expected else 1]


@pytest.mark.parametrize('latest', [False, True])
def test_forced_recovery_skips_unused_candidate_retrieval(project, monkeypatch, latest):
    monkeypatch.setenv('PIJIT_PLAN_TEMPLATES','1')
    monkeypatch.setenv('PIJIT_PLAN_DISABLE_REUSE','0')
    monkeypatch.setenv('PIJIT_RECOVERY_LATEST','1' if latest else '0')
    queries=[]
    monkeypatch.setattr(b.tool_plan.ToolContentBook,'candidates',lambda *a,**kw: queries.append(kw) or [])
    tools=[dict(name='write',description='write',parameters=b.tool_plan.obj(dict(
        path=dict(type='string'),content=dict(type='string'))))]
    def infer(messages,options,**kwargs):
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='fixture')))
    monkeypatch.setattr(b,'infer',infer)
    messages=[dict(role='user',content='repair'),dict(role='toolResult',content='failed',isError=True)]
    payload=dict(cwd=str(project),inner_tools=tools,context=dict(messages=messages))
    b.generic_plan_chat(payload)
    assert not queries
    messages.append(dict(role='toolResult',content='success',isError=False))
    b.generic_plan_chat(payload)
    assert len(queries)==(2 if latest else 0)
    queries.clear()
    messages.append(dict(role='user',content='new request'))
    b.generic_plan_chat(payload)
    assert len(queries)==2


def test_generic_failure_replans_without_fixed_first_tool_and_resets_on_new_user(project, monkeypatch):
    tools=[dict(name='bash',description='command',parameters=b.tool_plan.obj(dict(command=dict(type='string'))))]
    captured=[]
    def infer(messages, options, **kwargs):
        captured.append((options, kwargs['branch_instruction'](0,options[0])))
        return dict(decision=dict(index=len(options)-1), same_engine_session=True, finish_reason='stop',
                    classification_control_records=1, call=dict(name='plan',arguments=dict(content='Need clarification.')))
    monkeypatch.setattr(b,'infer',infer)
    messages=[dict(role='user',content='Fix the failure'),dict(role='toolResult',content='AssertionError',isError=True),
              dict(role='toolResult',content='Read completed',isError=False)]
    payload=dict(cwd=str(project),inner_tools=tools,context=dict(messages=messages))
    assert b.generic_plan_chat(payload)['call']['name']=='reply_user'
    assert len(captured[-1][0])==1
    assert 'Selected FIRST action' not in captured[-1][1]
    assert 'actual native tool calls' in captured[-1][1]
    messages.append(dict(role='user',content='A new task'))
    b.generic_plan_chat(payload)
    assert len(captured[-1][0])==2


def test_latest_recovery_restores_classification_without_erasing_unresolved_failures(project, monkeypatch):
    monkeypatch.setenv('PIJIT_RECOVERY_LATEST','1')
    tools=[dict(name='bash',description='command',parameters=b.tool_plan.obj(dict(command=dict(type='string'))))]
    captured=[]
    def infer(messages, options, **kwargs):
        captured.append((messages,options,kwargs['branch_instruction'](0,options[0])))
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='fixture')))
    monkeypatch.setattr(b,'infer',infer)
    messages=[dict(role='user',content='Fix'),dict(role='toolResult',content='AssertionError',isError=True)]
    payload=dict(cwd=str(project),inner_tools=tools,context=dict(messages=messages))
    b.generic_plan_chat(payload)
    assert len(captured[-1][1])==1
    messages.append(dict(role='toolResult',content='Read completed',isError=False))
    b.generic_plan_chat(payload)
    history,options,instruction=captured[-1]
    assert len(options)==2 and 'does not resolve a failed check' in instruction
    assert 'AssertionError' in str(history)
    messages.append(dict(role='toolResult',content='Another failure',isError=True))
    b.generic_plan_chat(payload)
    assert len(captured[-1][1])==1
    messages.append(dict(role='user',content='New task'))
    b.generic_plan_chat(payload)
    assert len(captured[-1][1])==2 and 'An earlier operation failed' not in captured[-1][2]


def test_validation_error_preserves_details_without_fake_provider_status(project, monkeypatch):
    from jsonschema import validate
    def invalid(_payload):
        validate([],dict(type='array',minItems=1,description='Read up to 500 lines'))
    monkeypatch.setattr(b,'chat',invalid)
    result=b.run(dict(action='chat',cwd=str(project)))
    assert result['status']=='error' and result['error']=='ValidationError: tool arguments failed minItems validation'
    assert result['validation_error']==dict(rule='minItems',path=[],message='[] should be non-empty',instance=[])
    assert '500' not in result['error']
    import urllib.error
    assert '500' in b.public_error(urllib.error.HTTPError('http://unused',500,'server error',{},None))


def test_failed_plan_loop_is_bounded_without_blocking_one_retry_or_changed_actions():
    call=dict(name='plan',arguments=dict(steps=[dict(name='bash',arguments=dict(command='python3 check.py'))]))
    history=[dict(role='user',content='Check')]
    def attempt(identity, arguments, error=True):
        history.extend([dict(role='assistant',content=[dict(type='toolCall',name='plan',id=identity,arguments=arguments)]),
                        dict(role='toolResult',toolCallId=identity,isError=error)])
    attempt('1',call['arguments'])
    b.reject_repeated_plan(call,history)
    attempt('2',call['arguments'])
    with pytest.raises(ValueError,match='task remains incomplete'):
        b.reject_repeated_plan(call,history)
    changed=dict(name='plan',arguments=dict(steps=[dict(name='bash',arguments=dict(command='python3 other.py'))]))
    b.reject_repeated_plan(changed,history)
    attempt('3',changed['arguments'],False)
    b.reject_repeated_plan(call,history)
    attempt('4',call['arguments']);attempt('5',call['arguments'])
    b.reject_repeated_plan(call,history+[dict(role='user',content='Try again')])


def test_latest_execution_error_is_readable_scoped_and_preserves_actual_output():
    failed=dict(name='bash',arguments=dict(command='python3 check.py'))
    error='line 3\nAssertionError: expected [1], got [1, 2]'
    messages=[dict(role='user',content='Fix'),dict(role='assistant',content=[dict(type='toolCall',id='p',name='plan',arguments=dict(steps=[failed]))]),
              dict(role='toolResult',toolCallId='p',isError=True,content=json.dumps(dict(failed_step=0,error=error)))]
    state=b.latest_plan_result(messages)
    assert error in state and 'python3 check.py' in state and 'remain applied' in state
    assert b.latest_plan_result(messages+[dict(role='user',content='New')])==''
    after_read=b.latest_plan_result(messages+[dict(role='toolResult',content='ok',isError=False)])
    assert 'SUCCEEDED' in after_read and 'LATEST EXECUTION FAILED' not in after_read
    assert error in b.plan_history(messages)[-1]['content'].replace('\\n','\n')
    assert 'FAILED' in b.latest_plan_result([dict(role='toolResult',content='malformed',isError=True)])


def test_tool_argument_schemas_are_deferred_without_losing_generation_constraints(project, monkeypatch):
    tools=[dict(name='bash',description='Run a command',parameters=b.tool_plan.obj(dict(
        command=dict(type='string',description='UNIQUE_ARGUMENT_DESCRIPTION'))))]
    def infer(messages, options, **kwargs):
        assert 'UNIQUE_ARGUMENT_DESCRIPTION' not in messages[0]['content']
        assert 'Run a command' in messages[0]['content']
        for index,option in enumerate(options):
            assert 'UNIQUE_ARGUMENT_DESCRIPTION' in kwargs['branch_instruction'](index,option)
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='Need input')))
    monkeypatch.setattr(b,'infer',infer)
    b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,context=dict(messages=[dict(role='user',content='Help')])) )


def test_plan_history_preserves_native_tool_protocol_and_error_evidence():
    messages=[dict(role='user',content='Read'),dict(role='assistant',content=[dict(type='text',text='Checking'),
        dict(type='toolCall',id='p1',name='plan',arguments=dict(steps=[dict(name='read',arguments=dict(path='中文.txt'))]))]),
        dict(role='toolResult',toolCallId='p1',toolName='plan',isError=True,content=[dict(type='text',text='missing file')])]
    before=json.dumps(messages)
    converted=b.plan_history(messages)
    assert [m['role'] for m in converted]==['user','assistant','tool']
    assert converted[1]['content']=='Checking'
    call=converted[1]['tool_calls'][0]
    assert call['id']=='p1' and call['function']['name']=='plan'
    assert json.loads(call['function']['arguments'])==messages[1]['content'][1]['arguments']
    assert converted[2]['tool_call_id']=='p1' and 'error=True' in converted[2]['content']
    assert 'missing file' in converted[2]['content']
    assert json.dumps(messages)==before


def test_codebook_admission_metadata_does_not_masquerade_as_failed_task_validation():
    nested=dict(content=[dict(type='text',text='{"learning": "actual file contents"}')])
    payload=dict(results=[dict(name='read',result=nested)],learning=dict(validation='semantic_correctness_unverified',admitted=['id']))
    message=dict(role='toolResult',toolCallId='p',toolName='plan',isError=False,content=json.dumps(payload))
    converted=b.plan_history([message])[0]['content']
    parsed=json.loads(converted.split('\n',1)[1])
    assert parsed==dict(results=payload['results'])
    assert json.loads(message['content'])==payload
    assert 'semantic_correctness_unverified' not in converted
    message['toolName']='read'
    assert 'semantic_correctness_unverified' in b.plan_history([message])[0]['content']


def test_reuse_routing_maps_wire_label_to_content_entry(project, monkeypatch):
    monkeypatch.setenv('PIJIT_TOOL_PLAN', '1')
    monkeypatch.setenv('PIJIT_REUSE_ROUTING', '1')
    (project/'old.txt').write_text('hello')
    b.complete_tool_plan(dict(cwd=str(project), task='create greeting',
        steps=[dict(name='write', arguments=dict(path='old.txt', content='hello'))]))
    tools=[dict(name='write', description='write file', parameters=dict(type='object',
        properties={'path':dict(type='string'),'content':dict(type='string')},required=['path','content']))]
    def infer(messages, options, **kwargs):
        assert len(options) == 2
        assert 'Selected Candidate 0; observed files: ["old.txt"]' in kwargs['branch_instruction'](0, options[0])
        return dict(decision=dict(index=0), same_engine_session=True, finish_reason='stop',
            classification_control_records=1, call=dict(name='plan', arguments=dict(steps=[
                dict(name='reuse_write', arguments=dict(path='new.txt'))])))
    monkeypatch.setattr(b, 'infer', infer)
    result=b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,
        context=dict(messages=[dict(role='user',content='create greeting')])) )
    assert result['call']['arguments']['steps'] == [dict(name='write', arguments=dict(path='new.txt',content='hello'))]
    assert result['cache_hit'] and len(result['reused_content_ids']) == 1
    assert result['decision']['index'] == 0


@pytest.mark.parametrize('template', [False, True])
@pytest.mark.parametrize('matching', [False, True])
def test_generic_payload_filter_refills_shortlist(project, monkeypatch, template, matching):
    monkeypatch.setenv('PIJIT_PLAN_TEMPLATES', '1' if template else '0')
    monkeypatch.setenv('PIJIT_PLAN_DISABLE_REUSE', '0')
    monkeypatch.setenv('PIJIT_COMPACT_CATALOG', '1')
    monkeypatch.setenv('PIJIT_REUSE_ROUTING', '0')
    filename = 'tool-plan-templates.sqlite3' if template else 'tool-plan-codebook.sqlite3'
    book = b.tool_plan.ToolContentBook(b.paths(str(project))/filename)
    def stored(content):
        return json.dumps(dict(version=1, content=content)) if template else content
    rows = [('write file variant 000', stored('wanted\n'), 'execution')] if matching else []
    rows += [(f'write file variant {i:03}', stored(f'wrong {i}\n'), 'execution') for i in range(1, 21)]
    book.admit(rows)
    tools = [dict(name='write', description='write', parameters=b.tool_plan.obj(dict(
        path=dict(type='string'), content=dict(type='string')))),
        dict(name='bash', description='command', parameters=b.tool_plan.obj(dict(command=dict(type='string'))))]
    def infer(messages, options, **kwargs):
        assert len(options) == len(tools)+1+int(matching)
        if matching:
            arguments = dict(steps=[dict(name='reuse_plan' if template else 'reuse_write',
                                         arguments=dict(path='new.py'))])
            index = len(tools)
        else:
            arguments, index = dict(content='No reusable literal'), len(options)-1
        return dict(decision=dict(index=index), same_engine_session=True, finish_reason='stop',
                    classification_control_records=1, call=dict(name='plan', arguments=arguments))
    monkeypatch.setattr(b, 'infer', infer)
    trace = {'stage_seconds': {}}; token = b.TRACE.set(trace)
    try:
        result = b.generic_plan_chat(dict(cwd=str(project), inner_tools=tools,
            context=dict(messages=[dict(role='user', content='write file\n```text\nwanted\n```')])) )
    finally:
        b.TRACE.reset(token)
    assert trace['payload_mismatch_candidates'] == 20
    assert trace['candidate_count'] == int(matching)
    if matching:
        assert result['call']['arguments']['steps'][0]['arguments']['content'] == 'wanted\n'
        assert result['cache_hit']
    else:
        assert result['call']['name'] == 'reply_user'


def test_generic_reuse_disabled_keeps_learning_without_content_candidates(project, monkeypatch):
    monkeypatch.setenv('PIJIT_PLAN_DISABLE_REUSE', '1')
    monkeypatch.setenv('PIJIT_PLAN_TEMPLATES', '1')
    monkeypatch.setattr(b, 'server_plan_budget', lambda: True)
    (project/'old.txt').write_text('hello')
    learned=b.complete_tool_plan(dict(cwd=str(project), task='create greeting',
        steps=[dict(name='write', arguments=dict(path='old.txt',content='hello'))]))
    assert learned['admission_count'] == 1
    monkeypatch.setattr(b.tool_plan.ToolContentBook, 'candidates',
        lambda self, task, contracts, limit: [] if limit==0 else pytest.fail('reuse retrieval enabled'))
    tools=[dict(name='write', description='write file', parameters=dict(type='object',
        properties={'path':dict(type='string'),'content':dict(type='string')},required=['path','content']))]
    def infer(messages, options, **kwargs):
        assert len(options)==2
        assert 'HISTORICAL BEHAVIOR CONTRACT' not in messages[0]['content']
        return dict(decision=dict(index=0),same_engine_session=True,finish_reason='stop',
            classification_control_records=1,call=dict(name='plan',arguments=dict(
                first=dict(path='new.txt',content='hello again'),rest=[])))
    monkeypatch.setattr(b, 'infer', infer)
    result=b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,
        context=dict(messages=[dict(role='user',content='create greeting')])) )
    assert not result['cache_hit'] and result['reused_content_ids']==[]
    (project/'new.txt').write_text('hello again')
    learned=b.complete_tool_plan(dict(cwd=str(project),task='create greeting again',
        steps=result['call']['arguments']['steps']))
    assert learned['admission_count']==1 and learned['book_entries_after']==2


@pytest.mark.parametrize('reply', ['Created hello.txt.', '', None])
def test_generic_success_reply_stays_outside_executable_plan(project, monkeypatch, reply):
    monkeypatch.setenv('PIJIT_PLAN_SUCCESS_REPLY', '1')
    monkeypatch.setenv('PIJIT_PLAN_DISABLE_REUSE', '1')
    tools=[dict(name='write',description='write',parameters=b.tool_plan.obj(dict(
        path=dict(type='string'),content=dict(type='string'))))]
    def infer(messages, options, **kwargs):
        assert 'withheld until execution succeeds' in messages[0]['content']
        assert 'on_success_reply' in str(options[0]['parameters'])
        rest=[] if reply is None else [dict(name='on_success_reply',arguments=dict(content=reply))]
        return dict(decision=dict(index=0),same_engine_session=True,finish_reason='stop',
            classification_control_records=1,call=dict(name='plan',arguments=dict(
                first=dict(path='hello.txt',content='hello'),rest=rest)))
    monkeypatch.setattr(b,'infer',infer)
    payload=dict(cwd=str(project),inner_tools=tools,
        context=dict(messages=[dict(role='user',content='Write hello.txt')]))
    result=b.generic_plan_chat(payload)
    assert result['on_success_reply']==reply
    assert set(result['call']['arguments'])=={'steps'}


@pytest.mark.parametrize('disabled', ['0', '1'])
def test_plan_launcher_preserves_explicit_reuse_setting(tmp_path, disabled):
    import os
    import shutil
    import subprocess
    node=shutil.which('node')
    if not node:
        pytest.skip('Pi launcher requires Node.js')
    package=tmp_path/'fake-pi'
    cli=package/'dist/bundle/cli.mjs'
    cli.parent.mkdir(parents=True)
    cli.write_text('console.log(JSON.stringify({disabled:process.env.PIJIT_PLAN_DISABLE_REUSE,plan:process.env.PIJIT_TOOL_PLAN}));')
    (package/'package.json').write_text('{"version":"0.85.1"}')
    bindir=tmp_path/'bin';bindir.mkdir()
    (bindir/'pi').symlink_to(cli)
    cli.chmod(0o755)
    env=dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'],
             PIJIT_PLAN_DISABLE_REUSE=disabled, PIJIT_STATE_DIR=str(tmp_path/'state'),
             PIJIT_URL='http://127.0.0.1:1')
    script=Path(__file__).resolve().parents[1]/'integrations/pijit/launch.mjs'
    result=subprocess.run([node,str(script),'--plan-only','--version'],env=env,
                          capture_output=True,text=True,timeout=5)
    assert result.returncode==0, result.stderr
    assert json.loads(result.stdout)=={'disabled':disabled,'plan':'1'}


def recovery_admission_history():
    write=dict(name='write',arguments=dict(path='recovered.txt',content='stale initial bytes'))
    check=dict(name='bash',arguments=dict(command='check'))
    def pair(identity, steps, failed=False):
        result=dict(completed=[dict(name='write')],failed_step=1) if failed else dict(results=[dict(name=s['name']) for s in steps])
        return [dict(role='assistant',content=[dict(type='toolCall',name='plan',id=identity,arguments=dict(steps=steps))]),
                dict(role='toolResult',toolName='plan',toolCallId=identity,isError=failed,
                     content=[dict(type='text',text=json.dumps(result))])]
    return [dict(role='user',content='create file'),*pair('failed',[write,check],True),*pair('recovered',[check])]


def test_recovery_admission_reads_current_file_without_template_or_reuse_credit(project,monkeypatch):
    monkeypatch.setenv('PIJIT_PLAN_TEMPLATES','1')
    (project/'recovered.txt').write_text('actual final bytes')
    result=b.admit_recovered_mutations(dict(cwd=str(project),context=dict(messages=recovery_admission_history())), 'create file')
    assert result['admission_count']==1 and not result['cache_hit'] and result['template_admitted']==[]
    entry,=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3').load()
    assert entry['source']=='actual final bytes'
    assert 'semantic_correctness_unverified' in entry['verification']


@pytest.mark.parametrize('change',['new_user','still_failed','read_only','mismatched_results','unknown_call','missing_completion','unexecuted_write','pending_call'])
def test_recovery_admission_rejects_unconfirmed_or_cross_task_mutations(change):
    messages=recovery_admission_history()
    if change=='new_user':messages.append(dict(role='user',content='another task'))
    if change=='still_failed':messages=messages[:-2]
    if change=='read_only':
        messages[-2]['content'][0]['arguments']['steps']=[dict(name='read',arguments=dict(path='recovered.txt'))]
        messages[-1]['content'][0]['text']=json.dumps(dict(results=[dict(name='read')]))
    if change=='mismatched_results':messages[2]['content'][0]['text']=json.dumps(dict(completed=[dict(name='bash')],failed_step=1))
    if change=='pending_call':messages.append(dict(role='assistant',content=[dict(type='toolCall',name='plan',id='pending',arguments=dict(steps=[dict(name='bash',arguments=dict(command='check'))]))]))
    if change=='unknown_call':messages[-1]['toolCallId']='other'
    if change=='missing_completion':messages[2]['content'][0]['text']='{}'
    if change=='unexecuted_write':
        messages[1]['content'][0]['arguments']['steps'].reverse()
        messages[2]['content'][0]['text']=json.dumps(dict(completed=[],failed_step=0))
    assert b.recovered_mutation_steps(messages)==[]


def test_recovery_admission_excludes_paths_already_written_by_successful_repair():
    messages=recovery_admission_history()
    write=dict(name='write',arguments=dict(path='recovered.txt',content='fixed'))
    messages[-2]['content'][0]['arguments']['steps'].insert(0,write)
    messages[-1]['content'][0]['text']=json.dumps(dict(results=[dict(name='write'),dict(name='bash')]))
    assert b.recovered_mutation_steps(messages)==[]


@pytest.mark.parametrize('enabled',[False,True])
def test_recovery_admission_runs_only_at_opt_in_final_reply_with_no_extra_inference(project,monkeypatch,enabled):
    monkeypatch.setenv('PIJIT_RECOVERY_ADMISSION','1' if enabled else '0')
    (project/'recovered.txt').write_text('final bytes')
    calls=[]
    def infer(messages,options,**kwargs):
        calls.append(1)
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='Done.')))
    monkeypatch.setattr(b,'infer',infer)
    tools=[dict(name='bash',description='command',parameters=b.tool_plan.obj(dict(command=dict(type='string'))))]
    result=b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,context=dict(messages=recovery_admission_history())))
    assert calls==[1] and result['call']['name']=='reply_user'
    assert result.get('admission_count',0)==int(enabled)
    assert b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3').count()==int(enabled)


def test_native_failed_plan_then_successful_check_can_be_admitted_at_close(project):
    import shutil
    import subprocess
    cli=shutil.which('pi')
    if not cli:pytest.skip('Pi integration requires pinned Pi in PATH')
    package=Path(cli).resolve().parents[2]
    assert json.loads((package/'package.json').read_text())['version']=='0.85.1'
    executor=(Path(__file__).resolve().parents[1]/'integrations/pijit/plan_executor.mjs').as_uri()
    script='''
import assert from 'node:assert/strict';
import {createWriteTool,createBashTool} from PI;
import {executePlan} from EXECUTOR;
const tools=new Map([createWriteTool,createBashTool].map(f=>{const t=f(CWD);return [t.name,t]}));
const messages=[{role:'user',content:'create file and check'}];
for(const [id,steps] of [
 ['failed',[{name:'write',arguments:{path:'recovered.txt',content:'final bytes'}},{name:'bash',arguments:{command:'exit 1'}}]],
 ['recovered',[{name:'bash',arguments:{command:'test "$(cat recovered.txt)" = "final bytes"'}}]]]) {
 messages.push({role:'assistant',content:[{type:'toolCall',id,name:'plan',arguments:{steps}}]});
 let result,isError=false;
 try {result={results:await executePlan(id,steps,tools)}} catch(error){isError=true;result=JSON.parse(error.message)}
 messages.push({role:'toolResult',toolName:'plan',toolCallId:id,isError,content:[{type:'text',text:JSON.stringify(result)}]});
}
assert.equal(messages[2].isError,true);assert.equal(messages[4].isError,false);
process.stdout.write(JSON.stringify(messages));
'''.replace('PI',json.dumps((package/'dist/index.js').as_uri())).replace('EXECUTOR',json.dumps(executor)).replace('CWD',json.dumps(str(project)))
    run=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stderr
    result=b.admit_recovered_mutations(dict(cwd=str(project),context=dict(messages=json.loads(run.stdout))), 'create file and check')
    assert result['admission_count']==1
    entry,=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3').load()
    assert entry['source']=='final bytes'


def test_content_admission_keeps_implementation_and_helper_paths_separate(project):
    files={'module.js':'export const x = 1;', 'test_module.js':"import {x} from './module.js';"}
    for name,content in files.items():(project/name).write_text(content)
    result=b.complete_tool_plan(dict(cwd=str(project),task='Implement x',steps=[
        dict(name='write',arguments=dict(path=name,content=content)) for name,content in files.items()]))
    assert result['admission_count']==2
    entries=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3').load()
    assert {e['source']:b.tool_plan.observed_paths(e) for e in entries}=={content:[name] for name,content in files.items()}
    assert all(e['contract']=='Implement x' for e in entries)


def test_identical_content_collects_paths_without_duplicate_admission(project):
    for name in ['a.txt','b.txt']:(project/name).write_text('shared')
    result=b.complete_tool_plan(dict(cwd=str(project),task='write files',steps=[
        dict(name='write',arguments=dict(path=str(project/name),content='shared')) for name in ['a.txt','b.txt']]))
    assert result['admission_count']==1
    entry,=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3').load()
    assert b.tool_plan.observed_paths(entry)==['a.txt','b.txt']


def test_native_pi_bash_accepts_decoded_literal_arguments(project):
    import shutil
    import subprocess
    import sys
    cli=shutil.which('pi')
    if not cli:pytest.skip('Pi integration requires pinned Pi in PATH')
    package=Path(cli).resolve().parents[2]
    assert json.loads((package/'package.json').read_text())['version']=='0.85.1'
    tools=[dict(name='bash',description='shell',parameters=b.tool_plan.obj(dict(command=dict(type='string'))))]
    literals=['a\'b"c','$(printf unintended)','', 'space value','line\nbreak']
    argv=[sys.executable,'-c','import json,sys; print(json.dumps(sys.argv[1:]))',*literals]
    response=dict(decision=dict(index=0),call=dict(name='plan',arguments=dict(first=dict(command=argv),rest=[])),
                  same_engine_session=True,finish_reason='stop',classification_control_records=1)
    call,_=b.tool_plan.decode(response,tools,[],b.tool_plan.branches(tools,[],bash_argv=True))
    script='''
import assert from 'node:assert/strict';
import {createBashTool} from PI;
const result=await createBashTool(CWD).execute('literal-check',ARGS);
assert.deepEqual(JSON.parse(result.content[0].text),EXPECTED);
'''.replace('PI',json.dumps((package/'dist/index.js').as_uri())).replace('CWD',json.dumps(str(project))).replace('ARGS',json.dumps(call['arguments']['steps'][0]['arguments'])).replace('EXPECTED',json.dumps(literals))
    run=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stderr


@pytest.mark.parametrize('supported', [True, False])
def test_capability_negotiation_overlaps_preparation_before_inference(monkeypatch, supported):
    from threading import Event
    preparing, negotiating = Event(), Event()
    monkeypatch.delenv('PIJIT_SERIAL_PREPARATION', raising=False)
    monkeypatch.delenv('PIJIT_PREFIX_CACHE', raising=False)
    def prepare(messages, tails):
        preparing.set()
        assert negotiating.wait(3), 'Capability probe was serialized behind tokenization'
        return [1], [[2]]
    def negotiate():
        negotiating.set()
        assert preparing.wait(3), 'Tokenization was serialized behind capability probe'
        b.trace_update(prefix_cache_supported=True)
        return supported
    sent=[]
    def post(route,payload):
        assert preparing.is_set() and negotiating.is_set()
        sent.append(payload)
        return dict(decision=dict(index=0))
    monkeypatch.setattr(b,'prepare_continuations',prepare)
    monkeypatch.setattr(b,'labels',lambda n:[3])
    monkeypatch.setattr(b,'post',post)
    trace=dict(stage_seconds={})
    token=b.TRACE.set(trace)
    try:
        b.infer([dict(role='user',content='x')],[dict(name='plan',parameters={})],budget_resolver=negotiate)
    finally:
        b.TRACE.reset(token)
    assert sent[0]['max_tokens']==(b.PLAN_TOTAL_TOKENS if supported else 2048)
    assert sent[0].get('plan_budget',False)==supported
    assert trace['prefix_cache_supported'] is True


def test_parallel_capability_failure_never_sends_inference(monkeypatch):
    monkeypatch.delenv('PIJIT_SERIAL_PREPARATION',raising=False)
    monkeypatch.setattr(b,'prepare_continuations',lambda *a:([1],[[2]]))
    monkeypatch.setattr(b,'labels',lambda n:[3])
    def fail():raise OSError('capabilities unavailable')
    def unexpected(*args):pytest.fail('Inference sent without capability result')
    monkeypatch.setattr(b,'post',unexpected)
    with pytest.raises(OSError,match='capabilities unavailable'):
        b.infer([], [dict(name='plan',parameters={})],budget_resolver=fail)


@pytest.mark.parametrize('routing',[False,True])
@pytest.mark.parametrize('recovery',[False,True])
def test_reply_branch_selection_maps_after_routing_and_preserves_recovery(project,monkeypatch,routing,recovery):
    monkeypatch.setenv('PIJIT_REPLY_BRANCH','1')
    monkeypatch.setenv('PIJIT_REUSE_ROUTING','1' if routing else '0')
    monkeypatch.setenv('PIJIT_PLAN_DISABLE_REUSE','1')
    tools=[dict(name='bash',description='shell',parameters=b.tool_plan.obj(dict(command=dict(type='string'))))]
    captured=[]
    def infer(messages,options,**kwargs):
        index=0 if recovery else len(options)-2
        captured.append(kwargs['branch_instruction'](index,options[index]))
        if not recovery:
            assert 'choose '+b.LABELS[index]+' to reply' in kwargs['classification_prompt']
        return dict(decision=dict(index=index),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='fixture')))
    monkeypatch.setattr(b,'infer',infer)
    history=[dict(role='user',content='hello')]
    if recovery:history.append(dict(role='toolResult',isError=True,content='failure'))
    result=b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,context=dict(messages=history)))
    assert result['call']['name']=='reply_user'
    assert ('Selected reply.' in captured[0]) == (not recovery)


def test_repair_feedback_rejects_replaced_bytes_only_for_same_task(project):
    book=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3')
    old='old implementation';new='corrected implementation';task='implement file'
    identity,=book.admit([(task,old,'execution only')])
    (project/'x.txt').write_text(new)
    history=[dict(role='user',content=task)]
    def result(identity,steps,failed=False):
        count=len(steps)-1 if failed else len(steps)
        output={('completed' if failed else 'results'):[dict(name=s['name']) for s in steps[:count]]}
        if failed:output.update(failed_step=count,error='assertion failed')
        history.extend([dict(role='assistant',content=[dict(type='toolCall',name='plan',id=identity,arguments=dict(steps=steps))]),
                        dict(role='toolResult',toolName='plan',toolCallId=identity,isError=failed,content=json.dumps(output))])
    write=dict(name='write',arguments=dict(path='x.txt',content=old))
    check=dict(name='bash',arguments=dict(command='check'))
    result('first',[write,check],True)
    payload=dict(cwd=str(project),context=dict(messages=history))
    assert b.record_repaired_content(payload,task)==[]
    result('repair',[dict(name='edit',arguments=dict(path=str(project/'x.txt'))),check])
    feedback=b.record_repaired_content(payload,task)
    assert feedback[0]['rejected_ids']==[identity]
    assert book.candidates(task,{},repair_feedback=True)==[]
    assert book.candidates(task,{},repair_feedback=False)
    assert book.candidates(task+' again',{},repair_feedback=True)
    book.admit([(task+' duplicate',old,'execution only')])
    assert book.candidates(task,{},repair_feedback=True)==[]
    assert book.candidates(task+' again',{},repair_feedback=True)


@pytest.mark.parametrize('change_content',[False,True])
def test_repair_feedback_does_not_penalize_check_only_repair(project,change_content):
    task='check content';old='existing content'
    book=b.tool_plan.ToolContentBook(b.paths(str(project))/'tool-plan-codebook.sqlite3')
    book.admit([(task,old,'execution only')])
    (project/'x.txt').write_text('external change' if change_content else old)
    history=[dict(role='user',content=task)]
    for identity,steps,failed in [('a',[dict(name='write',arguments=dict(path='x.txt',content=old)),dict(name='bash',arguments=dict(command='bad check'))],True),('b',[dict(name='bash',arguments=dict(command='fixed check'))],False)]:
        output=dict(completed=[dict(name='write')],failed_step=1,error='bad assertion') if failed else dict(results=[dict(name='bash')])
        history.extend([dict(role='assistant',content=[dict(type='toolCall',name='plan',id=identity,arguments=dict(steps=steps))]),dict(role='toolResult',toolName='plan',toolCallId=identity,isError=failed,content=json.dumps(output))])
    assert b.record_repaired_content(dict(cwd=str(project),context=dict(messages=history)),task)==[]
    assert book.candidates(task,{},repair_feedback=True)


@pytest.mark.parametrize('ending',['new_user','pending_call','read_only','malformed','failed_check'])
def test_repair_feedback_requires_complete_current_turn(project,monkeypatch,ending):
    (project/'x').write_text('new')
    old_step=dict(name='write',arguments=dict(path='x',content='old'))
    edit=dict(name='edit',arguments=dict(path='x'))
    check=dict(name='bash',arguments=dict(command='check'))
    def call(identity,steps):return dict(role='assistant',content=[dict(type='toolCall',name='plan',id=identity,arguments=dict(steps=steps))])
    history=[dict(role='user',content='task'),call('a',[old_step,check]),
        dict(role='toolResult',toolName='plan',toolCallId='a',isError=True,content=json.dumps(dict(completed=[dict(name='write')],failed_step=1,error='failed'))),
        call('b',[edit,check]),dict(role='toolResult',toolName='plan',toolCallId='b',isError=False,content=json.dumps(dict(results=[dict(name='edit'),dict(name='bash')])))]
    if ending=='new_user':history.append(dict(role='user',content='new task'))
    elif ending=='pending_call':history.append(call('pending',[check]))
    else:
        history.append(call('last',[dict(name='read',arguments=dict(path='x'))] if ending=='read_only' else [check]))
        content=json.dumps(dict(results=[dict(name='read')])) if ending=='read_only' else 'invalid result'
        if ending=='failed_check':content=json.dumps(dict(completed=[],failed_step=0,error='failed again'))
        history.append(dict(role='toolResult',toolName='plan',toolCallId='last',isError=ending=='failed_check',content=content))
    def unexpected(*args):pytest.fail('Incomplete evidence must not write rejection records')
    monkeypatch.setattr(b.tool_plan.ToolContentBook,'reject_content',unexpected)
    assert b.record_repaired_content(dict(cwd=str(project),context=dict(messages=history)),'task')==[]


@pytest.mark.parametrize('recovery',[False,True])
@pytest.mark.parametrize('routing',[False,True])
def test_dedup_tool_descriptions_preserves_catalog_mapping_and_schemas(project,monkeypatch,recovery,routing):
    description='Unique fixture description for reading files.'
    tools=[dict(name='read',description=description,parameters=b.tool_plan.obj(dict(path=dict(type='string'))))]
    monkeypatch.setenv('PIJIT_REUSE_ROUTING','1' if routing else '0')
    history=[dict(role='user',content='read a file')]
    if recovery:history.append(dict(role='toolResult',isError=True,content='failed'))
    captured=[]
    def infer(messages,options,**kwargs):
        captured.append((messages,options,[kwargs['branch_instruction'](i,o) for i,o in enumerate(options)],kwargs['classification_prompt']))
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='fixture')))
    monkeypatch.setattr(b,'infer',infer)
    for flag in ['0','1']:
        monkeypatch.setenv('PIJIT_DEDUP_TOOL_DESCRIPTIONS',flag)
        b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,context=dict(messages=history)))
    before,after=captured
    assert before[1:]==after[1:]
    assert before[0][0]['content'].count(description)==(1 if recovery or routing else 2)
    assert after[0][0]['content'].count(description)==1
    if not recovery and not routing:
        assert 'A: First action read. See INNER TOOLS above.' in after[0][0]['content']
    else:
        assert before==after


@pytest.mark.parametrize('candidate',[False,True])
def test_disable_first_tool_classification_preserves_candidate_and_general_decode(project,monkeypatch,candidate):
    monkeypatch.setenv('PIJIT_FIRST_TOOL_CLASSIFICATION','0')
    monkeypatch.setenv('PIJIT_REUSE_ROUTING','0')
    tools=[dict(name='write',description='write',parameters=b.tool_plan.obj(dict(path=dict(type='string'),content=dict(type='string'))))]
    entries=[dict(id='fixture-id',source='hello',contract='Write hello',verification='execution only')] if candidate else []
    monkeypatch.setattr(b.tool_plan.ToolContentBook,'candidates',lambda *a,**kw:entries)
    def infer(messages,options,**kwargs):
        assert len(options)==1+len(entries)
        assert 'CURRENT USER REQUIREMENTS' not in kwargs['classification_prompt']
        assert 'First action write:' not in messages[0]['content']
        args=dict(steps=[dict(name='reuse_write',arguments=dict(path='a.txt'))]) if candidate else dict(steps=[dict(name='write',arguments=dict(path='a.txt',content='hello'))])
        assert ('Selected Candidate 0' if candidate else 'Continue the user task') in kwargs['branch_instruction'](0,options[0])
        return dict(decision=dict(index=0),same_engine_session=True,finish_reason='stop',classification_control_records=1,call=dict(name='plan',arguments=args))
    monkeypatch.setattr(b,'infer',infer)
    result=b.generic_plan_chat(dict(cwd=str(project),inner_tools=tools,context=dict(messages=[dict(role='user',content='Write hello')])))
    assert result['call']==dict(name='plan',arguments=dict(steps=[dict(name='write',arguments=dict(path='a.txt',content='hello'))]))
    assert result['cache_hit']==candidate


def test_engine_length_failure_retains_decision_and_request_identity(monkeypatch):
    import io
    import urllib.error
    monkeypatch.setenv('PIJIT_URL','http://unused')
    failure=dict(request_id='openjev-test',decision=dict(index=1),finish_reason='length',
                 generated_argument_tokens=17408,classification_control_records=1,usage_complete=False,
                 generation_diagnostics=dict(characters=17408,json_document_complete=False))
    def failed(*args,**kwargs):
        raise urllib.error.HTTPError('http://unused',500,'incomplete',{},io.BytesIO(json.dumps(failure).encode()))
    monkeypatch.setattr(b.urllib.request,'urlopen',failed)
    trace=dict(http_requests=[]);token=b.TRACE.set(trace)
    try:
        with pytest.raises(b.GenerationLengthError):
            b.post('/v1/openjev/toolcall',dict(prompt_ids=[1,2],continuations=[[3],[4,5]]))
    finally:b.TRACE.reset(token)
    record,=trace['http_requests']
    assert record['engine_request_id']=='openjev-test' and record['engine_decision_index']==1
    assert record['engine_finish_reason']=='length' and record['generated_argument_tokens']==17408
    assert record['input_tokens']==4 and not record['usage_complete']
    assert record['engine_generation_diagnostics']==failure['generation_diagnostics']


def test_length_error_is_not_a_retryable_pi_provider_failure(project,monkeypatch):
    import io
    import shutil
    import subprocess
    import urllib.error
    cli=shutil.which('pi')
    if not cli:pytest.skip('Requires pinned Pi in PATH')
    package=Path(cli).resolve().parents[2]
    assert json.loads((package/'package.json').read_text())['version']=='0.85.1'
    retry_module=package/'node_modules/@earendil-works/pi-ai/dist/utils/retry.js'
    monkeypatch.setenv('PIJIT_URL','http://unused')
    failure=dict(decision=dict(index=0),finish_reason='length',generated_argument_tokens=17408,
                 classification_control_records=1,usage_complete=False)
    calls=[]
    def failed(*args,**kwargs):
        calls.append(1)
        raise urllib.error.HTTPError('http://unused',500,'incomplete',{},io.BytesIO(json.dumps(failure).encode()))
    monkeypatch.setattr(b.urllib.request,'urlopen',failed)
    monkeypatch.setattr(b,'chat',lambda payload:b.post('/v1/openjev/toolcall',dict(prompt_ids=[1],continuations=[[2]])))
    result=b.run(dict(action='chat',cwd=str(project)))
    assert result['status']=='error' and 'call' not in result and len(calls)==1
    assert result['error'].startswith('GenerationLengthError:')
    assert not result['accounting']['usage_complete']
    assert result['accounting']['known_generated_argument_tokens']==17408
    errors=[result['error'],b.public_error(urllib.error.HTTPError('http://unused',500,'server error',{},None)),
            b.public_error(urllib.error.HTTPError('http://unused',503,'unavailable',{},None))]
    script=('import {isRetryableAssistantError} from '+json.dumps(retry_module.as_uri())+'; '
            'console.log(JSON.stringify(JSON.parse(process.argv[1]).map(errorMessage=>'
            'isRetryableAssistantError({stopReason:"error",errorMessage}))));')
    checked=subprocess.run(['node','--input-type=module','-e',script,json.dumps(errors)],capture_output=True,text=True,check=True,timeout=10)
    assert json.loads(checked.stdout)==[False,True,True]
