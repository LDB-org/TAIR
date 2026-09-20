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
    fastapi=pytest.importorskip('fastapi')
    pytest.importorskip('httpx')
    from fastapi.testclient import TestClient
    for name, attrs in {
        'vllm.engine.protocol':dict(StreamingInput=SimpleNamespace),
        'vllm.inputs':dict(tokens_input=lambda ids,**kw:ids),
        'vllm.sampling_params':dict(SamplingParams=SimpleNamespace,StructuredOutputsParams=SimpleNamespace,
                                   RequestOutputKind=SimpleNamespace(DELTA='delta')),
    }.items():
        module=ModuleType(name);module.__dict__.update(attrs);monkeypatch.setitem(sys.modules,name,module)
    class Engine:
        model_config=SimpleNamespace(get_vocab_size=lambda:100000)
        arguments={}
        calls=0
        aborted=[]
        budgets=[]
        def get_tokenizer(self):return SimpleNamespace(encode=lambda text,**kw:list(text))
        async def abort(self, request_id):self.aborted.append(request_id)
        async def generate(self, inputs, params, request_id):
            self.calls+=1
            iterator=inputs.__aiter__();await anext(iterator)
            yield SimpleNamespace(metrics=None,outputs=[SimpleNamespace(token_ids=[7],logprobs=[{7:SimpleNamespace(logprob=0.)}])])
            continuation=await anext(iterator);self.budgets.append(continuation.sampling_params.max_tokens)
            raw=json.dumps(self.arguments)
            yield SimpleNamespace(outputs=[SimpleNamespace(token_ids=[1]*len(raw),text=raw,finish_reason='stop')])
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
