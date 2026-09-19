import json, sys, hashlib
from pathlib import Path
sys.path.insert(0, 'benchmarks')
from benchmark_adaptive_plan import check_module, cases, SEED
out=Path('results/experiments/adaptive-plan-20260919-a')
rows=[json.loads(line) for line in (out/'rows.jsonl').read_text().splitlines()]
assert len(rows)==48
book=json.loads((out/'codebook.json').read_text())
assert hashlib.sha256(SEED.read_bytes()).hexdigest()==book['entries'][0]['source_sha256']
case_map={c['name']:c for c in cases()}
for row in rows:
 assert row['inference_requests']==1 and row['usage_complete'] and row['passed']
 assert row['input_tokens']==row['response']['usage']['prompt_tokens']
 assert row['output_tokens']==row['response']['usage']['completion_tokens']
 assert row==json.loads((out/'attempts'/str(row['index'])/'result.json').read_text())
 for name,kind in case_map[row['case']]['outputs'].items():
  check_module(out/'attempts'/str(row['index'])/'project'/name,kind)
 for step in row['plan']['steps']:
  if step['op']=='reuse':
   assert case_map[row['case']]['outputs'][step['path']]=='utf8'
   assert (out/'attempts'/str(row['index'])/'project'/step['path']).read_text()==book['entries'][0]['source']
summary=json.loads((out/'summary.json').read_text())
summary['groups']={}
for group,names in {'reuse_eligible':['exact_contract','chinese_paraphrase','new_destination'],'must_generate':['different_encoding','create_parents','exclusive_write','binary'],'mixed':['mixed_plan']}.items():
 summary['groups'][group]={}
 for arm in summary['all']:
  selected=[r for r in rows if r['arm']==arm and r['case'] in names]
  summary['groups'][group][arm]={k:sum(r.get(k,0) for r in selected) for k in ['seconds','inference_seconds','input_tokens','output_tokens','reuse_steps','write_steps']}
  summary['groups'][group][arm]['attempts']=len(selected)
summary['audit']={'attempts':len(rows),'independent_artifact_checks':'all passed','requests_per_attempt':1,'catalog_source_unchanged':True,'wrong_reuse_steps':0}
(out/'audit.json').write_text(json.dumps(summary['audit'],indent=2)+'\n')
Path('docs/ADAPTIVE_PLAN_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'all':summary['all'],'groups':summary['groups']},indent=2))
