import json, pathlib, subprocess, hashlib
root=pathlib.Path('/Users/zacharyzcr/Projects/TAIR');p=root/'results/experiments/bound-edits-skip-empty-20260919-a'
rows=[json.loads(s) for s in (p/'rows.jsonl').read_text().splitlines()]
assert len(rows)==72 and len({(r['arm'],r['case'],r['repeat']) for r in rows})==72
for name in ['benchmark_bound_edits.py','benchmark_engine_plan.py']:
    assert (p/name).read_bytes()==(root/'benchmarks'/name).read_bytes(), 'Source changed during run'
ids=[r['responses'][0]['id'] for r in rows if r['controls']]
raw=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','rs-yuesheng-gpu-public','docker exec vllm-deepseek-v4-sm120-situ tail -n 2500 /tmp/openjev-direct-events.jsonl'],text=True)
events=[json.loads(s) for s in raw.splitlines()]
events=[e for e in events if any(e.get('request_id','').startswith(i) for i in ids)]
assert len(ids)==33
assert all(any(e['event']=='classify' and e.get('sampler_bypassed') and e.get('request_id','').startswith(i) for e in events) for i in ids)
(p/'engine-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
opt=[r for r in rows if r['arm']=='classify_skip_empty']
skipped=[r for r in opt if r.get('skipped_empty_classification')]
assert len(skipped)==3 and all(r['case']=='new_code' and r['controls']==0 and r['inference_requests']==1 for r in skipped)
miss=[r for r in opt if r['case']=='new_value']
assert len(miss)==3 and all(r['controls']==1 and r['fallback'] and r['inference_requests']==2 for r in miss)
percase=[]
for name in sorted({r['case'] for r in rows}):
    item={'case':name}
    for arm in ['generate','compact','classify','classify_skip_empty']:
        group=[r for r in rows if r['case']==name and r['arm']==arm]
        item[arm]=sum(r['total_seconds'] for r in group)/len(group)
    percase.append(item)
summaries=json.loads((p/'summary.json').read_text());index={(r['scope'],r['arm']):r for r in summaries}
ratios={scope:{base:1-index[scope,'classify_skip_empty']['total_seconds']/index[scope,base]['total_seconds'] for base in ['generate','compact','classify']} for scope in ['all','bound','fallback']}
result=dict(rows=len(rows),passed=sum(r['passed'] for r in rows),classified_requests=len(ids),bypass_verified=len(ids),empty_skips=len(skipped),percase=percase,ratios=ratios)
(p/'audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
