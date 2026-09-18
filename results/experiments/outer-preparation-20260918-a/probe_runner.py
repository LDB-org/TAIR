import importlib.util,json,os,tempfile,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('bridge','integrations/pijit/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
tails=[[{'role':'assistant','content':label},{'role':'user','content':'Selected tool: '+name+'. Generate ONLY its argument JSON. Schema: '+json.dumps(schema)}] for label,name,schema in [('A','read',{'type':'object','properties':{'path':{'type':'string'}}}),('B','bash',{'type':'object','properties':{'command':{'type':'string'}}})]]
cases=[ [{'role':'system','content':'Coding assistant. Tools read and bash.'},{'role':'user','content':'Inspect the project and run tests.'}],
 [{'role':'system','content':'Coding assistant. Tools read and bash.'},{'role':'user','content':'Read app.py.'},{'role':'assistant','content':'TOOL CALL read app.py'},{'role':'user','content':'TOOL RESULT read\n'+('print("hello")\n'*300)}],
 [{'role':'system','content':'Coding assistant. Tools read and bash.'},{'role':'user','content':'请检查文件。'},{'role':'assistant','content':'B'},{'role':'user','content':'TOOL RESULT bash error=False:\n测试通过 ✅\nReply with the next tool letter.'}]]
with tempfile.TemporaryDirectory(prefix='tair-suffix-probe-') as tmp:
 b.STATE=Path(tmp)
 for i,messages in enumerate(cases):
  started=time.perf_counter();actual=b.prepare_continuations(messages,tails);seconds=time.perf_counter()-started
  reference=b.continuation_tokens(messages,tails)
  print(json.dumps({'case':i,'cache_present':bool(list(b.STATE.rglob('*.json'))),'equal':actual==reference,'seconds':seconds,'prefix_tokens':len(actual[0]),'suffixes':actual[1]}),flush=True)
  assert actual==reference
