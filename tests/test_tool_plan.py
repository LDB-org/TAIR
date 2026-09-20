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
