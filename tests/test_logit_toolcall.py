import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('logit_engine', Path(__file__).parents[1]/'deploy/logit_toolcall.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Tokenizer:
    eos_token = '<|im_end|>'
    def encode(self, text, **kwargs): return list(text.encode())
    def apply_chat_template(self, messages, **kwargs):
        return ''.join(message['content'] for message in messages) + '\nAssistant:\n'


class Cache:
    def __init__(self): self.length = 0
    def get_seq_length(self): return self.length


class Model:
    device = 'cpu'
    def __init__(self): self.calls = []
    def __call__(self, input_ids, past_key_values, **kwargs):
        import torch
        self.calls.append((input_ids.shape[1], past_key_values))
        cache = past_key_values if past_key_values is not None else Cache()
        cache.length += input_ids.shape[1]
        logits = torch.zeros((1, 1, 256)); logits[0, 0, ord('B')] = 10
        return SimpleNamespace(logits=logits, past_key_values=cache)


@pytest.mark.parametrize('mode,reused', [('direct_cached',True),('direct_reprefill',False)])
def test_direct_readout_does_not_generate_choice_and_cache_path_is_real(monkeypatch, mode, reused):
    torch = pytest.importorskip('torch')
    monkeypatch.setattr(torch.cuda, 'synchronize', lambda: None)
    engine = m.Engine.__new__(m.Engine)
    engine.model, engine.tokenizer = Model(), Tokenizer()
    engine.tools = [{'name':'read','description':'Read'}, {'name':'bash','description':'Execute'}]
    engine.labels, engine.slots = 'AB', [ord('A'), ord('B')]
    engine.schemas = [{}, {}]; engine.arguments = ['read grammar', 'bash grammar']
    generated = []
    def generate(session, logits, grammar, limit):
        generated.append(grammar)
        assert [f['stage'] for f in session.forwards] == ['classification_prefill','argument_prefill']
        return '{"command":"echo ok"}', [1, 2], True, 0
    engine.generate = generate
    result = engine.run('Run echo ok', mode)
    assert generated == ['bash grammar']
    assert result['decision']['classification_sampled_tokens'] == 0
    assert result['decision']['same_cache_object'] == reused
    assert len(engine.model.calls) == 2
    assert (result['forwards'][1]['cached_tokens'] > 0) == reused
    assert result['call'] == {'name':'bash','arguments':{'command':'echo ok'}}


def test_cache_rejects_rewritten_prefix_and_wrong_length(monkeypatch):
    torch = pytest.importorskip('torch')
    monkeypatch.setattr(torch.cuda, 'synchronize', lambda: None)
    session = m.Session(Model(), Tokenizer())
    session.advance([1,2], 'prefill')
    with pytest.raises(ValueError): session.advance([1,3,4], 'next')
    session.cache.length = 1
    with pytest.raises(ValueError): session.advance([1,2,3], 'next')
