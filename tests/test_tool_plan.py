import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'deploy'))
from tool_plan import ToolContentBook, branches, decode, obj

TOOLS = [dict(name='write', description='write file', parameters=obj(dict(path=dict(type='string'), content=dict(type='string')))),
         dict(name='bash', description='run command', parameters=obj(dict(command=dict(type='string'))))]


def response(index, arguments):
    return dict(decision=dict(index=index), call=dict(name='plan', arguments=arguments),
                same_engine_session=True, finish_reason='stop', classification_control_records=1)


def test_classifies_first_tool_and_returns_one_multi_tool_plan():
    options = branches(TOOLS, [])
    result, reused = decode(response(0, dict(first=dict(path='index.js', content='export const x = 1;'),
                                             rest=[dict(name='bash', arguments=dict(command='node --check index.js'))])), TOOLS, [], options)
    assert all(option['name']=='plan' for option in options)
    assert result['name']=='plan' and [s['name'] for s in result['arguments']['steps']]==['write','bash']
    assert not reused


def test_generic_content_persists_without_python_or_task_validator(tmp_path):
    book = ToolContentBook(tmp_path/'content.sqlite3')
    identity, = book.admit([('JavaScript constant', 'export const x = 1;', 'execution only')])
    candidates = book.candidates('JavaScript constant', {})
    options = branches(TOOLS, candidates)
    result, reused = decode(response(len(TOOLS), dict(steps=[dict(name='reuse_write', arguments=dict(path='another.js'))])),
                            TOOLS, candidates, options)
    assert reused == [identity]
    assert result['arguments']['steps'] == [dict(name='write', arguments=dict(path='another.js',content='export const x = 1;'))]
    assert ToolContentBook(book.path).load()[0]['verification']=='execution only'


def test_reply_does_not_execute_a_tool_and_bad_steps_rejected():
    options=branches(TOOLS, [])
    assert decode(response(2, dict(content='Done')), TOOLS, [], options)[0]['name']=='reply_user'
    with pytest.raises(Exception):
        decode(response(0, dict(first=dict(path='a',content='x'), rest=[dict(name='unknown',arguments={})])), TOOLS, [], options)
    incomplete=response(0,{})
    incomplete['same_engine_session']=False
    with pytest.raises(ValueError,match='Incomplete'):
        decode(incomplete, TOOLS, [], options)


def test_executor_stops_on_error_and_cancel_and_preserves_results():
    if not shutil.which('node'):pytest.skip('Node.js required')
    path=(Path(__file__).resolve().parents[1]/'integrations/pijit/plan_executor.mjs').as_uri()
    script='''
import assert from 'node:assert/strict';
import { executePlan } from MODULE;
const calls=[];
const tools=new Map([
 ['write',{execute:async(id,args)=>{calls.push(args.path);return {content:[{type:'text',text:'written'}]};}}],
 ['bash',{execute:async()=>{throw new Error('exit 7');}}]
]);
const steps=[{name:'write',arguments:{path:'first'}},{name:'bash',arguments:{}},{name:'write',arguments:{path:'never'}}];
await assert.rejects(executePlan('id',steps,tools),error=>{
 const result=JSON.parse(error.message);assert.equal(result.failed_step,1);assert.equal(result.completed.length,1);
 assert.equal(result.remaining_steps_skipped,1);return true;
});
assert.deepEqual(calls,['first']);
const controller=new AbortController();controller.abort();
await assert.rejects(executePlan('id',steps,tools,controller.signal));assert.deepEqual(calls,['first']);
const result=await executePlan('ok',[steps[0]],tools);assert.equal(result[0].name,'write');
'''.replace('MODULE',json.dumps(path))
    actual=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=10)
    assert actual.returncode==0,actual.stderr


def test_execution_logs_are_metadata_only_and_do_not_affect_tools(tmp_path):
    if not shutil.which('node'):pytest.skip('Node.js required')
    root=Path(__file__).resolve().parents[1]/'integrations/pijit'
    script='''
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';
import { executePlan } from EXECUTOR;
import { appendPlanEvent, formatPlanStatus } from METRICS;
const state=STATE;const events=[];
const tools=new Map([['write',{execute:async()=>({content:[{type:'text',text:'SECRET_OUTPUT'}]})}],
 ['bash',{execute:async()=>{throw new Error('SECRET_ERROR');}}]]);
const steps=[{name:'write',arguments:{content:'SECRET_SOURCE'}},{name:'bash',arguments:{}},{name:'write',arguments:{}}];
await assert.rejects(executePlan('p',steps,tools,undefined,undefined,event=>{
 events.push(event);appendPlanEvent(state,state,'s','p',event);
}));
assert.deepEqual(events.map(e=>e.event),['plan_start','step_start','step_success','step_start','step_failure','plan_failure']);
assert.equal(events.at(-1).skipped_steps,1);assert.equal(events.at(-1).completed_steps,1);
const hash=createHash('sha256').update(resolve(state)).digest('hex').slice(0,20);
const raw=readFileSync(join(state,'workspaces',hash,'plan-events.jsonl'),'utf8');
assert.ok(!raw.includes('SECRET'));assert.ok(raw.includes('"plan_id":"p"'));
const result=await executePlan('q',[steps[0]],tools,undefined,undefined,()=>{throw new Error('logging failure');});
assert.equal(result.length,1);
assert.equal(formatPlanStatus({generated:2106,controls:3,plans:2,executed:2,failed:0,reusedSuccessful:0,admitted:1}),
 'pijit · gen 2106 · cls 3 · plans 2 · ok 2 · fail 0 · reuse 0 · learn 1');
'''.replace('EXECUTOR',json.dumps((root/'plan_executor.mjs').as_uri())).replace('METRICS',json.dumps((root/'plan_metrics.mjs').as_uri())).replace('STATE',json.dumps(str(tmp_path)))
    actual=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=10)
    assert actual.returncode==0,actual.stderr


def test_content_candidates_collapse_path_variants_without_merging_different_bytes(tmp_path):
    book = ToolContentBook(tmp_path/'content.sqlite3')
    book.admit([('write UTF-8 file old_a.py', 'same source', 'execution'),
                ('write UTF-8 file old_b.py', 'same source', 'execution'),
                ('write UTF-8 file other.py', 'different source', 'execution')])
    candidates = book.candidates('write UTF-8 file', {}, limit=7)
    assert {e['source'] for e in candidates} == {'same source', 'different source'}
    assert len(candidates) == 2 and book.count() == 3
    assert book.candidates('write UTF-8 file', {}, limit=0) == []
    options = branches(TOOLS, candidates)
    assert all(e['contract'] in options[len(TOOLS)+i]['description'] for i,e in enumerate(candidates))


def test_selected_content_can_fall_back_to_generation_for_changed_constraints(tmp_path):
    book = ToolContentBook(tmp_path/'content.sqlite3')
    book.admit([('write overwrite', 'old content', 'execution')])
    candidates = book.candidates('write append', {})
    options = branches(TOOLS, candidates)
    result, reused = decode(response(len(TOOLS), dict(steps=[
        dict(name='write', arguments=dict(path='new.py', content='new implementation'))])),
        TOOLS, candidates, options)
    assert not reused
    assert result['arguments']['steps'][0]['arguments']['content'] == 'new implementation'
