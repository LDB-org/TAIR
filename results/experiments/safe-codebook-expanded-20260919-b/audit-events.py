import pathlib,json,subprocess
p=pathlib.Path('/Users/zacharyzcr/Projects/TAIR/results/experiments/safe-codebook-expanded-20260919-b')
rows=[json.loads(s) for s in (p/'rows.jsonl').read_text().splitlines()]
ids=[req['request_id'] for row in rows for req in row['response'].get('requests',[]) if req['request_id'].startswith('openjev-')]
raw=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','rs-yuesheng-gpu-public','docker exec vllm-deepseek-v4-sm120-situ tail -n 10000 /tmp/openjev-direct-events.jsonl'],text=True)
events=[json.loads(s) for s in raw.splitlines()];events=[e for e in events if any(e.get('request_id','').startswith(i) for i in ids)]
(p/'engine-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
print({'requests':len(ids),'events':len(events)})
