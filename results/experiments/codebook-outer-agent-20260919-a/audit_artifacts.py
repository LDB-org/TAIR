import ast, hashlib, json, shlex, subprocess, sys
from pathlib import Path
root=Path('/Users/zacharyzcr/Projects/TAIR')
out=Path(sys.argv[1]).resolve()
assert not (out/'SHA256SUMS').exists()
rows=[json.loads(x) for x in (out/'rows.jsonl').read_text().splitlines()]
ids=sorted({h['request_id'] for r in rows for m in r['metrics'] for h in m.get('http_requests',[]) if h['route']!='/tokenize'})
code='''import json,sys
ids=json.loads(sys.stdin.read())
for line in open('/tmp/openjev-direct-events.jsonl'):
 try:e=json.loads(line)
 except ValueError:continue
 if e.get('event')=='classify' and any(str(e.get('request_id','')).startswith(i) for i in ids):print(json.dumps(e))
'''
ssh=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','rs-yuesheng-gpu-public']
raw=subprocess.check_output(ssh+[shlex.join(['docker','exec','-i','vllm-deepseek-v4-sm120-situ','python3','-c',code])],input=json.dumps(ids),text=True)
(out/'engine-classification-events.jsonl').write_text(raw)
events=[json.loads(x) for x in raw.splitlines()]
missing=[i for i in ids if not any(e.get('sampler_bypassed') and str(e['request_id']).startswith(i) for e in events)]
envcode='''import json,subprocess,urllib.request,hashlib
from pathlib import Path
print(json.dumps({'version':json.load(urllib.request.urlopen('http://127.0.0.1:8000/version')),'tokenizers':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('/model/tokenizer.json'),Path('/model/tokenizer_config.json')]}}))
'''
env=json.loads(subprocess.check_output(ssh+[shlex.join(['docker','exec','vllm-deepseek-v4-sm120-situ','python3','-c',envcode])],text=True))
env['container_started']=subprocess.check_output(ssh+[shlex.join(['docker','inspect','--format','{{.State.StartedAt}}','vllm-deepseek-v4-sm120-situ'])],text=True).strip()
env['gpu']=subprocess.check_output(ssh+[shlex.join(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'])],text=True).splitlines()
(out/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
suites=[]
for folder in sorted(out.glob('*/project-after')):
 p=subprocess.run(['/tmp/tair-test-venv-20260918/bin/python','-B','-m','unittest','-v'],cwd=folder,capture_output=True,text=True,timeout=20)
 suites.append({'case':folder.parent.name,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
(out/'independent-unittest.json').write_text(json.dumps(suites,indent=2)+'\n')
profiles={}
for arm in dict.fromkeys(r['arm'] for r in rows):
 rr=[r for r in rows if r['arm']==arm];ms=[m for r in rr for m in r['metrics']]
 profiles[arm]={'tasks':len(rr),'tokenizer_requests':sum(h['route']=='/tokenize' for m in ms for h in m.get('http_requests',[])),
 'local_routes':sum(bool(m.get('local_route')) for m in ms),'continuation_cache_hits':sum(bool(m.get('continuation_cache_hit')) for m in ms),
 'directory_redirects':sum(bool(m.get('directory_read_redirect')) for m in ms),
 'preparation_seconds':sum(m.get('stage_seconds',{}).get('generation_preparation',0)+m.get('stage_seconds',{}).get('cache_preparation',0) for m in ms),
 'by_case':{c:{'tasks':len(rs:=[r for r in rr if r['case']==c]),'seconds':sum(r['validated_seconds'] for r in rs)} for c in sorted({r['case'] for r in rr})},
 'by_round':{str(k):sum(r['validated_seconds'] for r in rr if r['round']==k) for k in [1,2]},
 'by_repeat':{str(k):sum(r['validated_seconds'] for r in rr if r['repeat']==k) for k in sorted({r['repeat'] for r in rr})}}
(out/'profile-summary.json').write_text(json.dumps(profiles,indent=2)+'\n')
source_checks={}
for p in (out/'sources').iterdir():
 matches=[q for d in ['benchmarks','deploy','integrations/pijit'] for q in (root/d).glob(p.name)]
 if matches:source_checks[p.name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'matches_current':p.read_bytes()==matches[0].read_bytes()}
verification={'tasks':len(rows),'all_passed':all(r['passed'] for r in rows),'usage_complete':all(r['usage_complete'] for r in rows),
 'test_integrity':all(r['test_integrity'] for r in rows),'independent_unittest_passed':all(s['returncode']==0 for s in suites),
 'classification_requests':len(ids),'missing_sampler_bypass_evidence':missing,'source_snapshots':source_checks}
(out/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
print(json.dumps(verification));print(json.dumps(profiles))
assert verification['all_passed'] and verification['usage_complete'] and verification['test_integrity'] and verification['independent_unittest_passed'] and not missing
