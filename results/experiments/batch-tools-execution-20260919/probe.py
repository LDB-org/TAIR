import json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,'benchmarks')
import compare_pijit_presets as b
out=Path('results/experiments/batch-tools-execution-20260919').resolve();out.mkdir(exist_ok=False,parents=True)
with tempfile.TemporaryDirectory(prefix='tair-batch-probe-') as tmp:
 root=Path(tmp);stub=root/'bridge-stub'
 stub.write_text('''#!/tmp/tair-test-venv-20260918/bin/python
import json,sys,os
p=json.load(sys.stdin)
if any(m['role']=='toolResult' for m in p['context']['messages']):
 r={'call':{'name':'reply_user','arguments':{'content':'Probe finished.'}}}
else:
 steps=([{'name':'read','arguments':{'path':'missing.txt'}},{'name':'write','arguments':{'path':'must-not-exist.txt','content':'bad'}},{'name':'bash','arguments':{'command':'touch must-not-run.txt'}}] if os.environ['PROBE_MODE']=='failure' else [{'name':'write','arguments':{'path':'sequence.txt','content':'first'}},{'name':'read','arguments':{'path':'sequence.txt'}},{'name':'bash','arguments':{'command':"python -c \\\"from pathlib import Path; assert Path('sequence.txt').read_text() == 'first'\\\""}}])
 r={'call':{'name':'execute_plan','arguments':{'steps':steps}},'calls':steps}
r.update(request_id='probe',input_tokens=1,generated_argument_tokens=0,classification_control_records=0)
print(json.dumps(r))
''');stub.chmod(0o700)
 os.environ.update(PIJIT_PYTHON=str(stub),PIJIT_URL='http://127.0.0.1:1',PIJIT_BATCH_TOOLS='1')
 for mode in ['failure','sequence']:
  os.environ['PROBE_MODE']=mode
  project=root/mode;project.mkdir();(project/'app.py').write_text(b.SOURCE)
  folder=out/mode;folder.mkdir()
  scenario={'prompt':'Execute the probe.','check':("from pathlib import Path\nassert not Path('must-not-exist.txt').exists()\nassert not Path('must-not-run.txt').exists()" if mode=='failure' else "from pathlib import Path\nassert Path('sequence.txt').read_text()=='first'")}
  r=b.attempt(project,root/(mode+'-state'),folder,'batched',0,30,scenario=scenario)
  events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()]
  results=[e['message'] for e in events if e.get('type')=='message_end' and e.get('message',{}).get('role')=='toolResult']
  assert r['passed'],r
  assert len(results)==3,results
  assert all(m.get('isError')==(mode=='failure') for m in results),results
  (folder/'probe-verification.json').write_text(json.dumps({'mode':mode,'passed':True,'tool_results':results,'note':'Mocked provider, real Pi 0.85.1 tool execution. Not a GPU or performance measurement.'},indent=2))
  print(mode,'PASS')
