import json,subprocess,shlex,sys,shutil
from pathlib import Path
p=Path(sys.argv[1]); rows=[json.loads(l) for l in (p/'rows.jsonl').read_text().splitlines()]
ids=[r['response']['id'] for r in rows if r['arm']=='classify']
code='import json\nids='+repr(ids)+'\nfor line in open("/tmp/openjev-direct-events.jsonl"):\n try: e=json.loads(line)\n except ValueError: continue\n if any(e.get("request_id", "").startswith(i) for i in ids): print(line,end="")'
r=subprocess.run(['ssh','-T','-o','BatchMode=yes','rs-yuesheng-gpu-vps','docker exec vllm-deepseek-v4-sm120-situ python3 -c '+shlex.quote(code)],capture_output=True,text=True,check=True)
events=[json.loads(l) for l in r.stdout.splitlines()]
checks=[]
for rid in ids:
 matches=[e for e in events if e.get('event')=='classify' and e['request_id'].startswith(rid)]
 assert matches and all(e.get('sampler_bypassed') and e.get('runner')=='v2' for e in matches),rid
 checks.append({'request_id':rid,'sampler_bypassed':True})
(p/'engine-events.jsonl').write_text(r.stdout)
(p/'audit.json').write_text(json.dumps(checks,indent=2))
shutil.copyfile(__file__,p/'audit-script.py')
print('verified',len(checks),p)
