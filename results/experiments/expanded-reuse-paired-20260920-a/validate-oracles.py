import sys,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,'benchmarks')
from expanded_reuse_cases import cases
passed=0;negatives=0
for job in cases():
 group=job['group'];changed=job['phase']=='changed'
 if group=='jsonl':
  source='import json\ndef pairs(items):\n d={}\n for k,v in items:\n  if k in d: raise ValueError(k)\n  d[k]=v\n return d\ndef parse_jsonl(text):\n return [json.loads(s'+(',object_pairs_hook=pairs' if changed else '')+') for s in text.splitlines() if s.strip()]\n'
 elif group=='unique':
  source='export function uniqueStrings(values){ const seen=new Set();return values.filter(s=>{const k='+('s.toLowerCase()' if changed else 's')+';if(seen.has(k))return false;seen.add(k);return true;});}\n'
 elif group=='totals':source="SELECT user_id,SUM(amount) AS total FROM events WHERE status='posted' GROUP BY user_id "+('HAVING SUM(amount)>0 ' if changed else '')+'ORDER BY user_id;'
 elif group=='intervals':source='def merge_intervals(items):\n out=[]\n for a,b in sorted(items):\n  if out and a '+('<' if changed else '<=')+' out[-1][1]: out[-1][1]=max(out[-1][1],b)\n  else:out.append([a,b])\n return out\n'
 else:
  import json
  data=json.loads(job['files']['service.json']);data['service']['port']=8443 if job['id']=='config_1' else 9443;source=json.dumps(data)
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);(root/job['primary_file']).write_text(source)
  result=subprocess.run([sys.executable,'-c',job['check']],cwd=root,capture_output=True,text=True)
  assert result.returncode==0,(job['id'],result.stderr);passed+=1
  (root/job['primary_file']).write_text('')
  result=subprocess.run([sys.executable,'-c',job['check']],cwd=root,capture_output=True,text=True)
  assert result.returncode!=0,job['id'];negatives+=1
print('Reference accepted:',passed,'empty output rejected:',negatives)
