import hashlib,json,os,subprocess,time
from pathlib import Path
os.umask(0o077)
base=Path('/opt/openjev-toolcall/maintenance/dtype-20260918');base.mkdir(exist_ok=False)
name='vllm-deepseek-v4-sm120-situ'
target='/usr/local/lib/python3.12/dist-packages/vllm/openjev_direct_tools.py'
def call(*args):return subprocess.check_output(args,text=True).strip()
x=json.loads(call('docker','inspect',name))[0]
assert x['State']['Running']
(base/'inspect-private.json').write_text(json.dumps(x,indent=2))
call('docker','cp',name+':'+target,str(base/'original.py'))
original=(base/'original.py').read_bytes()
assert hashlib.sha256(original).hexdigest()=='b301b025299c1eb45ba9b6d2a94bcb2581b170235e9c947e21f71abbf16054a8'
needle=b'        processed[rows] = ordinary_logits'
assert original.count(needle)==1
patched=original.replace(needle,b'        processed = processed.to(dtype=ordinary_logits.dtype)\n'+needle)
compile(patched,str(target),'exec');(base/'patched.py').write_bytes(patched)
state={'container_id':x['Id'],'phase':'prepared','original_sha256':hashlib.sha256(original).hexdigest(),'patched_sha256':hashlib.sha256(patched).hexdigest(),'watchdog_was_active':call('systemctl','is-active','vllm-deepseek-health-watchdog.timer')=='active','started_at':time.time()}
def save(): (base/'state.json').write_text(json.dumps(state,indent=2))
save()
call('systemctl','stop','vllm-deepseek-health-watchdog.timer','vllm-deepseek-health-watchdog.service')
state['phase']='stopping';save()
call('docker','stop','--time','60',name)
call('docker','cp',str(base/'patched.py'),name+':'+target)
call('docker','cp',name+':'+target,str(base/'verified.py'))
assert (base/'verified.py').read_bytes()==patched
state['phase']='starting';save()
call('docker','start',name)
state['phase']='awaiting_validation';save()
print(json.dumps(state))
