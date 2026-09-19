import os,socket,subprocess,time,urllib.request
from pathlib import Path
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
command=['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public']
with subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True) as tunnel:
 try:
  url=f'http://127.0.0.1:{port}'
  for attempt in range(100):
   if tunnel.poll() is not None: raise RuntimeError(tunnel.stderr.read())
   try:
    with urllib.request.urlopen(url+'/health',timeout=1) as response:
     if response.status==200: break
   except Exception:time.sleep(.2)
  else:raise RuntimeError('Tunnel health check failed')
  env=dict(os.environ,PATH='/tmp/tair-pi-0.85.1/node_modules/.bin:/tmp/tair-test-venv-20260918/bin:'+os.environ['PATH'],PIJIT_PYTHON='/tmp/tair-test-venv-20260918/bin/python')
  subprocess.run(['/tmp/tair-test-venv-20260918/bin/python','-u','benchmarks/benchmark_codebook_agent.py','--url',url,'--out','results/experiments/expanded-context-agent-20260919-a','--timeout','180','--suite','expanded','--repeats','2','--plan-context-comparison','--tokenizer-revision','c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b:6ac8c8dc065ed118161d02dd532749ae3f52c243deac27872134fae2f50d8547'],env=env,check=True)
 finally:
  tunnel.terminate()
  try:tunnel.wait(timeout=10)
  except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
  print('Temporary SSH tunnel closed',flush=True)
