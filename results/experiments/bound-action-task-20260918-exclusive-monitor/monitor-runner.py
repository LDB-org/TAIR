import json,os,subprocess,threading,time,urllib.request
from pathlib import Path
p=Path('results/experiments/bound-action-task-20260918-exclusive-monitor');p.mkdir(exist_ok=False)
stop=threading.Event()
def monitor():
 with (p/'load.jsonl').open('x') as f:
  while not stop.is_set():
   row={'time':time.time()}
   try:
    with urllib.request.urlopen('http://127.0.0.1:18907/metrics',timeout=5) as r:lines=r.read().decode().splitlines()
    row['load']={k:sum(float(l.rsplit(' ',1)[1]) for l in lines if l.startswith('vllm:'+k+'{')) for k in ['num_requests_running','num_requests_waiting']}
   except Exception as e:row['error']=repr(e)
   f.write(json.dumps(row)+'\n');f.flush();stop.wait(1)
t=threading.Thread(target=monitor);t.start()
try:
 result=subprocess.run(['.venv/bin/python','benchmarks/benchmark_bound_action_task.py','--out','results/experiments/bound-action-task-20260918-exclusive','--repeats','5'],env=dict(os.environ,PIJIT_URL='http://127.0.0.1:18907'))
finally:stop.set();t.join()
raise SystemExit(result.returncode)
