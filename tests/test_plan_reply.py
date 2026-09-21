import json
from pathlib import Path
import subprocess
import os
import shutil
import sys

import pytest


def test_reply_is_bound_to_successful_execution_and_unmodified_conversation():
    module = (Path(__file__).resolve().parents[1] / 'integrations/pijit/plan_reply.mjs').as_uri()
    script = r'''
import assert from 'node:assert/strict';
import { PlanReply } from MODULE;
const latch = new PlanReply();
const history = [{role: 'user', content: 'Write and check the file'}];
const steps = [{name: 'write', arguments: {path: 'x', content: 'ok'}},
  {name: 'bash', arguments: {command: 'check x'}}];
const results = steps.map(step => ({name: step.name, result: {content: [{type:'text',text:'(no output)'}]}}));
const messages = [...history, {role:'assistant', content:[{type:'toolCall',id:'p',name:'plan',arguments:{steps}}]},
  {role:'toolResult',toolCallId:'p',toolName:'plan',isError:false}];
const offer = () => latch.offer('p', 'Done', history, steps, results, 'session');
assert.equal(offer(), true);
assert.equal(latch.take(messages, 'session'), 'Done');
assert.equal(latch.take(messages, 'session'), undefined);
for (const changed of [
  [...messages, {role:'user',content:'Wait'}],
  [{role:'user',content:'Different task'}, ...messages.slice(1)],
  [...messages.slice(0,-1), {...messages.at(-1), isError:true}],
  [...messages.slice(0,-1), {...messages.at(-1), toolCallId:'other'}],
]) { offer(); assert.equal(latch.take(changed, 'session'), undefined); }
offer(); assert.equal(latch.take(messages, 'other-session'), undefined);
offer(); assert.equal(latch.take(messages, 'session', true), undefined);
offer(); latch.clear(); assert.equal(latch.take(messages, 'session'), undefined);
assert.equal(latch.offer('p','Done',history,steps,results.slice(0,1),'session'),false);
for (const name of ['read','find','grep','ls']) {
  assert.equal(latch.offer('p','Done',history,[{name}], [{name,result:{content:[]}}],'session'),false);
  assert.equal(latch.rejectionReason,'tool_requires_interpretation');
}
for (const result of [
  {isError:true,content:[]},
  {content:[{type:'text',text:'Unexpected diagnostic'}]},
  {content:[{type:'image',data:'x'}]},
  {content:[],details:{truncated:true}},
  {content:[],details:{fullOutputPath:'/tmp/output'}},
]) {
  assert.equal(latch.offer('p','Done',history,steps,[results[0],{name:'bash',result}],'session'),false);
}
const receipt = {name:'bash',result:{content:[{type:'text',text:'checks passed\n'}]}};
const outputs = [{step:1,text:'checks passed\n'}];
assert.equal(latch.offer('p','Done',history,steps,[results[0],receipt],'session',outputs),true);
assert.equal(latch.rejectionReason,undefined);
assert.equal(latch.offer('p','Done',history,steps,[results[0],receipt],'session'),false);
assert.equal(latch.rejectionReason,'unacknowledged_output');
assert.equal(latch.offer('p','Done',history,steps,[results[0],receipt],'session',[{step:1,text:'different'}]),false);
assert.equal(latch.rejectionReason,'expected_output_mismatch');
for (const expected of [
  [{step:1,text:'checks passed'}], // Whitespace is significant.
  [{step:1,text:'passed'}], // No substring matching.
  [{step:1,text:'checks passed.*'}], // No regular expressions.
  [{step:0,text:'checks passed\n'}], // Only bash outputs may be acknowledged.
  [{step:9,text:'checks passed\n'}],
  [...outputs,...outputs],
]) assert.equal(latch.offer('p','Done',history,steps,[results[0],receipt],'session',expected),false);
assert.equal(latch.offer('p','Done',history,steps,[results[0],{...receipt,result:{...receipt.result,
  details:{truncation:{truncated:true}}}}],'session',outputs),false);
'''.replace('MODULE', json.dumps(module))
    subprocess.run(['node', '--input-type=module', '-e', script], check=True, capture_output=True, text=True)


@pytest.mark.parametrize('mode', ['write', 'read', 'failure', 'output', 'matched_output', 'mismatched_output', 'cache_error'])
def test_real_pi_delivers_prepared_reply_only_after_eligible_tools(tmp_path, mode):
    cli = shutil.which('pi')
    if not cli:
        pytest.skip('Install pinned Pi 0.85.1 in PATH for adapter integration tests')
    package = Path(cli).resolve().parents[2] / 'package.json'
    if json.loads(package.read_text())['version'] != '0.85.1':
        pytest.skip('Adapter integration requires Pi 0.85.1')
    stub = tmp_path/'bridge-stub'
    stub.write_text('#!'+sys.executable+'\n'+r'''
import json, os, sys, time
from pathlib import Path
p=json.load(sys.stdin)
if p['action']=='chat':
    with Path('capability-inputs.jsonl').open('a') as f: f.write(json.dumps(p.get('server_capabilities'))+'\n')
with Path('bridge-actions.jsonl').open('a') as f: f.write(json.dumps(p['action'])+'\n')
if p['action']=='tool_plan_complete':
    result=dict(admitted=[],validation='fixture')
elif any(m['role']=='toolResult' for m in p['context']['messages']):
    result=dict(call=dict(name='reply_user',arguments=dict(content='MODEL CONTINUATION')))
else:
    mode=os.environ['REPLY_FIXTURE_MODE']
    step={'write':dict(name='write',arguments=dict(path='out.txt',content='hello')),
          'read':dict(name='read',arguments=dict(path='input.txt')),
          'failure':dict(name='bash',arguments=dict(command='exit 1')),
          'output':dict(name='bash',arguments=dict(command='echo unseen-result'))}[
              'output' if mode.endswith('matched_output') else 'read' if mode=='cache_error' else mode]
    result=dict(request_id='fixture-plan',call=dict(name='plan',arguments=dict(steps=[step])),
                generic_plan=True,plan_task='fixture',on_success_reply='PREPARED REPLY',
                generated_argument_tokens=10,classification_control_records=1,input_tokens=20)
    if mode.endswith('matched_output'):
        result['expected_plan_outputs']=[dict(step=0,text='unseen-result\n' if mode=='matched_output' else 'different\n')]
if p['action']=='chat':
    result['server_capabilities']=p.get('server_capabilities') or dict(url=os.environ['PIJIT_URL'],
        model='/model',session_id=p['session_id'],observed_at=time.time(),capabilities=dict(plan_budget_version=1))
    if os.environ['REPLY_FIXTURE_MODE']=='cache_error' and len(Path('capability-inputs.jsonl').read_text().splitlines())==2:
        result['error']='HTTPError: HTTP Error 500: Internal Server Error'
print(json.dumps(result))
''')
    stub.chmod(0o755)
    (tmp_path/'input.txt').write_text('unseen input')
    root = Path(__file__).resolve().parents[1]
    env = {k:v for k,v in os.environ.items() if not k.startswith(('PIJIT_', 'TAIR_'))}
    env.update(PIJIT_URL='http://127.0.0.1:1', PIJIT_PYTHON=str(stub),
               PIJIT_STATE_DIR=str(tmp_path/'state'), PIJIT_PLAN_SUCCESS_REPLY='1',
               PIJIT_CAPABILITIES_CACHE='1', REPLY_FIXTURE_MODE=mode)
    result = subprocess.run(['node',str(root/'integrations/pijit/launch.mjs'),'--plan-only',
        '--no-session','--mode','json','-p','Execute fixture'],cwd=tmp_path,env=env,
        capture_output=True,text=True,timeout=30,check=True)
    events=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    messages=[event['message'] for event in events if event.get('type')=='message_end'
              and event.get('message',{}).get('role')=='assistant']
    final=messages[-1]
    direct=mode in ('write','matched_output')
    expected='PREPARED REPLY' if direct else 'MODEL CONTINUATION'
    assert final['content']==[dict(type='text',text=expected)]
    actions=[json.loads(line) for line in (tmp_path/'bridge-actions.jsonl').read_text().splitlines()]
    assert actions.count('chat')==(1 if direct else 3 if mode=='cache_error' else 2)
    snapshots=[json.loads(line) for line in (tmp_path/'capability-inputs.jsonl').read_text().splitlines()]
    assert snapshots[0] is None
    if not direct:assert snapshots[1]['capabilities']['plan_budget_version']==1
    if mode=='cache_error':assert snapshots[2] is None
    if mode=='write':
        assert (tmp_path/'out.txt').read_text()=='hello'
        assert final['usage']['totalTokens']==0
