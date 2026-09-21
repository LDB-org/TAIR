import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cap_bridge',ROOT/'integrations/pijit/bridge.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
CAPS=dict(plan_budget_version=1,per_tool_limit=2048,max_steps=8,max_plan_tokens=17408,prefix_cache_version=1)


def test_session_cache_expires_without_sliding_and_isolates_connections():
    script='import {CapabilitiesCache} from '+json.dumps((ROOT/'integrations/pijit/capabilities_cache.mjs').as_uri())+';'+r'''
import assert from 'node:assert/strict';
const c=new CapabilitiesCache(), s={session_id:'s',observed_at:100,capabilities:{plan_budget_version:1}};
c.remember('url+model+credential','s',s);
const hit=c.get('url+model+credential','s',129);
assert.deepEqual(hit,s); hit.capabilities.plan_budget_version=9;
assert.equal(c.get('url+model+credential','s',129).capabilities.plan_budget_version,1);
c.remember('url+model+credential','s',c.get('url+model+credential','s',129));
assert.equal(c.get('url+model+credential','s',130),undefined);
for(const [key,session,now] of [['changed-credential','s',101],['url+model+credential','other',101],
  ['url+model+credential','s',99],['url+model+credential','s',NaN]]) {
 c.remember('url+model+credential','s',s); assert.equal(c.get(key,session,now),undefined);
}
c.remember('url+model+credential','s',s); c.clear();
assert.equal(c.get('url+model+credential','s',101),undefined);
'''
    subprocess.run(['node','--input-type=module','-e',script],check=True,capture_output=True,text=True)


@pytest.mark.parametrize('change',[None,'expired','future','url','model','session','disabled','malformed'])
def test_bridge_revalidates_snapshot_binding_and_age(monkeypatch,change):
    monkeypatch.setenv('PIJIT_URL','http://server')
    monkeypatch.setenv('PIJIT_CAPABILITIES_CACHE','0' if change=='disabled' else '1')
    monkeypatch.setattr(b.time,'time',lambda:110)
    snapshot=dict(url='http://server',model=b.MODEL,session_id='s',observed_at=100,capabilities=CAPS)
    if change=='expired':snapshot['observed_at']=80
    if change=='future':snapshot['observed_at']=111
    if change in ('url','model'):snapshot[change]='other'
    if change=='session':snapshot['session_id']='other'
    if change=='malformed':snapshot['observed_at']='100'
    fetched=[]
    monkeypatch.setattr(b,'fetch_server_capabilities',lambda url:fetched.append(url) or {})
    trace=dict(stage_seconds={},session_id='s');token=b.TRACE.set(trace)
    try:result=b.server_plan_budget(snapshot)
    finally:b.TRACE.reset(token)
    assert result==(change is None)
    assert len(fetched)==(0 if change is None else 1)
    assert trace['capabilities_cache_hit']==(change is None)
    if change is None:assert trace['server_capabilities']['observed_at']==100


def test_cache_miss_does_not_mask_negotiation_errors(monkeypatch):
    import urllib.error
    monkeypatch.setenv('PIJIT_URL','http://server')
    monkeypatch.setenv('PIJIT_CAPABILITIES_CACHE','1')
    def denied(url):raise urllib.error.HTTPError(url,401,'denied',{},None)
    monkeypatch.setattr(b,'fetch_server_capabilities',denied)
    with pytest.raises(urllib.error.HTTPError):b.server_plan_budget()


def test_cached_negotiation_does_not_change_model_instructions_or_schema(tmp_path,monkeypatch):
    monkeypatch.setenv('PIJIT_URL','http://server')
    monkeypatch.setenv('PIJIT_CAPABILITIES_CACHE','1')
    monkeypatch.setenv('PIJIT_PLAN_DISABLE_REUSE','1')
    monkeypatch.setattr(b,'STATE',tmp_path/'state')
    calls=[];fetched=[]
    monkeypatch.setattr(b,'fetch_server_capabilities',lambda url:fetched.append(url) or CAPS)
    def infer(messages,options,**kwargs):
        calls.append(json.dumps(dict(messages=messages,tools=options,plan_budget=kwargs['plan_budget'],
            classification=kwargs['classification_prompt'],
            instructions=[kwargs['branch_instruction'](i,option) for i,option in enumerate(options)]),sort_keys=True))
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',
            classification_control_records=1,call=dict(name='plan',arguments=dict(content='hello')))
    monkeypatch.setattr(b,'infer',infer)
    payload=dict(cwd=str(tmp_path),context=dict(messages=[dict(role='user',content='Say hello')]),
        inner_tools=[dict(name='bash',description='command',parameters=b.tool_plan.obj(dict(command=dict(type='string'))))])
    for index in range(2):
        trace=dict(stage_seconds={},session_id='s');token=b.TRACE.set(trace)
        try:b.generic_plan_chat(payload)
        finally:b.TRACE.reset(token)
        assert trace['capabilities_cache_hit']==bool(index)
        payload['server_capabilities']=trace['server_capabilities']
    assert calls[0]==calls[1] and len(fetched)==1
