import hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path('/Users/zacharyzcr/Projects/TAIR')
out=ROOT/'results/experiments/plan-budget-real-agent-20260920-b'
out.mkdir(exist_ok=False)
shutil.copyfile(__file__,out/'runner.py')
for rel in ['integrations/pijit/bridge.py','integrations/pijit/extension.ts','integrations/pijit/launch.mjs','integrations/pijit/plan_executor.mjs','deploy/vllm_direct_tools.py']:
 p=out/'sources'/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,p)
source='from pathlib import Path\n\nSAMPLE = """'+''.join(f'local file line {i:04d}\n' for i in range(200))+'''"""

def write_text(path, content):
    Path(path).write_text(content, encoding="utf-8")

def read_text(path):
    return Path(path).read_text(encoding="utf-8")
'''
rows=[]
with tempfile.TemporaryDirectory(prefix='tair-real-budget-') as tmp:
 root=Path(tmp);work=root/'work';work.mkdir()
 env={k:v for k,v in os.environ.items() if not k.startswith(('PIJIT_','TAIR_'))}
 env.update(PIJIT_SSH_HOST='rs-yuesheng-gpu-public',PIJIT_PYTHON=sys.executable,PIJIT_STATE_DIR=str(root/'state'))
 previous=0
 try:
  for name,files in [('cold',['files_a.py','files_b.py']),('warm',['files_c.py','files_d.py'])]:
   check='import importlib; '+ '; '.join(f'm=importlib.import_module({f[:-3]!r}); m.write_text("roundtrip.txt", m.SAMPLE+"中文测试\\n"); assert m.read_text("roundtrip.txt")==m.SAMPLE+"中文测试\\n"' for f in files)
   prompt=f'Create both {files[0]} and {files[1]} with the exact Python source below, preserving every line. Then use bash to execute this verification: python3 -c {__import__("shlex").quote(check)}. Put both independent writes and the bash verification into ONE plan when possible. Do not read existing files. Use available cached content if identical. Do not create other source files.\n```python\n'+source+'```'
   (out/f'{name}-prompt.txt').write_text(prompt)
   start=time.perf_counter();done=subprocess.run(['node',str(ROOT/'integrations/pijit/launch.mjs'),'--plan-only','-p',prompt],cwd=work,env=env,capture_output=True,text=True,timeout=240)
   elapsed=time.perf_counter()-start
   (out/f'{name}-stdout.txt').write_text(done.stdout);(out/f'{name}-stderr.txt').write_text(done.stderr)
   records=[json.loads(l) for p in (root/'state').glob('workspaces/*/metrics.jsonl') for l in p.read_text().splitlines()]
   current=records[previous:];previous=len(records)
   chats=[r for r in current if r.get('action')=='chat']
   row=dict(name=name,seconds=elapsed,returncode=done.returncode,records=current)
   rows.append(row)
   exact=all((work/f).exists() and (work/f).read_text()==source for f in files)
   verify=subprocess.run([sys.executable,'-c',check],cwd=work,capture_output=True,text=True) if exact else None
   row.update(exact_files=exact,independent_function_check=verify is not None and verify.returncode==0,generated_tokens=sum(r.get('generated_argument_tokens',0) for r in chats),control_records=sum(r.get('classification_control_records',0) for r in chats),reuse_hit=any(r.get('reused_content_ids') for r in chats),plans=[dict(steps=r.get('plan_step_names'),generated=r.get('generated_argument_tokens'),budget=r.get('plan_token_budget')) for r in chats])
   (out/'report.json').write_text(json.dumps(rows,indent=2))
   print(json.dumps({k:v for k,v in row.items() if k!='records'}),flush=True)
   assert done.returncode==0 and row['independent_function_check']
   assert chats and all(r.get('available_tools')==['plan'] and r.get('requested_plan_tokens')==17408 for r in chats)
 finally:
  for p in work.iterdir():
   if p.is_file():shutil.copyfile(p,out/p.name)
  for p in (root/'state').glob('workspaces/*/*.jsonl'):shutil.copyfile(p,out/p.name)
  for p in (root/'state/agent/sessions').rglob('*.jsonl'):shutil.copyfile(p,out/('session-'+p.name))
  files=sorted(p for p in out.rglob('*') if p.is_file())
  (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))
