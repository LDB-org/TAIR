import hashlib, json, os, shlex, socket, subprocess, time, urllib.request
from pathlib import Path
root=Path('/Users/zacharyzcr/Projects/TAIR')
out=root/'results/experiments/mechanism-ablation-20260919-a'
out.mkdir(exist_ok=False)
ssh=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','rs-yuesheng-gpu-public']
code='''import hashlib,importlib.metadata,json,urllib.request
from pathlib import Path
print(json.dumps({'version':json.load(urllib.request.urlopen('http://127.0.0.1:8000/version')),'xgrammar':importlib.metadata.version('xgrammar'),'tokenizers':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('/model/tokenizer.json'),Path('/model/tokenizer_config.json')]}}))'''
environment=json.loads(subprocess.check_output(ssh+[shlex.join(['docker','exec','vllm-deepseek-v4-sm120-situ','python3','-c',code])],text=True))
environment['container_started']=subprocess.check_output(ssh+['docker inspect --format "{{.State.StartedAt}}" vllm-deepseek-v4-sm120-situ'],text=True).strip()
environment['gpu']=subprocess.check_output(ssh+['nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader'],text=True).splitlines()
(out/'environment-before.json').write_text(json.dumps(environment,indent=2))
revision=':'.join(environment['tokenizers'][p] for p in ['/model/tokenizer.json','/model/tokenizer_config.json'])
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
command=['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public']
python='/tmp/tair-test-venv-20260918/bin/python'
base={k:v for k,v in os.environ.items() if not k.startswith('PIJIT_')}
base.update(PATH='/tmp/tair-pi-0.85.1/node_modules/.bin:/tmp/tair-test-venv-20260918/bin:'+os.environ['PATH'],PIJIT_PYTHON=python)
with subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True) as tunnel:
 try:
  url=f'http://127.0.0.1:{port}'
  for attempt in range(100):
   if tunnel.poll() is not None:raise RuntimeError(tunnel.stderr.read())
   try:
    with urllib.request.urlopen(url+'/health',timeout=1) as response:
     if response.status==200:break
   except Exception:time.sleep(.2)
  else:raise RuntimeError('Tunnel health check failed')
  env=dict(base,PIJIT_URL=url)
  stages=[('ideal',['benchmarks/benchmark_ideal_classification.py','--url',url,'--constrain-json','--repeats','3']),
          ('edits',['benchmarks/benchmark_native_codebook.py','--url',url,'--repeats','3']),
          ('replay',['benchmarks/benchmark_schema_jit_edits.py']),
          ('agent',['benchmarks/benchmark_mechanism_ablation.py','--url',url,'--tokenizer-revision',revision,'--repeats','1','--timeout','120'])]
  codes={}
  for name,args in stages:
   print('Starting '+name,flush=True)
   with (out/(name+'-stdout.txt')).open('w') as stdout,(out/(name+'-stderr.txt')).open('w') as stderr:
    p=subprocess.run([python,'-u',*args,'--out',str(out/name)],cwd=root,env=env,stdout=stdout,stderr=stderr)
   codes[name]=p.returncode
   (out/'stage-exit-codes.json').write_text(json.dumps(codes,indent=2))
   print('Finished '+name+' exit='+str(p.returncode),flush=True)
   if not (out/name/'rows.jsonl').exists():raise RuntimeError('Missing trial records for '+name)
 finally:
  tunnel.terminate()
  try:tunnel.wait(timeout=10)
  except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
  print('Temporary SSH tunnel closed',flush=True)
