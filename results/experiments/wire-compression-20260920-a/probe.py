import sys,os,json,hashlib,socket,subprocess,time,urllib.request,uuid,random,shutil
from pathlib import Path
from contextlib import contextmanager,ExitStack
root=Path('/Users/zacharyzcr/Projects/TAIR');sys.path.insert(0,str(root/'benchmarks'))
from benchmark_tokenizer_preparation import bridge
from benchmark_prefix_cache import freeze
@contextmanager
def tunnel(out,compressed):
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 with (out/('ssh-'+str(compressed)+'.log')).open('w') as log:
  cmd=['ssh','-N','-S','none','-o','Compression='+('yes' if compressed else 'no'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public']
  process=subprocess.Popen(cmd,stderr=log)
  try:
   url=f'http://127.0.0.1:{port}'
   for _ in range(50):
    if process.poll() is not None:raise RuntimeError('tunnel failed')
    try:urllib.request.urlopen(url+'/health',timeout=2).close();break
    except OSError:time.sleep(.2)
   else:raise RuntimeError('unreachable')
   yield url
  finally:
   process.terminate();process.wait(timeout=10)
out=root/'results/experiments/wire-compression-20260920-a';out.mkdir(exist_ok=False)
shutil.copyfile(__file__,out/'probe.py')
snapshot=Path.home()/'.cache/tair/tokenizer-dsv4-20260920';raw=(snapshot/'manifest.json').read_bytes()
os.environ.update(PIJIT_LOCAL_TOKENIZER=str(snapshot),PIJIT_TOKENIZER_REVISION=hashlib.sha256(raw).hexdigest())
schema={'type':'object','properties':{'content':{'const':'OK'}},'required':['content'],'additionalProperties':False}
tail=[[{'role':'assistant','content':'A'},{'role':'user','content':'Return only {"content":"OK"}. Schema: '+json.dumps(schema)}]]
nonce=uuid.uuid4().hex
messages=[{'role':'system','content':'Wire experiment '+nonce+'\n'+'def read_text(path): return path.read_text(encoding="utf-8")\n'*1000},{'role':'user','content':'Select A. The next response must be OK.'}]
rows=[]
try:
 with ExitStack() as stack:
  urls={arm:stack.enter_context(tunnel(out,arm)) for arm in [False,True]}
  os.environ['PIJIT_URL']=urls[False]
  prefix,suffix=bridge.continuation_tokens(messages,tail)
  payload=dict(prompt_ids=prefix,candidate_ids=bridge.tokenize_label('A'),continuations=suffix,tools=[dict(name='plan',parameters=schema)],max_tokens=64,plan_budget=True,cache_salt=nonce)
  data=json.dumps(payload).encode();(out/'payload.json').write_bytes(data)
  schedule=[False,True];rng=random.Random(731)
  for _ in range(10):
   pair=[False,True];rng.shuffle(pair);schedule.extend(pair)
  (out/'manifest.json').write_text(json.dumps(dict(schedule=schedule,payload_bytes=len(data),prompt_tokens=len(prefix),payload_sha256=hashlib.sha256(data).hexdigest(),method='Identical serialized request bytes and shared session salt; first two calls warmups excluded from timed comparison but retained. Ten random-order pairs, C1, forced OK only; SSH compression is the sole variable. No other test inference runs concurrently. Not Agent quality evidence.'),indent=2))
  for i,arm in enumerate(schedule):
   request=urllib.request.Request(urls[arm]+'/v1/openjev/toolcall',data=data,headers={'Content-Type':'application/json'})
   start=time.perf_counter();result=json.load(urllib.request.urlopen(request,timeout=195));elapsed=time.perf_counter()-start
   row=dict(index=i,compressed=arm,warmup=i<2,seconds=elapsed,engine_seconds=result['seconds'],cached_tokens=result['decision']['cached_prefix_tokens'],correct=result['call']=={'name':'plan','arguments':{'content':'OK'}},result=result)
   rows.append(row);(out/'report.json').write_text(json.dumps(rows,indent=2));print(json.dumps({k:v for k,v in row.items() if k!='result'}),flush=True)
   assert row['correct']
finally:freeze(out)
