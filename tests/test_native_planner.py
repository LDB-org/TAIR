import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('native_planner',Path(__file__).parents[1]/'deploy/native_planner.py')
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)


def test_native_history_retains_tool_roles_and_identifiers():
    context={'systemPrompt':'system','messages':[
        {'role':'user','content':'task'},
        {'role':'assistant','content':[{'type':'toolCall','id':'a','name':'read','arguments':{'path':'a.py'}}]},
        {'role':'toolResult','toolCallId':'a','content':[{'type':'text','text':'source'}]},
    ]}
    messages=n.messages_for(context,'policy')
    assert messages[0]['content']=='system\npolicy'
    assert messages[2]['tool_calls'][0]['id']=='a'
    assert messages[3]=={'role':'tool','tool_call_id':'a','content':'source'}


@pytest.mark.parametrize('finish,calls,content,valid',[
    ('length',[], 'partial',False),
    ('stop',[],None,False),
    ('stop',[],'done',True),
    ('tool_calls',[{'function':{'name':'read','arguments':'{"path":"a.py"}'}}],None,True),
    ('tool_calls',[{'function':{'name':'missing','arguments':'{}'}}],None,True),
    ('tool_calls',[{'function':{'name':'read','arguments':'invalid json'}}],None,False),
])
def test_native_response_validates_completion_and_preserves_usage(finish,calls,content,valid):
    payload={'context':{'messages':[],'tools':[{'name':'read','description':'read','parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}}]}}
    def post(route,body):
        assert route=='/v1/chat/completions' and body['parallel_tool_calls']
        return {'id':'response','usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'finish_reason':finish,'message':{'content':content,'tool_calls':calls}}]}
    if not valid:
        with pytest.raises(ValueError):n.chat(payload,post,'/model')
    else:
        result=n.chat(payload,post,'/model')
        assert result['input_tokens']==100 and result['generated_argument_tokens']==20
        assert result['classification_control_records']==0
        assert result['call']['name']==(calls[0]['function']['name'] if calls else 'reply_user')


def test_prefix_cache_is_workspace_scoped_and_opt_in():
    salts=[]
    def post(route, body):
        salts.append(body['cache_salt'])
        return {'id':'r','usage':{'prompt_tokens':10,'completion_tokens':1},'choices':[{'finish_reason':'stop','message':{'content':'done'}}]}
    payload={'cwd':'/project/a','context':{'messages':[],'tools':[]}}
    for _ in range(2):n.chat(payload,post,'model',workspace_cache=True)
    assert salts[-1]==salts[-2]
    n.chat(payload,post,'model',workspace_cache=True,cache_namespace='other-arm')
    assert salts[-1]!=salts[-2]
    n.chat({**payload,'cwd':'/project/b'},post,'model',workspace_cache=True)
    assert salts[-1]!=salts[-2]
    for _ in range(2):n.chat(payload,post,'model')
    assert salts[-1]!=salts[-2]
