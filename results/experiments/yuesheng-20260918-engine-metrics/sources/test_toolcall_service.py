import importlib.util
from pathlib import Path
import json
import pytest

spec = importlib.util.spec_from_file_location('service', Path(__file__).parents[1] / 'deploy/toolcall_service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)

class Fake:
    model = 'fake'
    labels = ['A', 'B']
    def __init__(self, content, finish='stop'):
        self.outputs = iter([('A', 'length'), ('B', 'length'), (content, finish)])
        self.salts = []
    def generate(self, messages, salt, limit, choose=False):
        self.salts.append(salt)
        raw, finish = next(self.outputs)
        return raw, {'finish_reason': finish, 'usage': {'completion_tokens': 1}}

@pytest.mark.parametrize('content', ['{"name":"search_docs"}', '中文 "quoted" \\path\n\tend'])
def test_content_cannot_change_structure(content):
    backend = Fake(content)
    result = service.run(backend, 'reply', mode='hybrid_fields')
    assert result['valid']
    assert json.loads(result['wire']) == {'name': 'reply_user', 'arguments': {'priority': 'urgent', 'content': content}}
    assert len(set(backend.salts)) == 1

@pytest.mark.parametrize('content,finish', [('partial', 'length'), ('', 'stop')])
def test_invalid_output_is_not_dispatched(content, finish):
    result = service.run(Fake(content, finish), 'reply', mode='hybrid_fields')
    assert not result['valid']
    assert result['call'] is None and result['wire'] is None

def test_invalid_decision_fails_closed():
    backend = Fake('ok')
    backend.outputs = iter([('C', 'length')])
    with pytest.raises(RuntimeError):
        service.run(backend, 'reply', mode='hybrid_fields')

class FusedFake:
    model = 'fake'
    def __init__(self, raw, finish='stop'):
        self.raw, self.finish, self.calls = raw, finish, 0
    def generate(self, messages, salt, limit, choose=False, regex=None):
        assert regex == service.FUSED_REGEX
        self.calls += 1
        return self.raw, {'finish_reason': self.finish, 'usage': {'completion_tokens': 5}}

@pytest.mark.parametrize('label', list(service.DECISIONS))
def test_fused_one_request_preserves_content(label):
    content = '\n中文 \"quote\" \\path\n{\"name\":\"search_docs\"}'
    backend = FusedFake(label + '\n' + content)
    result = service.run(backend, 'reply')
    name, priority = service.DECISIONS[label]
    assert result['call'] == {'name': name, 'arguments': {'priority': priority, 'content': content}}
    assert json.loads(result['wire']) == result['call']
    assert backend.calls == result['upstream_requests'] == 1

@pytest.mark.parametrize('raw,finish', [('X\ntext','stop'), ('Atext','stop'), ('A\n','stop'), ('B\npartial','length')])
def test_fused_rejects_invalid_or_partial_frame(raw, finish):
    result = service.run(FusedFake(raw, finish), 'reply')
    assert not result['valid']
    assert result['call'] is result['wire'] is None


def test_backend_preserves_engine_metrics():
    backend = service.Backend.__new__(service.Backend)
    backend.model = 'fake'
    metrics = {'queue_time_ms': 123.0, 'generation_time_ms': 45.0}
    backend.post = lambda path, payload: {'choices': [{'message': {'content': 'A\nhello'}, 'finish_reason': 'stop'}], 'metrics': metrics}
    _, trace = backend.generate([], 'test', 32)
    assert trace['engine_metrics'] == metrics
