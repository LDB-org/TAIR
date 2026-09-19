import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
spec = importlib.util.spec_from_file_location('bound_edits', ROOT / 'benchmarks/benchmark_bound_edits.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_binder_ignores_nonliteral_and_nested_values():
    source = 'workers = get_workers()\ntimeout = True\ndef inner():\n    workers = 2\n'
    assert module.bind({'app.py': source}) == [None]


def test_batch_binding_changes_requested_fields_only(tmp_path):
    case = next(c for c in module.cases() if c['name'] == 'eight_edits')
    for name, content in case['sources'].items():
        (tmp_path / name).write_text(content)
    plan = next(p for p in module.bind(case['sources']) if p and len(p['edits']) == 8)
    module.execute({'kind': 'replace', 'arguments': plan}, tmp_path)
    module.verify(case, tmp_path)
    path = tmp_path / 'service_0.py'
    path.write_text(path.read_text().replace('preserve-0', 'wrong'))
    with pytest.raises(AssertionError):
        module.verify(case, tmp_path)


def test_new_value_is_not_in_catalog():
    case = next(c for c in module.cases() if c['name'] == 'new_value')
    plans = module.bind(case['sources'])
    assert all('workers = 7' != e['new'] for p in plans if p for e in p['edits'])


def test_empty_catalog_skips_classification_before_tokenization(monkeypatch):
    calls = []
    monkeypatch.setattr(module, 'tokenize', lambda url, messages: [10, 20])
    def post(url, route, body):
        calls.append(body)
        return {'usage': {'prompt_tokens': 2, 'completion_tokens': 5},
                'choices': [{'finish_reason': 'stop', 'text': '{"edits": []}'}]}
    monkeypatch.setattr(module, 'post', post)
    row = dict(preparation_seconds=0., inference_seconds=0., responses=[],
               logical_input_tokens=0, generated_tokens=0, controls=0)
    result = module.infer('unused', [], [35], [None], 'classify_skip_empty', row)
    assert result == {'edits': []}
    assert len(calls) == 1 and 'structured_outputs' in calls[0]
    assert 'vllm_xargs' not in calls[0]
    assert row['controls'] == 0 and row['skipped_empty_classification']


def test_nonempty_catalog_still_classifies_and_falls_back(monkeypatch):
    calls = []
    monkeypatch.setattr(module, 'tokenize', lambda url, messages: [10, 20])
    def post(url, route, body):
        calls.append(body)
        if len(calls) == 1:
            return {'usage': {'prompt_tokens': 2, 'completion_tokens': 1},
                    'choices': [{'token_ids': [36]}]}
        return {'usage': {'prompt_tokens': 2, 'completion_tokens': 5},
                'choices': [{'finish_reason': 'stop', 'text': '{"edits": []}'}]}
    monkeypatch.setattr(module, 'post', post)
    row = dict(preparation_seconds=0., inference_seconds=0., responses=[],
               logical_input_tokens=0, generated_tokens=0, controls=0)
    module.infer('unused', [], [35, 36], [{'edits': []}, None], 'classify_skip_empty', row)
    assert len(calls) == 2 and 'vllm_xargs' in calls[0]
    assert row['controls'] == 1 and row['fallback']
    assert not row['skipped_empty_classification']
