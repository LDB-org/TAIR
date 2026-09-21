import hashlib,json,pathlib,subprocess,urllib.request
root=pathlib.Path('/tmp/tair-prefix-cache-20260920-a');container='vllm-deepseek-v4-sm120-situ';target='/usr/local/lib/python3.12/dist-packages/vllm/openjev_direct_tools.py'
m=json.loads((root/'manifest.json').read_text())
metrics=urllib.request.urlopen('http://127.0.0.1:8000/metrics',timeout=10).read().decode()
active=[line for line in metrics.splitlines() if line.startswith(('vllm:num_requests_running{','vllm:num_requests_waiting{'))]
assert active and all(float(line.rsplit(' ',1)[-1])==0 for line in active),active
subprocess.run(['docker','cp',container+':'+target,str(root/'rollback.py')],check=True)
assert hashlib.sha256((root/'rollback.py').read_bytes()).hexdigest()==m['previous_sha256']
assert hashlib.sha256((root/'candidate.py').read_bytes()).hexdigest()==m['candidate_sha256']
compile((root/'candidate.py').read_text(),target,'exec')
subprocess.run(['docker','cp',str(root/'candidate.py'),container+':'+target],check=True)
subprocess.run(['docker','exec',container,'python3','-m','py_compile',target],check=True)
print(json.dumps({'idle':active,'backup':str(root/'rollback.py'),'installed_sha256':m['candidate_sha256']}),flush=True)
subprocess.run(['docker','restart','-t','30',container],check=True)
