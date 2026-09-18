import json,subprocess,shlex
from pathlib import Path
p=Path('results/experiments/general-pijit-20260918-exclusive')
rows=[json.loads(l) for l in (p/'rows.jsonl').read_text().splitlines()]
ids=[m['request_id'] for r in rows if r['arm']=='preset' for m in r['metrics'] if m['action']=='chat']
code='import json\nids='+repr(ids)+'\nfor line in open("/tmp/openjev-direct-events.jsonl"):\n try:e=json.loads(line)\n except ValueError:continue\n if any(e.get("request_id", "").startswith(i) for i in ids):print(line,end="")'
r=subprocess.run(['ssh','-T','-o','BatchMode=yes','rs-yuesheng-gpu-vps','docker exec vllm-deepseek-v4-sm120-situ python3 -c '+shlex.quote(code)],capture_output=True,text=True,check=True)
events=[json.loads(l) for l in r.stdout.splitlines()]
checks=[]
for rid in ids:
 matches=[e for e in events if e.get('event')=='classify' and e['request_id'].startswith(rid)]
 assert matches and all(e.get('sampler_bypassed') for e in matches),rid
 checks.append({'request_id':rid,'sampler_bypassed':True})
(p/'engine-events.jsonl').write_text(r.stdout);(p/'audit.json').write_text(json.dumps(checks,indent=2));print('Verified',len(checks),'classification calls')
