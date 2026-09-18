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
    monkeypatch.setattr(b, 'tokenize', lambda messages: [1, 2] if len(messages) == 2 else [8, 9])
    with pytest.raises(ValueError, match='prefix'):
        b.infer([{'role': 'user', 'content': 'test'}], [{'name': 'tool', 'parameters': {'type': 'object'}}])


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
