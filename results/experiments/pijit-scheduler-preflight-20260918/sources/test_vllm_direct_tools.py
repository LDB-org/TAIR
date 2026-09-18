import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType

import pytest

torch = pytest.importorskip('torch')
spec = importlib.util.spec_from_file_location('direct_tools', Path(__file__).parents[1]/'deploy/vllm_direct_tools.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_classification_timing_snapshots_before_continuation_mutates_stats():
    stats = SimpleNamespace(queued_ts=10., scheduled_ts=18., first_token_ts=18.2)
    timing = module.classification_timing(stats)
    stats.queued_ts = 22.
    stats.first_token_ts = 23.
    assert timing['initial_queue_seconds'] == 8.
    assert timing['scheduled_to_first_output_seconds'] == pytest.approx(.2)
    assert timing['engine_monotonic_timestamps']['queued_ts'] == 10.
    assert timing['engine_monotonic_timestamps']['first_token_ts'] == 18.2


@pytest.mark.parametrize('stats', [None, SimpleNamespace(),
    SimpleNamespace(queued_ts=0., scheduled_ts=0., first_token_ts=0.),
    SimpleNamespace(queued_ts=float('nan'), scheduled_ts=float('inf'), first_token_ts=-1.)])
def test_missing_classification_timing_is_unknown_not_zero(stats):
    timing = module.classification_timing(stats)
    assert timing['initial_queue_seconds'] is None
    assert timing['scheduled_to_first_output_seconds'] is None


def test_requeued_timestamp_does_not_create_negative_queue_duration():
    timing = module.classification_timing(SimpleNamespace(queued_ts=22., scheduled_ts=18., first_token_ts=23.))
    assert timing['initial_queue_seconds'] is None
    assert timing['scheduled_to_first_output_seconds'] == 5.


@pytest.mark.parametrize('mixed', [False, True])
def test_classification_uses_raw_candidate_logits(monkeypatch, mixed):
    outputs = ModuleType('vllm.v1.outputs')
    outputs.SamplerOutput = SimpleNamespace
    monkeypatch.setitem(sys.modules, 'vllm.v1.outputs', outputs)
    events = []
    monkeypatch.setattr(module, 'audit', lambda event, **data: events.append((event, data)))

    class Sampler:
        calls = 0

        def __call__(self, logits, sampling_metadata):
            self.calls += 1
            return SimpleNamespace(sampled_token_ids=torch.tensor([[0], [2]]), logprobs_tensors='unchanged')

        def gather_specific_token_logprobs(self, raw, mapping, selected):
            assert selected.tolist() == [2]
            assert torch.allclose(raw.exp().sum(-1), torch.ones(1))
            return 'scores'

    sampler = Sampler()
    ids = ['class', 'normal'] if mixed else ['class']
    params = SimpleNamespace(extra_args={'openjev_direct_classify': True}, logprob_token_ids=[1, 2])
    batch = SimpleNamespace(req_ids=ids, sampling_metadata=SimpleNamespace(logprob_token_ids={0: [1, 2]}),
                            update_async_output_token_ids=lambda: None)
    runner = SimpleNamespace(input_batch=batch, sampler=sampler, requests={
        'class': SimpleNamespace(sampling_params=params, num_computed_tokens=15),
        'normal': SimpleNamespace(sampling_params=SimpleNamespace(extra_args=None))})
    logits = torch.tensor([[100., 3., 7.], [4., 6., 8.]])[:len(ids)]
    result = module.classify(runner, logits, None)
    assert result.sampled_token_ids[:, 0].tolist() == ([2, 2] if mixed else [2])
    assert sampler.calls == int(mixed)
    assert events[0][1]['sampler_bypassed'] is not mixed


def test_ordinary_request_preserves_original_path(monkeypatch):
    outputs = ModuleType('vllm.v1.outputs')
    outputs.SamplerOutput = SimpleNamespace
    monkeypatch.setitem(sys.modules, 'vllm.v1.outputs', outputs)
    runner = SimpleNamespace(input_batch=SimpleNamespace(req_ids=['normal']), requests={
        'normal': SimpleNamespace(sampling_params=SimpleNamespace(extra_args=None))})
    assert module.classify(runner, None, None) is None


def test_resume_changes_schema_and_limit_without_resetting_cache(monkeypatch):
    request = ModuleType('vllm.v1.request')
    request.RequestStatus = SimpleNamespace(WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR='grammar')
    monkeypatch.setitem(sys.modules, 'vllm.v1.request', request)
    events = []
    monkeypatch.setattr(module, 'audit', lambda event, **data: events.append(data))
    grammar = object()
    session = SimpleNamespace(request_id='test', max_tokens=1, num_computed_tokens=123,
                              num_prompt_tokens=150, structured_output_request=None)
    scheduler = SimpleNamespace(kv_cache_manager=SimpleNamespace(get_blocks=lambda _: SimpleNamespace(get_block_ids=lambda: [[7, 8]])))
    module.resumed(scheduler, session, SimpleNamespace(max_tokens=192, structured_output_request=grammar))
    assert session.max_tokens == 192
    assert session.structured_output_request is grammar
    assert session.status == 'grammar'
    assert session.num_computed_tokens == 123
    assert events[0]['block_ids'] == [[7, 8]]


@pytest.mark.parametrize('mixed', [False, True])
def test_v2_excludes_classifier_from_sampler_even_when_mixed(monkeypatch, mixed):
    import numpy as np
    monkeypatch.setattr(module, 'audit', lambda *args, **kwargs: None)

    class Sampler:
        _openjev_candidates = {5: [1, 2]}
        req_states = SimpleNamespace(req_id_to_index={'direct': 5, 'ordinary': 9})
        calls = 0

        def sample(self, logits, expanded, mapping, mapping_np, pos, ids, local, **kwargs):
            self.calls += 1
            assert mapping_np.tolist() == [9]
            assert expanded.tolist() == mapping.tolist() == [9]
            assert pos.tolist() == [21]
            assert module.classify_v2(self, logits, expanded, mapping, mapping_np, pos, ids, local) is None
            return logits.argmax(-1), logits

    n = 2 if mixed else 1
    logits = torch.tensor([[100., 3., 7.], [4., 6., 8.]])[:n]
    mapping = torch.tensor([5, 9])[:n]
    sampler = Sampler()
    selected, processed = module.classify_v2(sampler, logits, mapping, mapping,
        np.array([5, 9])[:n], torch.tensor([20, 21])[:n], mapping, mapping)
    assert selected.tolist() == ([2, 2] if mixed else [2])
    assert torch.equal(processed, logits)
    assert sampler.calls == int(mixed)


def test_pause_retires_worker_slot_without_freeing_kv(monkeypatch):
    events = []
    monkeypatch.setattr(module, 'audit', lambda event, **data: events.append(data))
    blocks = [[7, 8]]
    scheduler = SimpleNamespace(finished_req_ids=set(), kv_cache_manager=SimpleNamespace(
        get_blocks=lambda _: SimpleNamespace(get_block_ids=lambda: blocks)))
    request = SimpleNamespace(request_id='classifier', num_computed_tokens=123,
                              sampling_params=SimpleNamespace(extra_args={'openjev_direct_classify': True}))
    module.paused(scheduler, request)
    assert scheduler.finished_req_ids == {'classifier'}
    assert events[0]['block_ids'] is blocks
    assert request.num_computed_tokens == 123
    request.sampling_params.extra_args = None
    request.request_id = 'normal'
    module.paused(scheduler, request)
    assert scheduler.finished_req_ids == {'classifier'}
