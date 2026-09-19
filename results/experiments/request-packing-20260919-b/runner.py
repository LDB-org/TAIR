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
  env=dict({k:v for k,v in os.environ.items() if not k.startswith(('PIJIT_', 'TAIR_'))},PATH='/tmp/tair-pi-0.85.1/node_modules/.bin:/tmp/tair-test-venv-20260918/bin:'+os.environ['PATH'],PIJIT_PYTHON='/tmp/tair-test-venv-20260918/bin/python')
  subprocess.run(['/tmp/tair-test-venv-20260918/bin/python','-u','benchmarks/benchmark_request_packing.py','--url',url,'--out','results/experiments/request-packing-20260919-b','--repeats','2'],env=env,check=True)
 finally:
  tunnel.terminate()
  try:tunnel.wait(timeout=10)
  except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
  print('Temporary SSH tunnel closed',flush=True)
