import hashlib,importlib.util,json,os,shutil,sqlite3,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path('/Users/zacharyzcr/Projects/TAIR');work=Path('/Users/zacharyzcr/测试');state=Path.home()/'.pijit'
run='classification-repeat-ten-20260920-final';out=ROOT/'results/experiments'/run;out.mkdir(exist_ok=False)
dest=work/run;dest.mkdir(exist_ok=False)
bookdir=state/'workspaces'/hashlib.sha256(str(work.resolve()).encode()).hexdigest()[:20];book=bookdir/'tool-plan-codebook.sqlite3'
backup=Path('/tmp')/(run+'-book-before.sqlite3')
with sqlite3.connect(book.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(backup) as dst:src.backup(dst)
def inventory():
 with sqlite3.connect(book.as_uri()+'?mode=ro',uri=True) as c:
  return [dict(id=r[0],source_sha256=r[1],reuse_count=r[2]) for r in c.execute('select id,source_sha256,reuse_count from entries order by seq')]
def records():
 p=bookdir/'metrics.jsonl';return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
jobs=[('textio','Provide write_text(path, text) and read_text(path). Use pathlib and UTF-8. write_text overwrites the file, read_text returns the full string. Do not create parent directories. No top-level execution.'),('jsonio','Provide save_json(path, data) and load_json(path). Use UTF-8, ensure_ascii=False, indent=2, and append one final newline when saving. Preserve nested objects, arrays and Unicode. No top-level execution.'),('csvio','Provide write_rows(path, rows) and read_rows(path). Use csv.writer and csv.reader, UTF-8, newline="". read_rows returns list of lists of strings. Support commas and embedded newlines in cells. No top-level execution.'),('hashing','Provide sha256_file(path). Return lowercase hexadecimal SHA-256 of the binary file, streaming in chunks of 65536 bytes. Use hashlib. No top-level execution.'),('stats','Provide summarize(values). Return a dict with keys count, total, mean, minimum, maximum. Empty input yields count=0, total=0, mean=None, minimum=None, maximum=None. For nonempty numeric input use arithmetic mean and built-in min/max. No top-level execution.')]
def validate(kind,path):
 spec=importlib.util.spec_from_file_location('checked_'+path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 f=dest/'validation-data.tmp'
 if kind=='textio':
  for text in ['中文\nhello\n','', 'overwrite']:m.write_text(f,text);assert m.read_text(f)==text and f.read_text()==text
 elif kind=='jsonio':
  data={'中文':[1,True,None,{'nested':'值'}]};m.save_json(f,data);assert m.load_json(f)==data;assert f.read_text()==json.dumps(data,ensure_ascii=False,indent=2)+'\n'
 elif kind=='csvio':
  rows=[['a,b','中文'],['line\nbreak','"quoted"']];m.write_rows(f,rows);assert m.read_rows(f)==rows
 elif kind=='hashing':
  for b in [b'',bytes(range(256))*1000]:f.write_bytes(b);assert m.sha256_file(f)==hashlib.sha256(b).hexdigest()
 else:
  assert m.summarize([])==dict(count=0,total=0,mean=None,minimum=None,maximum=None)
  assert m.summarize([-2,0,8])==dict(count=3,total=6,mean=2,minimum=-2,maximum=8)
 if f.exists():f.unlink()
env={k:v for k,v in os.environ.items() if not k.startswith(('PIJIT_','TAIR_'))}
env.update(PIJIT_STATE_DIR=str(state),PIJIT_SSH_HOST='rs-yuesheng-gpu-public',PIJIT_PYTHON=sys.executable)
shutil.copyfile(__file__,out/'runner.py')
before=inventory();(out/'book-before.json').write_text(json.dumps(before,indent=2));rows=[]
try:
 for number,(kind,spec) in enumerate(jobs[:1]*10,1):
  filename=f'{run}/{number:02d}_{kind}.py';target=work/filename
  prompt=f'Create a Python standard-library-only module at {filename}. {spec} Then run python3 -m py_compile {filename} using bash. Put the write and compilation check in one plan if possible. Do not modify other files. Report completion briefly.'
  (out/f'{number:02d}-prompt.txt').write_text(prompt)
  round_before=inventory();offset=len(records());start=time.perf_counter()
  try:
   done=subprocess.run(['node',str(ROOT/'integrations/pijit/launch.mjs'),'--plan-only','-p',prompt],cwd=work,env=env,capture_output=True,text=True,timeout=150)
   elapsed=time.perf_counter()-start;(out/f'{number:02d}-stdout.txt').write_text(done.stdout);(out/f'{number:02d}-stderr.txt').write_text(done.stderr)
   current=records()[offset:];chats=[r for r in current if r.get('action')=='chat'];completions=[r for r in current if r.get('action')=='tool_plan_complete']
   row=dict(task=number,kind=kind,repeat=True,seconds=elapsed,returncode=done.returncode,records=current)
   try:validate(kind,target);row['correct']=True
   except Exception:row.update(correct=False,validation_error=traceback.format_exc())
   row.update(reuse_selected=any(r.get('reused_content_ids') for r in chats),reuse_executed=any(r.get('cache_hit') and r.get('status')=='ok' for r in completions),generated_tokens=sum(r.get('accounting',{}).get('known_generated_argument_tokens',0) for r in chats),input_tokens=sum(r.get('accounting',{}).get('known_input_tokens',0) for r in chats),control_records=sum(r.get('accounting',{}).get('known_classification_control_records',0) for r in chats),inference_requests=sum(r.get('accounting',{}).get('inference_requests',0) for r in chats),usage_complete=all(r.get('accounting',{}).get('usage_complete',False) for r in chats),candidates=[r.get('candidate_count') for r in chats],outcomes=[r.get('cache_outcome') for r in chats],admitted=sum(r.get('admission_count',0) for r in completions),plan_only=bool(chats) and all(r.get('available_tools')==['plan'] for r in chats))
  except Exception:row=dict(task=number,kind=kind,correct=False,error=traceback.format_exc())
  row.update(book_entries_before=len(round_before),book_entries_after=len(inventory()),book_after=inventory());rows.append(row);(out/'report.json').write_text(json.dumps(rows,indent=2));print(json.dumps({k:v for k,v in row.items() if k not in ('records','book_after')}),flush=True)
finally:
 (out/'book-after.json').write_text(json.dumps(inventory(),indent=2))
 for p in dest.glob('*.py'):shutil.copyfile(p,out/p.name)
 sessions={r.get('session_id') for row in rows for r in row.get('records',[]) if r.get('session_id')}
 for p in (state/'agent/sessions').rglob('*.jsonl'):
  if any(s in p.name for s in sessions):shutil.copyfile(p,out/('session-'+p.name))
 p=bookdir/'plan-events.jsonl'
 if p.exists():
  selected=[l for l in p.read_text().splitlines() if json.loads(l).get('session_id') in sessions]
  (out/'plan-events.jsonl').write_text('\n'.join(selected)+'\n')
 files=sorted(p for p in out.rglob('*') if p.is_file());(out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))
