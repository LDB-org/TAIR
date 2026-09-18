import json,subprocess,shlex,sys,shutil
from pathlib import Path
p=Path(sys.argv[1]); rows=[json.loads(l) for l in (p/'rows.jsonl').read_text().splitlines()]
records=[m for r in rows for m in r.get('metrics',[r.get('result',{})])]
ids=sorted({h['request_id'] for m in records for h in m.get('http_requests',[]) if h['route'] in ('/v1/completions','/v1/openjev/toolcall') and h.get('status')=='ok'})
code='import json\nids='+repr(ids)+'\nfor line in open("/tmp/openjev-direct-events.jsonl"):\n try:e=json.loads(line)\n except ValueError:continue\n if any(e.get("request_id", "").startswith(i) for i in ids):print(line,end="")'
r=subprocess.run(['ssh','-T','-o','BatchMode=yes','rs-yuesheng-gpu-vps','docker exec vllm-deepseek-v4-sm120-situ python3 -c '+shlex.quote(code)],capture_output=True,text=True,check=True)
events=[json.loads(l) for l in r.stdout.splitlines()]
checks=[]
for rid in ids:
 matches=[e for e in events if e.get('event')=='classify' and e['request_id'].startswith(rid)]
 assert matches and all(e.get('sampler_bypassed') and e.get('runner')=='v2' for e in matches),rid
 checks.append({'request_id':rid,'sampler_bypassed':True})
hits=[m for m in records if m.get('jit_hit')]
assert all(not m['http_requests'] and m['accounting']['inference_requests']==0 and m['generated_argument_tokens']==0 and m['classification_control_records']==0 for m in hits)
(p/'engine-events.jsonl').write_text(r.stdout)
(p/'audit.json').write_text(json.dumps({'classification_checks':checks,'jit_hits_without_http':len(hits)},indent=2))
shutil.copyfile(__file__,p/'audit-script.py')
print('verified',len(checks),'model classifications;',len(hits),'JIT edits without HTTP')
