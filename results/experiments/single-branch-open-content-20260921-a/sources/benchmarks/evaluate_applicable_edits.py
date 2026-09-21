"""Frozen three-arm evaluation on a new fixture, including an unsupported edit."""

import os
import argparse
import importlib.util
import json
from pathlib import Path
import random
import shutil
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runner',ROOT/'benchmarks/evaluate_region_holdout.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
CASES={
 'compact_record':'Make encode_record emit compact JSON without spaces after separators, preserving sorted keys and all field values.',
 'finite_record':'Make encode_record reject NaN and Infinity with ValueError instead of emitting nonstandard JSON. Preserve ordinary finite records and sorted keys.',
 'score_range':'In normalize_score, reject scores outside 0..100 inclusive with ValueError before any arithmetic. Preserve normal normalization and both boundary values.',
 'empty_jobs':'Make schedule_jobs return ([], 0) immediately when jobs is empty. Preserve nonempty jobs, ordering and the given workers value.',
 'retry_alias':'Add -r as an alias for --retries in build_parser. Preserve the existing long flag, default of 2, explicit overrides and label behavior.',
 'missing_resource':'Make read_resource return None when loader(key) raises LookupError, preserving normal return values and allowing other exception types to propagate.',
 'new_divisor':'Change normalize_score to divide the input score by 200 instead of 100, preserving its signature and accepting all numeric input values.',
}
CHECK='''import json,sys,subprocess
sys.path.insert(0,'.')
import port_scanner as m
case=sys.argv[1]
if case=='compact_record':
 for value in [{'b':[1,2],'a':'x'},{}]:assert m.encode_record(value)==json.dumps(value,sort_keys=True,separators=(',',':'))
elif case=='finite_record':
 for value in [float('nan'),float('inf'),-float('inf')]:
  try:m.encode_record({'value':value})
  except ValueError:pass
  else:raise AssertionError('nonstandard float accepted')
 assert json.loads(m.encode_record({'value':1.5}))=={'value':1.5}
elif case=='score_range':
 for value in [-1,101,-.01,100.01]:
  try:m.normalize_score(value)
  except ValueError:pass
  else:raise AssertionError(value)
 for value in [0,1,50,100]:assert m.normalize_score(value)==value/100
elif case=='empty_jobs':
 assert m.schedule_jobs([],4)==([],0)
 assert m.schedule_jobs((),2)==([],0)
 assert m.schedule_jobs([3,1],4)==([3,1],4)
elif case=='retry_alias':
 for flag in ['-r','--retries']:assert m.build_parser().parse_args([flag,'5']).retries==5
 assert m.build_parser().parse_args([]).retries==2
elif case=='missing_resource':
 def missing(key):raise LookupError(key)
 assert m.read_resource(missing,'absent') is None
 def other(key):raise RuntimeError(key)
 try:m.read_resource(other,'error')
 except RuntimeError:pass
 else:raise AssertionError('unrelated exception swallowed')
 assert m.read_resource(lambda key:key+'!', 'found')=='found!'
elif case=='new_divisor':
 for value in [-125,-1,0,1,13,50,99,100,2000]:assert m.normalize_score(value)==value/200,(value,m.normalize_score(value))
p=subprocess.run([sys.executable,'-m','unittest','-v','test_port_scanner'],capture_output=True,text=True,timeout=25)
assert p.returncode==0,p.stdout+p.stderr
print(json.dumps({'passed':True,'regression':p.stderr}))
'''


def main(out,host,repeats):
 out=out.resolve();out.mkdir()
 pristine=out/'pristine';shutil.copytree(ROOT/'benchmarks/data/applicability_fixture',pristine,ignore=shutil.ignore_patterns('__pycache__'))
 source=(pristine/'port_scanner.py').read_text()
 check=out/'check.py';check.write_text(CHECK)
 r.CASES=CASES
 template=json.loads((ROOT/'results/experiments/pi-scoped-typed-20260918-a/empty_scan-0-native/attempt0/request.json').read_text())
 sources=out/'sources';sources.mkdir()
 for path in [Path(__file__),ROOT/'benchmarks/evaluate_region_holdout.py',ROOT/'benchmarks/compare_region_edits.py',ROOT/'deploy/region_edit_protocol.py',ROOT/'deploy/structural_edit_protocol.py',ROOT/'deploy/compact_structural_protocol.py',ROOT/'deploy/applicable_structural_protocol.py',ROOT/'integrations/pi/apply_edit.mjs']:
  shutil.copyfile(path,sources/path.name)
 manifest={'cases':CASES,'repeats':repeats,'seed':20260919,'arms':['native','previous','applicable'],'unsupported_case':'new_divisor',
  'policy':'each structural arm may make one additional native request on explicit route or failure; all costs counted; no training or prompt tuning after launch',
  'fixture':'new configuration utility, adapter-compatible filename; five regression tests, not the previous scanner',
  'scope':'six operation-compatible edits plus one expression beyond the restricted language; small synthetic screening, not production proof'}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 before={case:r.b.validate(pristine,case,check) for case in CASES};(out/'before-tests.json').write_text(json.dumps(before,indent=2))
 assert all(not value['passed'] for value in before.values())
 jobs=[(case,n) for n in range(repeats) for case in CASES];random.Random(20260919).shuffle(jobs)
 for index,(case,n) in enumerate(jobs):
  native=json.loads(json.dumps(template));native['messages'][1]['content']='Edit this file with the smallest necessary change; preserve unrelated behavior.\nFILE: port_scanner.py\nSOURCE:\n'+source+'\nTASK: '+CASES[case]
  allowed=r.compact.task_scope(source,CASES[case])
  payloads={'native':native}
  for arm,protocol in [('previous',r.compact),('applicable',r.applicable)]:
   payload=json.loads(json.dumps(native))
   for key in ['tools','tool_choice','parallel_tool_calls']:payload.pop(key,None)
   pattern=protocol.typed_grammar(source,allowed) if arm=='previous' else protocol.grammar(source,allowed)
   prompt=protocol.typed_prompt(source,allowed) if arm=='previous' else protocol.prompt(source,allowed)
   payload['structured_outputs']={'regex':pattern};payload['messages'][0]['content']=prompt
   payloads[arm]=payload
  order=['native','previous','applicable'];shift=index%3;order=order[shift:]+order[:shift]
  for arm in order:
   folder=out/f'{case}-{n}-{arm}';folder.mkdir();started=time.perf_counter();attempts=[]
   modes=['native'] if arm=='native' else ['multi','native']
   for number,mode in enumerate(modes):
    payload=native if mode=='native' else payloads[arm]
    result=r.attempt(folder/f'attempt{number}',payload,source,{},pristine,check,case,mode,host,
      typed_protocol=arm!='native',scoped_protocol=arm!='native',applicable_protocol=arm=='applicable')
    attempts.append(result)
    if result['passed']:break
   route=attempts[0].get('error')=='ValueError: Native route requested'
   row={'case':case,'repeat':n,'arm':arm,'passed':attempts[-1]['passed'],'seconds':time.perf_counter()-started,
    'explicit_native_route':route,'failure_fallback':len(attempts)>1 and not route,'attempts':attempts,
    'usage_complete':all('usage' in a for a in attempts),'usage':{k:sum(a.get('usage',{}).get(k,0) for a in attempts) for k in ['prompt_tokens','completion_tokens','total_tokens']}}
   (folder/'result.json').write_text(json.dumps(row,indent=2))
   with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   print(case,n,arm,'passed',row['passed'],'attempts',len(attempts),'native_route',route,'usage',row['usage'],'seconds',round(row['seconds'],2),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);p.add_argument('--host',default=os.environ.get('TAIR_ENGINE_HOST', os.environ.get('ENGINE_TOOLCALL_HOST', 'localhost')));p.add_argument('--repeats',type=int,default=1)
 a=p.parse_args();main(a.out,a.host,a.repeats)
