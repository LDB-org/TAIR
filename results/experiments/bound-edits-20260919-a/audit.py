import json, pathlib, subprocess
root=pathlib.Path('/Users/zacharyzcr/Projects/TAIR')
p=root/'results/experiments/bound-edits-20260919-a'
rows=[json.loads(s) for s in (p/'rows.jsonl').read_text().splitlines()]
assert len(rows)==54 and len({(r['arm'],r['case'],r['repeat']) for r in rows})==54
raw=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','rs-yuesheng-gpu-public','docker exec vllm-deepseek-v4-sm120-situ tail -n 2000 /tmp/openjev-direct-events.jsonl'],text=True)
ids=[r['responses'][0]['id'] for r in rows if r['arm']=='classify']
events=[json.loads(s) for s in raw.splitlines()]
events=[e for e in events if any(e.get('request_id','').startswith(i) for i in ids)]
assert all(any(e['event']=='classify' and e.get('sampler_bypassed') and e.get('request_id','').startswith(i) for e in events) for i in ids)
(p/'engine-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
summary=json.loads((p/'summary.json').read_text())
percase=[]
for name in sorted({r['case'] for r in rows}):
    item={'case':name}
    for arm in ['generate','compact','classify']:
        group=[r for r in rows if r['case']==name and r['arm']==arm]
        item[arm]=sum(r['total_seconds'] for r in group)/len(group)
    percase.append(item)
index={(r['scope'],r['arm']):r for r in summary}
ratios={scope:dict(classify_vs_full_saved=1-index[scope,'classify']['total_seconds']/index[scope,'generate']['total_seconds'],
    classify_vs_compact_saved=1-index[scope,'classify']['total_seconds']/index[scope,'compact']['total_seconds']) for scope in ['all','bound','fallback']}
result=dict(rows=len(rows),passed=sum(r['passed'] for r in rows),classified_requests=len(ids),bypass_verified=len(ids),percase=percase,ratios=ratios)
(p/'audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
