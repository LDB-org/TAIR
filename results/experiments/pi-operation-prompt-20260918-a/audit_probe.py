import json,subprocess,shlex,hashlib,shutil
from pathlib import Path
root=Path('/home/Kei/openjev')
for name in ['pi-all-classification-20260918-a','pi-operation-prompt-20260918-a']:
 p=root/'results/experiments'/name
 rows=[json.loads(l) for l in (p/'rows.jsonl').read_text().splitlines()]
 ids=[r.get('request_id') or r.get('response',{}).get('id') for r in rows if r['arm']!='typed']
 assert all(ids)
 code='import json\nids='+repr(ids)+'\nfor line in open("/tmp/openjev-direct-events.jsonl"):\n try:e=json.loads(line)\n except ValueError:continue\n if any(e.get("request_id","").startswith(i) for i in ids):print(line,end="")'
 result=subprocess.run(['ssh','rs-yuesheng-gpu-vps','docker exec vllm-deepseek-v4-sm120-situ python3 -c '+shlex.quote(code)],capture_output=True,text=True,check=True)
 events=[json.loads(l) for l in result.stdout.splitlines()]
 checks=[]
 for rid in ids:
  matched=[e for e in events if e['request_id'].startswith(rid) and e['event']=='classify']
  assert matched and all(e['sampler_bypassed'] and e['runner']=='v2' for e in matched),rid
  checks.append({'request_id':rid,'classify_events':len(matched),'sampler_bypassed':True})
 with (p/'engine-events.jsonl').open('x') as f:f.write(result.stdout)
 with (p/'verification.json').open('x') as f:json.dump({'calls_verified':len(checks),'checks':checks},f,indent=2)
 print(name,len(checks),'verified')
