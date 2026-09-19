import hashlib,json,os,shlex,subprocess,sys
from pathlib import Path
root=Path('/Users/zacharyzcr/Projects/TAIR')
out=Path(sys.argv[1]).resolve()
assert not (out/'SHA256SUMS').exists()
ids=set()
for section in ['edits','replay','agent']:
 for line in (out/section/'rows.jsonl').read_text().splitlines():
  row=json.loads(line)
  for m in row.get('metrics',[row.get('result',{})]):
   for h in m.get('http_requests',[]):
    if h['route']!='/tokenize' and h.get('status')=='ok' and h.get('request_id'):ids.add(h['request_id'])
for line in (out/'ideal/rows.jsonl').read_text().splitlines():
 r=json.loads(line)
 if r['arm']=='classify' and r.get('response'):ids.add(r['response']['id'])
ssh=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','rs-yuesheng-gpu-public']
code='''import json,sys
ids=set(json.loads(sys.stdin.read()))
for line in open('/tmp/openjev-direct-events.jsonl'):
 try:e=json.loads(line)
 except ValueError:continue
 if e.get('event')=='classify' and any(str(e.get('request_id','')).startswith(i) for i in ids):print(json.dumps(e))
'''
raw=subprocess.check_output(ssh+[shlex.join(['docker','exec','-i','vllm-deepseek-v4-sm120-situ','python3','-c',code])],input=json.dumps(sorted(ids)),text=True)
(out/'engine-classification-events.jsonl').write_text(raw)
events=[json.loads(l) for l in raw.splitlines()]
missing=[i for i in sorted(ids) if not any(e.get('sampler_bypassed') and str(e.get('request_id','')).startswith(i) for e in events)]
envcode='''import hashlib,importlib.metadata,json,urllib.request
from pathlib import Path
print(json.dumps({'version':json.load(urllib.request.urlopen('http://127.0.0.1:8000/version')),'xgrammar':importlib.metadata.version('xgrammar'),'tokenizers':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('/model/tokenizer.json'),Path('/model/tokenizer_config.json')]}}))'''
env=json.loads(subprocess.check_output(ssh+[shlex.join(['docker','exec','vllm-deepseek-v4-sm120-situ','python3','-c',envcode])],text=True))
env['container_started']=subprocess.check_output(ssh+['docker inspect --format "{{.State.StartedAt}}" vllm-deepseek-v4-sm120-situ'],text=True).strip()
env['gpu']=subprocess.check_output(ssh+['nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader'],text=True).splitlines()
(out/'environment-after.json').write_text(json.dumps(env,indent=2))
before=json.loads((out/'environment-before.json').read_text())
suites=[]
for p in sorted((out/'agent').glob('*/project-after')):
 try:
  proc=subprocess.run([sys.executable,'-B','-m','unittest','-v'],cwd=p,env=dict(os.environ,PATH='/tmp/tair-test-venv-20260918/bin:'+os.environ['PATH']),capture_output=True,text=True,timeout=20)
  suites.append({'case':p.parent.name,'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
 except subprocess.TimeoutExpired as e:suites.append({'case':p.parent.name,'returncode':None,'error':'unittest timeout'})
(out/'independent-unittest.json').write_text(json.dumps(suites,indent=2))
hashes=json.loads((out/'source-sha256.json').read_text())
hashes.update(json.loads((out/'agent/manifest.json').read_text())['source_sha256'])
source_checks={f:hashlib.sha256((root/f).read_bytes()).hexdigest()==digest for f,digest in hashes.items()}
rows=[json.loads(l) for l in (out/'agent/rows.jsonl').read_text().splitlines()]
passed={f"{r['repeat']}-{r['case']}-{r['arm']}-{r['round']}" for r in rows if r['passed']}
verification={'classification_requests':len(ids),'missing_sampler_bypass_evidence':missing,'scope':'All completed non-tokenize TAIR requests and nine formal ideal classification requests; no usage claims for incomplete requests.',
 'environment_unchanged':before==env,'source_checks':source_checks,'independent_unittest_cases':len(suites),
 'independent_unittest_failed':[s['case'] for s in suites if s['returncode']!=0],
 'passed_task_unittest_failures':[s['case'] for s in suites if s['returncode']!=0 and s['case'] in passed]}
(out/'verification.json').write_text(json.dumps(verification,indent=2))
print(json.dumps(verification))
assert not missing and before==env and all(source_checks.values()) and not verification['passed_task_unittest_failures']
