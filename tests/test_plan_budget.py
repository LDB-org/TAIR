"""Budget contract and endpoint behavior without loading GPU weights."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

spec=importlib.util.spec_from_file_location('budget_engine',Path(__file__).parents[1]/'deploy/vllm_direct_tools.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_budget_is_per_argument_not_whole_plan():
    args=dict(first={'content':'x'*1500},rest=[dict(name='write',arguments={'content':'y'*1500})])
    report=m.measure_plan_arguments(args,list)
    assert sum(report['argument_tokens'])>2048 and not report['exceeded_steps']
    assert report['total_generation_limit']==17408
    report=m.measure_plan_arguments(dict(steps=[dict(name='write',arguments={'content':'x'*2100})]),list)
    assert report['exceeded_steps']==[0]


def test_conditional_reply_uses_existing_budget_envelope():
    reply=dict(name='on_success_reply',arguments=dict(content='Done.'))
    args=dict(first=dict(path='x',content='hello'),rest=[reply])
    report=m.measure_plan_arguments(args,list)
    assert len(report['argument_tokens'])==2 and not report['exceeded_steps']
    assert len(m.measure_plan_arguments(dict(steps=[dict(name='write',arguments=args['first']),reply]),list)['argument_tokens'])==2
    with pytest.raises(ValueError,match='Unsupported budgeted plan shape'):
        m.measure_plan_arguments(dict(args,on_success_reply='Done.'),list)


def test_exact_limit_unicode_serialization_and_reuse_reference():
    empty=len(json.dumps({'content':''},ensure_ascii=False,separators=(',',':')))
    args=dict(steps=[dict(name='write',arguments={'content':'雪'*(2048-empty)})])
    assert m.measure_plan_arguments(args,list)['argument_tokens']==[2048]
    args['steps'][0]['arguments']['content']+='雪'
    assert m.measure_plan_arguments(args,list)['exceeded_steps']==[0]
    reuse=dict(steps=[dict(name='reuse_write',arguments={'path':'huge.js'})])
    assert m.measure_plan_arguments(reuse,list)['argument_tokens'][0]<2048
    with pytest.raises(m.PlanBudgetExceeded):
        m.measure_plan_arguments(dict(steps=[dict(arguments={})]*9),list)


@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setattr(m, 'audit', lambda *args, **kwargs: None)
    monkeypatch.delenv('TAIR_STREAM_PLAN_BUDGET', raising=False)
    fastapi=pytest.importorskip('fastapi')
    pytest.importorskip('httpx')
    from fastapi.testclient import TestClient
    for name, attrs in {
        'vllm.engine.protocol':dict(StreamingInput=SimpleNamespace),
        'vllm.inputs':dict(tokens_input=lambda ids,**kw:dict(prompt_token_ids=ids,**kw)),
        'vllm.sampling_params':dict(SamplingParams=SimpleNamespace,StructuredOutputsParams=SimpleNamespace,
                                   RequestOutputKind=SimpleNamespace(DELTA='delta')),
    }.items():
        module=ModuleType(name);module.__dict__.update(attrs);monkeypatch.setitem(sys.modules,name,module)
    class Engine:
        model_config=SimpleNamespace(get_vocab_size=lambda:100000)
        arguments={}
        raw_override=None
        finish_reason='stop'
        calls=0
        aborted=[]
        budgets=[]
        prompts=[]
        request_ids=[]
        chunks=None
        emitted_chunks=0
        def get_tokenizer(self):return SimpleNamespace(encode=lambda text,**kw:list(text))
        async def abort(self, request_id):self.aborted.append(request_id)
        async def generate(self, inputs, params, request_id):
            self.calls+=1
            iterator=inputs.__aiter__();initial=await anext(iterator)
            self.prompts.append(initial.prompt);self.request_ids.append(request_id)
            yield SimpleNamespace(metrics=None,num_cached_tokens=64,outputs=[SimpleNamespace(token_ids=[7],logprobs=[{7:SimpleNamespace(logprob=0.)}])])
            continuation=await anext(iterator);self.budgets.append(continuation.sampling_params.max_tokens)
            raw=json.dumps(self.arguments) if self.raw_override is None else self.raw_override
            if self.chunks is not None:
                for i,chunk in enumerate(self.chunks):
                    self.emitted_chunks+=1
                    yield SimpleNamespace(outputs=[SimpleNamespace(token_ids=[1]*len(chunk),text=chunk,
                        finish_reason=self.finish_reason if i==len(self.chunks)-1 else None)])
                return
            yield SimpleNamespace(outputs=[SimpleNamespace(token_ids=[1]*len(raw),text=raw,finish_reason=self.finish_reason)])
    engine=Engine();app=fastapi.FastAPI();app.state.engine_client=engine;m.attach_router(app)
    with TestClient(app) as client:yield engine,client


def payload(budget=True):
    return dict(prompt_ids=[1],candidate_ids=[7],continuations=[[2]],tools=[dict(name='plan',parameters={'type':'object'})],
                max_tokens=17408 if budget else 2048,plan_budget=budget)


def test_router_accepts_large_plan_and_rejects_one_oversized_child(endpoint):
    engine,client=endpoint
    engine.arguments=dict(first={'content':'x'*1500},rest=[dict(name='write',arguments={'content':'y'*1500})])
    result=client.post('/v1/openjev/toolcall',json=payload())
    assert result.status_code==200,result.text
    data=result.json()
    assert data['generated_argument_tokens']>2048
    assert data['same_engine_session'] and len(data['plan_budget']['argument_tokens'])==2
    assert engine.budgets==[17408] and engine.calls==1
    engine.arguments=dict(steps=[dict(name='write',arguments={'content':'x'*2100})])
    result=client.post('/v1/openjev/toolcall',json=payload())
    assert result.status_code==422
    error=result.json()
    assert error['plan_budget']['exceeded_steps']==[0]
    assert error['generated_argument_tokens']>2048 and error['classification_control_records']==1
    assert 'call' not in error and len(engine.aborted)==1


def test_router_eight_children_and_legacy_requests(endpoint):
    engine,client=endpoint
    assert client.get('/v1/openjev/capabilities').json()['max_plan_tokens']==17408
    engine.arguments=dict(steps=[dict(name='write',arguments={'content':'x'*1800}) for _ in range(8)])
    result=client.post('/v1/openjev/toolcall',json=payload())
    assert result.status_code==200 and len(result.json()['plan_budget']['argument_tokens'])==8
    request=payload(False);request['max_tokens']=17408
    assert client.post('/v1/openjev/toolcall',json=request).status_code==400
    engine.arguments={'content':'hello'}
    result=client.post('/v1/openjev/toolcall',json=payload(False))
    assert result.status_code==200 and result.json()['plan_budget'] is None


def test_session_salt_reuses_namespace_without_reusing_request_ids(endpoint):
    engine,client=endpoint
    assert client.get('/v1/openjev/capabilities').json()['prefix_cache_version']==1
    engine.arguments={'content':'hello'}
    for _ in range(2):
        result=client.post('/v1/openjev/toolcall',json=dict(payload(),cache_salt='session-a'))
        assert result.status_code==200
        assert result.json()['prefix_cache_mode']=='session'
        assert result.json()['decision']['cached_prefix_tokens']==64
    assert engine.prompts[-1]['cache_salt']==engine.prompts[-2]['cache_salt']
    assert engine.request_ids[-1]!=engine.request_ids[-2]
    client.post('/v1/openjev/toolcall',json=dict(payload(),cache_salt='session-b'))
    assert engine.prompts[-1]['cache_salt']!=engine.prompts[-2]['cache_salt']
    for _ in range(2):
        result=client.post('/v1/openjev/toolcall',json=payload())
        assert result.json()['prefix_cache_mode']=='request'
    assert engine.prompts[-1]['cache_salt']!=engine.prompts[-2]['cache_salt']
    for salt in ['', 'x'*129]:
        assert client.post('/v1/openjev/toolcall',json=dict(payload(),cache_salt=salt)).status_code==422


def test_generation_diagnostics_distinguishes_complete_json_from_truncation():
    raw='  {"content":"private source"}'
    trailing=m.generation_diagnostics(raw+' '*10000)
    assert trailing['json_value_complete'] and trailing['json_document_complete']
    assert trailing['json_value_end']==len(raw) and trailing['trailing_whitespace_characters']==10000
    incomplete=m.generation_diagnostics(raw[:-2])
    assert not incomplete['json_value_complete'] and not incomplete['json_document_complete']
    assert incomplete['json_error_message']=='Unterminated string starting at'
    extra=m.generation_diagnostics(raw+'unexpected')
    assert extra['json_value_complete'] and not extra['json_document_complete']
    assert 'private source' not in json.dumps([trailing,incomplete,extra])


def test_length_error_exposes_structural_diagnostics_without_accepting_output(endpoint):
    engine,client=endpoint
    engine.raw_override='{"content":"unfinished'
    engine.finish_reason='length'
    result=client.post('/v1/openjev/toolcall',json=payload())
    assert result.status_code==500
    data=result.json()
    assert data['finish_reason']=='length' and not data['usage_complete'] and 'call' not in data
    assert data['generation_diagnostics']['characters']==len(engine.raw_override)
    assert not data['generation_diagnostics']['json_document_complete']
    assert data['decision']['index']==0 and engine.aborted==[data['request_id']]


def test_failed_generation_audit_retains_branch_without_source(endpoint, monkeypatch):
    engine,client=endpoint
    events=[]
    monkeypatch.setattr(m,'audit',lambda event,**fields:events.append(dict(event=event,**fields)))
    engine.raw_override='{"content":"private source'
    engine.finish_reason='length'
    result=client.post('/v1/openjev/toolcall',json=payload())
    assert result.status_code==500
    data=result.json()
    assert [e['event'] for e in events]==['decision','generation_failed']
    assert all(e['request_id']==data['request_id'] for e in events)
    assert events[0]['selected_index']==0 and events[0]['control_id']==7
    assert events[0]['continuation_tokens']==1 and events[0]['candidate_count']==1
    assert events[1]['finish_reason']=='length'
    assert events[1]['generated_argument_tokens']==data['generated_argument_tokens']
    assert events[1]['generation_diagnostics']==data['generation_diagnostics']
    assert 'private source' not in json.dumps(events)


@pytest.mark.parametrize('layout',['steps','first'])
@pytest.mark.parametrize('chunk_size',[1,7,4096])
def test_stream_budget_counts_closed_arguments_once(layout,chunk_size):
    values=[dict(content='雪\\"{}[],:',nested=dict(arguments={'content':'small'})),dict(command=['x','y'])]
    args=(dict(steps=[dict(name='write',arguments=v) for v in values]) if layout=='steps'
          else dict(rest=[dict(name='bash',arguments=values[1])],first=values[0]))
    encoded=[]
    def encode(value):
        encoded.append(value)
        return list(value)
    guard=m.StreamingPlanBudget(encode)
    raw=json.dumps(args,ensure_ascii=False)
    for end in range(chunk_size,len(raw)+chunk_size,chunk_size):guard.feed(raw[:end])
    assert [guard.counts[i] for i in range(2)]==m.measure_plan_arguments(args,list)['argument_tokens']
    assert len(encoded)==2


def test_stream_budget_aborts_before_generating_remaining_children(endpoint,monkeypatch):
    engine,client=endpoint
    monkeypatch.setenv('TAIR_STREAM_PLAN_BUDGET','1')
    first='{"steps":[{"name":"write","arguments":'+json.dumps({'content':'x'*2100})
    engine.chunks=[first, '},{"name":"write","arguments":{"content":"unused"}}]}']
    result=client.post('/v1/openjev/toolcall',json=payload())
    data=result.json()
    assert result.status_code==422 and 'call' not in data
    assert engine.emitted_chunks==1 and engine.aborted==[data['request_id']]
    assert data['generated_argument_tokens']==len(first) and not data['usage_complete']
    assert data['stream_argument_tokens']['0']>2048


def test_stream_budget_preserves_multi_child_capacity(endpoint,monkeypatch):
    engine,client=endpoint
    monkeypatch.setenv('TAIR_STREAM_PLAN_BUDGET','1')
    engine.arguments=dict(steps=[dict(name='write',arguments=dict(content='x'*1500)) for _ in range(8)])
    result=client.post('/v1/openjev/toolcall',json=payload())
    assert result.status_code==200 and result.json()['generated_argument_tokens']>2048
    assert len(result.json()['plan_budget']['argument_tokens'])==8


def test_stream_budget_exact_boundary_and_incomplete_string():
    overhead=len(json.dumps({'content':''},separators=(',',':')))
    guard=m.StreamingPlanBudget(list)
    prefix='{"first":'+json.dumps({'content':'x'*(2048-overhead)},separators=(',',':'))
    guard.feed(prefix)
    assert guard.counts=={0:2048}
    guard=m.StreamingPlanBudget(list)
    guard.feed('{"first":{"content":"'+'x'*10000)
    assert guard.counts=={}
    with pytest.raises(m.PlanBudgetExceeded):
        guard.feed('{"first":{"content":"'+'x'*10000+'"}')
