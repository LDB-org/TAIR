import json, subprocess, pathlib, hashlib
root=pathlib.Path('/Users/zacharyzcr/Projects/TAIR')
p=root/'results/experiments/engine-plan-20260919-a'
rows=[json.loads(s) for s in (p/'rows.jsonl').read_text().splitlines()]
raw=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','rs-yuesheng-gpu-public','docker exec vllm-deepseek-v4-sm120-situ tail -n 2000 /tmp/openjev-direct-events.jsonl'],text=True)
ids=[response.get('request_id',response.get('id')) for row in rows for response in row['responses']]
events=[json.loads(s) for s in raw.splitlines()]
events=[e for e in events if any(e.get('request_id','').startswith(i) for i in ids if i)]
(p/'engine-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
checks=[]
for row in rows:
    if row['arm']!='engine': continue
    rid=row['responses'][0]['request_id']
    ev=[e for e in events if e.get('request_id','').startswith(rid)]
    paused=next(e for e in ev if e['event']=='retire_worker_slot')
    resumed=next(e for e in ev if e['event']=='resume')
    checks.append(dict(request_id=rid, sampler_bypassed=all(e['sampler_bypassed'] for e in ev if e['event']=='classify'),
        has_classify=any(e['event']=='classify' for e in ev), kv_equal=paused['block_ids']==resumed['block_ids'],
        computed_tokens_equal=paused['computed_tokens']==resumed['computed_tokens']))
assert len(checks)==18 and all(all(c[k] for k in ['sampler_bypassed','has_classify','kv_equal','computed_tokens_equal']) for c in checks)
inputs=json.loads((p/'inputs.json').read_text())
logical={}
for arm in ['generate','split','engine']:
    total=0
    for row in rows:
        if row['arm']!=arm: continue
        data=inputs['prepared'][row['case']]
        if arm=='generate': total+=row['responses'][0]['usage']['prompt_tokens']
        elif arm=='split': total+=sum(r['usage']['prompt_tokens'] for r in row['responses'])
        else:
            selected=row['responses'][0]['decision']['index']
            total+=len(data['prefix'])+len(data['tails'][selected])
    logical[arm]=total
summary=json.loads((p/'summary.json').read_text())
by={r['arm']:r for r in summary}
audit=dict(engine_checks=checks, logical_input_tokens=logical,
    engine_vs_split_saved_fraction=1-by['engine']['seconds']/by['split']['seconds'],
    engine_vs_generate_extra_fraction=by['engine']['seconds']/by['generate']['seconds']-1,
    note='Logical input counts do not measure uncached GPU work. Forward passes not counted. All 54 trials retained.')
(p/'audit.json').write_text(json.dumps(audit,indent=2))
print(json.dumps({k:v for k,v in audit.items() if k!='engine_checks'},indent=2))
