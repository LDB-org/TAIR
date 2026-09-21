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


def test_success_reply_is_opt_in_validated_metadata_not_an_executable_step():
    arguments = dict(first=dict(path='x', content='ok'), rest=[dict(name='on_success_reply',arguments=dict(content='Created x.'))])
    with pytest.raises(Exception):
        decode(response(0, arguments), TOOLS, [], branches(TOOLS, []))
    options = branches(TOOLS, [], success_reply=True)
    call, _ = decode(response(0, arguments), TOOLS, [], options)
    assert call['arguments'] == dict(steps=[dict(name='write', arguments=arguments['first'])])
    with pytest.raises(Exception):
        decode(response(0, dict(arguments, rest=[dict(name='on_success_reply',arguments=dict(content='x'*601))])), TOOLS, [], options)
    with pytest.raises(ValueError, match='once at the end'):
        decode(response(0, dict(arguments, rest=[*arguments['rest'],dict(name='bash',arguments=dict(command='true'))])), TOOLS, [], options)


def test_known_output_receipt_survives_decoding_without_becoming_a_native_argument():
    from tool_plan import split_success_reply
    receipt=dict(content='Checked.',expected_outputs=[dict(step=1,text='checks passed\n')])
    arguments=dict(first=dict(path='x',content='ok'),rest=[
        dict(name='bash',arguments=dict(command='check x')),
        dict(name='on_success_reply',arguments=receipt)])
    call,_=decode(response(0,arguments),TOOLS,[],branches(TOOLS,[],success_reply=True))
    assert [step['name'] for step in call['arguments']['steps']]==['write','bash']
    assert split_success_reply(arguments)[1]==receipt
    assert arguments['rest'][-1]['name']=='on_success_reply'


def test_completion_only_is_a_normal_reply_not_an_empty_executable_plan():
    options=branches(TOOLS,[],success_reply=True)
    def completion(content, **extra):
        return response(len(TOOLS),dict(steps=[dict(name='on_success_reply',
            arguments=dict(content=content,**extra))]))
    call,reused=decode(completion('All checks passed.'),TOOLS,[],options)
    assert call==dict(name='reply_user',arguments=dict(content='All checks passed.')) and not reused
    with pytest.raises(ValueError,match='Completion without actions'):
        decode(completion(''),TOOLS,[],options)
    with pytest.raises(ValueError,match='Completion without actions'):
        decode(completion('Done',expected_outputs=[dict(step=0,text='ok')]),TOOLS,[],options)


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


def test_content_shortlist_fills_after_more_than_fifteen_duplicate_sources(tmp_path):
    from plan_book import PlanBook
    book = ToolContentBook(tmp_path/'content.sqlite3')
    book.admit([('write file variant 000', 'distinct content', 'execution')])
    book.admit([(f'write file variant {i:03}', 'repeated content', 'execution')
                for i in range(1, 31)])
    ranked = PlanBook(book.path).candidates('write file', {})
    assert len(ranked) == 15
    assert {entry['source'] for entry in ranked} == {'repeated content'}
    candidates = book.candidates('write file', {}, limit=2)
    assert [entry['source'] for entry in candidates] == ['repeated content', 'distinct content']
    assert candidates[0]['id'] == ranked[0]['id']
    assert book.candidates('write file', {}, limit=1) == candidates[:1]
    book.reject(candidates[0]['id'], 'write file')
    filtered = book.candidates('', {'target': 'write file'}, limit=2)
    assert len(filtered) == 2
    assert candidates[0]['id'] not in {entry['id'] for entry in filtered}
    assert book.count() == 31


@pytest.mark.parametrize('use_cached', [False, True])
def test_reviewed_reuse_can_replace_content_without_another_request(use_cached):
    from tool_plan import continuation
    entry=dict(id='cached', contract='write old behavior', source='old bytes')
    options=branches(TOOLS, [entry], reuse_review=True)
    args=dict(requirement_check='Current requirement differs' if not use_cached else 'Content implements current requirement',
              use_cached_content=use_cached, path='new.txt')
    if not use_cached:
        args['content']='corrected bytes'
    actual,reused=decode(response(len(TOOLS),dict(steps=[dict(name='reuse_write',arguments=args)])),
                         TOOLS,[entry],options)
    assert actual['arguments']['steps']==[dict(name='write',arguments=dict(
        path='new.txt',content='old bytes' if use_cached else 'corrected bytes'))]
    assert reused==(['cached'] if use_cached else [])
    assert 'requirement_check' in continuation(len(TOOLS),TOOLS,[entry],options[len(TOOLS)])
    from jsonschema import ValidationError
    args.pop('use_cached_content')
    with pytest.raises(ValidationError):
        decode(response(len(TOOLS),dict(steps=[dict(name='reuse_write',arguments=args)])),TOOLS,[entry],options)


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


def test_request_delta_highlights_small_changes_in_long_contracts():
    from tool_plan import request_delta
    old='Create old.py\n'+'unchanged line\n'*200+'MARKER = 1\n'
    new=old.replace('old.py','new.py').replace('MARKER = 1','MARKER = 2')+'Run an additional check.\n'
    delta=request_delta(old,new)
    assert '-MARKER = 1' in delta and '+MARKER = 2' in delta
    assert '+Run an additional check.' in delta
    assert len(delta)<len(new)
    assert request_delta(old,old)=='(same request text)'


def test_request_delta_bounds_large_differences_without_hiding_truncation():
    from tool_plan import request_delta
    delta=request_delta('old\n'*4000,'new\n'*4000)
    assert len(delta)<6100 and 'middle omitted' in delta


def test_fenced_payload_guard_compares_actual_content_for_both_reuse_kinds():
    from tool_plan import compatible_payload
    task='Use this exact text:\n```python\nvalue = "中文"\n```'
    matching=dict(source='value = "中文"\n')
    assert compatible_payload(matching,task)
    assert not compatible_payload(dict(source='value = "中文"'),task)
    assert not compatible_payload(dict(source='value = "old"\n'),task)
    template=dict(plan_template=True,source=json.dumps(dict(version=1,content=matching['source'])))
    assert compatible_payload(template,task)
    assert not compatible_payload(template,task.replace('中文','new'))
    assert compatible_payload(matching,'Write a useful program without explicit source.')


def test_prepared_payload_guard_is_scoped_to_current_request():
    from tool_plan import payload_guard
    old=payload_guard('Exact source:\n```python\nold\n```')
    new=payload_guard('Exact source:\n```python\nnew\n```')
    for template in (False,True):
        for content in ('old\n','new\n','new'):
            entry=dict(source=json.dumps(dict(content=content)) if template else content,plan_template=template)
            assert old(entry)==(content=='old\n')
            assert new(entry)==(content=='new\n')
    assert payload_guard('No literal payload')(dict(source='anything'))


def test_general_branch_can_execute_after_coarse_classification_miss():
    from jsonschema import ValidationError
    options = branches(TOOLS, [])
    steps = [dict(name='bash', arguments=dict(command='python3 check.py'))]
    call, reused = decode(response(2, dict(steps=steps)), TOOLS, [], options)
    assert call == dict(name='plan', arguments=dict(steps=steps))
    assert not reused
    for args in [dict(steps=[]), dict(content='Done', steps=steps),
                 dict(steps=[dict(name='unknown', arguments={})])]:
        with pytest.raises(ValidationError):
            decode(response(2, args), TOOLS, [], options)


def test_every_classification_branch_can_finish_without_replaying_actions(tmp_path):
    book = ToolContentBook(tmp_path/'content.sqlite3')
    book.admit([('write text', 'text', 'execution')])
    candidates = book.candidates('write text', {})
    options = branches(TOOLS, candidates)
    for index in range(len(options)):
        call, reused = decode(response(index, dict(content='Checks passed.')), TOOLS, candidates, options)
        assert call == dict(name='reply_user', arguments=dict(content='Checks passed.'))
        assert not reused


def test_catalog_preserves_full_sources_and_highlights_changed_constraints():
    from tool_plan import contract_changes
    old='Create old.py. Merge touching intervals. Preserve order and do not mutate the input.'
    new='Create new.py. Separate touching intervals. Preserve order and do not mutate the input.'
    delta=contract_changes(old,new)
    assert any(line.startswith('-') and 'Merge' in line for line in delta.splitlines())
    assert any(line.startswith('+') and 'Separate' in line for line in delta.splitlines())
    entry=dict(id='a',contract=old,source='full source\n'*500,contract_changes=delta)
    description=branches(TOOLS,[entry])[len(TOOLS)]['description']
    assert entry['source'] in description and old in description and delta in description
    assert contract_changes(old,old)==''
    assert contract_changes('one two three','unrelated things here')==''


def test_repair_purpose_is_validated_and_never_forwarded_to_native_tool():
    from tool_plan import recovery_option
    from jsonschema import ValidationError
    options=[recovery_option(branches(TOOLS,[])[-1])]
    steps=[dict(purpose='Correct an assertion that contradicts the requirement',name='bash',arguments=dict(command='python3 corrected.py'))]
    call,reused=decode(response(0,dict(steps=steps)),TOOLS,[],options)
    assert call['arguments']['steps']==[dict(name='bash',arguments=dict(command='python3 corrected.py'))]
    assert not reused
    with pytest.raises(ValidationError):
        decode(response(0,dict(steps=call['arguments']['steps'])),TOOLS,[],options)
    assert decode(response(0,dict(content='Blocked by missing input')),TOOLS,[],options)[0]['name']=='reply_user'


@pytest.mark.parametrize('branch', ['write', 'bash', 'general'])
def test_write_references_expand_across_native_branches_without_mutating_wire(branch):
    import copy
    candidates = [dict(id='one', contract='first', source='first bytes'),
                  dict(id='two', contract='second', source='second bytes')]
    writes = [dict(name='write', arguments=dict(path=f'{i}.txt', content=dict(stored=i))) for i in range(2)]
    if branch == 'write':
        index, args = 0, dict(first=writes[0]['arguments'], rest=writes[1:])
    elif branch == 'bash':
        index, args = 1, dict(first=dict(command='true'), rest=writes)
    else:
        index, args = len(TOOLS)+len(candidates), dict(steps=writes)
    wire = copy.deepcopy(args)
    options = branches(TOOLS, candidates, write_references=True)
    call, reused = decode(response(index, args), TOOLS, candidates, options)
    assert reused == ['one', 'two']
    assert [s['arguments']['content'] for s in call['arguments']['steps'] if s['name']=='write'] == ['first bytes', 'second bytes']
    assert args == wire
    assert TOOLS[0]['parameters']['properties']['content'] == dict(type='string')


@pytest.mark.parametrize('content', [{'stored': -1}, {'stored': 1}, {'stored': True}, {'stored': 0, 'extra': 'x'}])
def test_write_references_reject_unknown_or_malformed_indices(content):
    from jsonschema import ValidationError
    candidates = [dict(id='one', contract='first', source='bytes')]
    with pytest.raises(ValidationError):
        decode(response(0, dict(first=dict(path='x', content=content), rest=[])),
               TOOLS, candidates, branches(TOOLS, candidates, write_references=True))


def test_write_references_are_opt_in_and_keep_full_generation_legal():
    from jsonschema import ValidationError
    candidates = [dict(id='one', contract='first', source='old bytes')]
    args = dict(first=dict(path='x', content=dict(stored=0)), rest=[])
    with pytest.raises(ValidationError):
        decode(response(0, args), TOOLS, candidates, branches(TOOLS, candidates))
    args['first']['content'] = 'new requirements need new bytes'
    call, reused = decode(response(0, args), TOOLS, candidates, branches(TOOLS, candidates, write_references=True))
    assert call['arguments']['steps'][0]['arguments']['content'] == args['first']['content']
    assert reused == []


def test_candidate_labels_distinguish_artifact_paths_from_whole_user_task():
    from tool_plan import content_evidence, observed_paths
    entry=dict(id='test',contract='Implement uniqueStrings',source="import './implementation.mjs';",
               verification=content_evidence(['test_module.mjs']))
    description=branches(TOOLS,[entry])[len(TOOLS)]['description']
    assert 'test_module.mjs' in description and 'NOT a specification of this particular file' in description
    assert 'helper or test' in description and entry['source'] in description
    for evidence in ['tool_execution_succeeded','{}','{"version":1,"observed_paths":"test.py"}','null']:
        assert observed_paths(dict(entry,verification=evidence))==[]
        assert entry['source'] in branches(TOOLS,[dict(entry,verification=evidence)])[len(TOOLS)]['description']


def test_selected_candidate_binding_matches_catalog_and_actual_decode():
    from tool_plan import candidate_binding, content_evidence, continuation
    candidates=[dict(id='python-id',contract='helper',source='import json',verification=content_evidence(['helper.py'])),
                dict(id='js-id',contract='implementation',source='export const x = 1;',verification=content_evidence(['module.mjs']))]
    options=branches(TOOLS,candidates,write_references=True)
    for i,entry in enumerate(candidates):
        index=len(TOOLS)+i
        binding=candidate_binding(i,entry)
        assert binding in options[index]['description']
        tail=continuation(index,TOOLS,candidates,options[index])
        assert binding in tail and entry['id'] not in tail
        call,reused=decode(response(index,dict(steps=[dict(name='reuse_write',arguments=dict(path='out'))])),TOOLS,candidates,options)
        assert call['arguments']['steps'][0]['arguments']['content']==entry['source']
        assert reused==[entry['id']]


@pytest.mark.parametrize('branch',['first','rest','general'])
def test_bash_argv_preserves_literals_and_does_not_mutate_wire(branch):
    import copy
    argv=[sys.executable,'-c','import json,sys; print(json.dumps(sys.argv[1:]))',
          'single\'double"', '$HOME', '$(printf unintended)', '', 'semi;colon', 'line\nbreak']
    step=dict(name='bash',arguments=dict(command=argv))
    if branch=='first':index,args=1,dict(first=step['arguments'],rest=[])
    elif branch=='rest':index,args=0,dict(first=dict(path='x',content='x'),rest=[step])
    else:index,args=len(TOOLS),dict(steps=[step])
    before=copy.deepcopy(args)
    call,reused=decode(response(index,args),TOOLS,[],branches(TOOLS,[],bash_argv=True))
    command=call['arguments']['steps'][-1]['arguments']['command']
    completed=subprocess.run(['bash','-c',command],capture_output=True,text=True,timeout=10)
    assert completed.returncode==0,completed.stderr
    assert json.loads(completed.stdout)==argv[3:]
    assert args==before and not reused
    assert TOOLS[1]['parameters']['properties']['command']==dict(type='string')


@pytest.mark.parametrize('command',[[],[42],['true']*65])
def test_bash_argv_rejects_empty_nonstrings_and_excessive_arguments(command):
    from jsonschema import ValidationError
    with pytest.raises(ValidationError):
        decode(response(1,dict(first=dict(command=command),rest=[])),TOOLS,[],branches(TOOLS,[],bash_argv=True))


def test_bash_argv_is_opt_in_and_preserves_shell_strings():
    from jsonschema import ValidationError
    with pytest.raises(ValidationError):
        decode(response(1,dict(first=dict(command=['printf','ok']),rest=[])),TOOLS,[],branches(TOOLS,[]))
    command='printf "%s" "$HOME" | cat'
    call,_=decode(response(1,dict(first=dict(command=command),rest=[])),TOOLS,[],branches(TOOLS,[],bash_argv=True))
    assert call['arguments']['steps'][0]['arguments']['command']==command


def test_dedicated_reply_branch_keeps_general_plan_and_reuse_indices():
    from tool_plan import continuation
    entry=dict(id='entry',contract='write',source='x')
    options=branches(TOOLS,[entry],reply_branch=True)
    reply_index=len(TOOLS)+1
    call,reused=decode(response(reply_index,dict(content='Done')),TOOLS,[entry],options)
    assert call==dict(name='reply_user',arguments=dict(content='Done')) and not reused
    tail=continuation(reply_index,TOOLS,[entry],options[reply_index])
    assert 'Selected reply' in tail and 'steps' not in tail and 'first' not in tail
    step=dict(name='bash',arguments=dict(command='true'))
    call,_=decode(response(len(options)-1,dict(steps=[step])),TOOLS,[entry],options)
    assert call['arguments']['steps']==[step]
    call,reused=decode(response(len(TOOLS),dict(steps=[dict(name='reuse_write',arguments=dict(path='x'))])),TOOLS,[entry],options)
    assert reused==['entry'] and call['arguments']['steps'][0]['arguments']['content']=='x'
    from jsonschema import ValidationError
    with pytest.raises(ValidationError):
        decode(response(reply_index,dict(steps=[step])),TOOLS,[entry],options)
