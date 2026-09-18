import importlib.util,json,time,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
spec=importlib.util.spec_from_file_location('http','benchmarks/benchmark_ideal_classification.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=Path('results/experiments/bound-action-task-20260918-maintenance');url='http://127.0.0.1:18906'
native=m.post(url,'/v1/chat/completions',{'model':'/model','messages':[{'role':'user','content':'Return exactly this text: DTYPE_OK'}],'temperature':0,'max_tokens':16,'cache_salt':uuid.uuid4().hex,'chat_template_kwargs':{'thinking':False,'enable_thinking':False}})
(p/'native-smoke2.json').write_text(json.dumps(native,indent=2));assert native['choices'][0]['message']['content'].strip()=='DTYPE_OK'
plans=json.loads(Path('results/experiments/ideal-classification-20260918-b/plans.json').read_text())
def call(plan):
 req=dict(plan['request'],cache_salt=uuid.uuid4().hex)
 begin=time.perf_counter();res=m.post(url,'/v1/completions',req)
 choice=res['choices'][0]
 if plan['arm']=='classify':
  idx=req['logprob_token_ids'].index(choice['token_ids'][0]);action=plan['options'][idx]['action']
 else:action=json.loads(choice['text'])
 return {'arm':plan['arm'],'correct':action==plan['expected'],'seconds':time.perf_counter()-begin,'response':res}
for repeat in range(2):
 jobs=[next(p for p in plans if p['size']==512 and p['repeat']==repeat and p['arm']==arm) for arm in ['generate','generate','classify','classify']]
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(call,jobs))
 with (p/'mixed-smoke.jsonl').open('a') as f:
  for r in rows:f.write(json.dumps(r)+'\n')
 assert all(r['correct'] for r in rows)
 print('Mixed batch',repeat,'4/4 correct',flush=True)
