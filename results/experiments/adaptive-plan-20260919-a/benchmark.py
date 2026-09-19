"""One model request chooses persisted code reuse or writes new code, returning one plan."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
SEED=ROOT/'results/experiments/file-io-20260919-a/hybrid/project-after/file_io.py'
CONTRACT='UTF-8 text module: read_text(path) returns all text; write_text(path,text,*,append=False) creates files, overwrites by default, appends only when requested. Accepts str/Path. Missing reads raise FileNotFoundError. Does NOT create parent directories. No binary API, encoding parameter, or exclusive-create behavior.'
POLICY='''Return exactly one plan tool call containing every requested output file. Only create the listed files. No shell, network, tests, explanations or extra files. Generate small standard-library Python modules with no import-time I/O. The persisted catalog contains earlier validated source, not a guarantee that its contract satisfies this task. Reuse an entry only if its entire contract satisfies the request; bind its destination path. Otherwise emit a write step with complete new source IN THIS SAME RESPONSE. A plan may mix reuse and write steps. Do not change an entry via reuse parameters: the only supported binding is destination path. Do not choose a vaguely similar entry or ignore a new requirement.'''


def cases():
    standard='Provide read_text(path) and write_text(path,text,*,append=False), UTF-8 text, str or Path paths. Read the whole file. Write overwrites by default or appends on append=True; create missing files, but do not create parent directories. Missing reads raise FileNotFoundError.'
    return [dict(name='exact_contract',task='Create text_io.py. '+standard,outputs={'text_io.py':'utf8'}),
        dict(name='chinese_paraphrase',task='编写 local_io.py：read_text 读取整个 UTF-8 文件；write_text(path,text,*,append=False) 默认覆盖，append=True 才追加。支持字符串和 Path。文件不存在可新建，但不自动创建父目录；读取不存在的文件抛出 FileNotFoundError。',outputs={'local_io.py':'utf8'}),
        dict(name='new_destination',task='Create helpers/files.py. '+standard,outputs={'helpers/files.py':'utf8'}),
        dict(name='different_encoding',task='Create text_io.py with read_text(path) and write_text(path,text,*,append=False). Use UTF-16, NOT UTF-8, for both reading and writing. Support overwrite/append, str and Path; do not create parent directories.',outputs={'text_io.py':'utf16'}),
        dict(name='create_parents',task='Create text_io.py. '+standard+' EXCEPTION: writing must automatically create any missing parent directories, including nested parents.',outputs={'text_io.py':'parents'}),
        dict(name='exclusive_write',task='Create text_io.py providing read_text(path) and write_text(path,text). Use UTF-8. write_text must create a new file but raise FileExistsError and preserve all bytes if the destination already exists. Never overwrite or append. Do not create parent directories.',outputs={'text_io.py':'exclusive'}),
        dict(name='binary',task='Create binary_io.py with read_bytes(path)->bytes and write_bytes(path,data,*,append=False). Binary files, arbitrary bytes including invalid UTF-8, overwrite by default, append when requested, str/Path accepted. Do not create parent directories.',outputs={'binary_io.py':'binary'}),
        dict(name='mixed_plan',task='Create two modules. text_io.py: '+standard+' Also create binary_io.py with read_bytes(path) and write_bytes(path,data,*,append=False), arbitrary binary bytes, overwrite or append, no automatic parent directories.',outputs={'text_io.py':'utf8','binary_io.py':'binary'})]


def obj(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def schema(arm):
    string=dict(type='string')
    write=obj(dict(op=dict(type='string',enum=['write']),path=string,content=string))
    choices=[write]
    if arm=='adaptive':choices.append(obj(dict(op=dict(type='string',enum=['reuse']),path=string,entry_id=string,source_sha256=string)))
    return obj(dict(steps=dict(type='array',minItems=1,maxItems=4,items=dict(anyOf=choices))))


def check_module(path, kind):
    # Hidden behavior audit, not available to the model and not a production semantic guard.
    code=r'''import importlib.util,sys,tempfile
from pathlib import Path
path,kind=sys.argv[1:]
spec=importlib.util.spec_from_file_location('subject',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);p=root/'sample'
 if kind=='binary':
  data=b'\x00\xff\xfe\x80\r\n';m.write_bytes(p,data);assert p.read_bytes()==data and m.read_bytes(str(p))==data
  m.write_bytes(str(p),b'new');assert m.read_bytes(p)==b'new'
  m.write_bytes(p,b'\xff',append=True);assert m.read_bytes(p)==b'new\xff'
  read,write=m.read_bytes,m.write_bytes;value=b'x'
 else:
  encoding='utf-16' if kind=='utf16' else 'utf-8'
  value='雪 café\n';m.write_text(p,value);assert p.read_bytes().decode(encoding)==value and m.read_text(str(p))==value
  read,write=m.read_text,m.write_text
  if kind=='exclusive':
   before=p.read_bytes()
   try:write(str(p),'replacement')
   except FileExistsError:pass
   else:raise AssertionError('Existing file was not rejected')
   assert p.read_bytes()==before
  else:
   write(str(p),'new');assert read(p)=='new'
   write(p,'追加',append=True);assert read(p)=='new追加'
   write(p,'');assert read(p)==''
 try:read(root/'missing')
 except FileNotFoundError:pass
 else:raise AssertionError('Missing read did not raise')
 nested=root/'a'/'b'/'x'
 if kind=='parents':write(nested,value);assert read(nested)==value
 else:
  try:write(nested,value)
  except FileNotFoundError:pass
  else:raise AssertionError('Unexpected parent directory creation')
'''
    result=subprocess.run([sys.executable,'-B','-c',code,str(path.resolve()),kind],capture_output=True,text=True,timeout=8)
    if result.returncode:raise ValueError(result.stderr)


def build_book():
    source=SEED.read_text();check_module(SEED,'utf8')
    return dict(version=1,entries=[dict(id='text_io_v1',source=source,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        contract=CONTRACT,bindings=['path'],origin=str(SEED.relative_to(ROOT)),admission='Independent UTF-8 read/write behavior checks on earlier model-generated artifact')])


def materialize(plan, book, folder, allowed, arm):
    from jsonschema import validate
    validate(plan,schema(arm))
    names=[step['path'] for step in plan['steps']]
    if len(set(names))!=len(names) or set(names)!=set(allowed):raise ValueError('Wrong, duplicate or missing output paths')
    prepared=[]
    for step in plan['steps']:
        path=(folder/step['path']).resolve()
        if not path.is_relative_to(folder.resolve()):raise ValueError('Path escapes workspace')
        if step['op']=='reuse':
            entry=next((e for e in book['entries'] if e['id']==step['entry_id']),None)
            if entry is None or step['source_sha256']!=entry['source_sha256']:raise ValueError('Unknown or stale codebook entry')
            content=entry['source']
            if hashlib.sha256(content.encode()).hexdigest()!=entry['source_sha256']:raise ValueError('Corrupt persisted source')
        else:content=step['content']
        compile(content,str(path),'exec');prepared.append((path,content))
    for path,content in prepared:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)


def attempt(url,arm,case,book,folder):
    row=dict(arm=arm,case=case['name'],passed=False,inference_requests=0,input_tokens=0,output_tokens=0,controls=0,usage_complete=False)
    start=time.perf_counter()
    context=POLICY
    if arm!='adaptive':context+=' This interface accepts write only; generate complete source for every requested file.'
    user=dict(task=case['task'],allowed_paths=list(case['outputs']))
    if arm!='generate_no_catalog':user['catalog']=book
    body=dict(model='/model',messages=[dict(role='system',content=context),dict(role='user',content=json.dumps(user,ensure_ascii=False))],
        tools=[dict(type='function',function=dict(name='plan',description='One plan containing all file operations.',parameters=schema(arm)))],
        tool_choice=dict(type='function',function=dict(name='plan')),parallel_tool_calls=False,temperature=0,max_tokens=4096,
        cache_salt=uuid.uuid4().hex,chat_template_kwargs=dict(thinking=False,enable_thinking=False))
    row['request']=body
    try:
        row['inference_requests']=1;begin=time.perf_counter()
        request=urllib.request.Request(url+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=120) as response:data=json.load(response)
        row.update(response=data,inference_seconds=time.perf_counter()-begin,input_tokens=data['usage']['prompt_tokens'],
            output_tokens=data['usage']['completion_tokens'],usage_complete=True)
        choice=data['choices'][0]
        if choice['finish_reason'] not in ('stop','tool_calls'):raise ValueError('Incomplete response')
        calls=choice['message'].get('tool_calls') or []
        if len(calls)!=1 or calls[0]['function']['name']!='plan':raise ValueError('Expected exactly one plan')
        plan=json.loads(calls[0]['function']['arguments']);row['plan']=plan
        materialize(plan,book,folder,case['outputs'],arm)
        row['reuse_steps']=sum(s['op']=='reuse' for s in plan['steps'])
        row['write_steps']=sum(s['op']=='write' for s in plan['steps'])
        row['file_checks']=[]
        for path,kind in case['outputs'].items():
            try:check_module(folder/path,kind);row['file_checks'].append(dict(path=path,passed=True))
            except Exception as error:row['file_checks'].append(dict(path=path,passed=False,error=repr(error)))
        row['passed']=all(r['passed'] for r in row['file_checks'])
    except Exception as error:row['error']=repr(error)
    row['seconds']=time.perf_counter()-start
    return row


def run(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(__file__,out/'benchmark.py')
    book=build_book();(out/'codebook.json').write_text(json.dumps(book,indent=2,ensure_ascii=False))
    # Reload from disk: this is a persisted learned artifact, not a regex task dispatcher.
    book=json.loads((out/'codebook.json').read_text())
    arms=['generate_no_catalog','generate_with_catalog','adaptive'];tasks=cases()
    (out/'manifest.json').write_text(json.dumps(dict(arms=arms,cases=tasks,repeats=args.repeats,policy=POLICY,max_tokens=4096,
        method='Exactly one model request per attempt, both reuse and new source in one plan. Fresh cache namespace, randomized interleaving, no retry. Fixed persisted catalog from earlier validated model output, no admission during timed evaluation. First generator sees no catalog; second shares the adaptive catalog. No regex intent dispatch and no special logits classification kernel. Independent hidden checks do not choose branches or repair plans.'),indent=2))
    jobs=[(case,arm,r) for r in range(args.repeats) for case in tasks for arm in arms];random.Random(20260921).shuffle(jobs)
    rows=[]
    for index,(case,arm,repeat) in enumerate(jobs):
        folder=out/'attempts'/str(index)/'project';folder.mkdir(parents=True)
        row=attempt(args.url,arm,case,book,folder);row.update(index=index,repeat=repeat)
        (folder.parent/'result.json').write_text(json.dumps(row,indent=2,ensure_ascii=False));rows.append(row)
        with (out/'rows.jsonl').open('a') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(json.dumps({k:v for k,v in row.items() if k not in ('request','response','plan','file_checks')}),flush=True)
    def total(group):
        return dict(attempts=len(group),passed=sum(r['passed'] for r in group),usage_complete=all(r['usage_complete'] for r in group),
            **{key:sum(r.get(key,0) for r in group) for key in ['seconds','inference_seconds','inference_requests','input_tokens','output_tokens','controls','reuse_steps','write_steps']})
    result=dict(all={a:total([r for r in rows if r['arm']==a]) for a in arms},
        by_case={c['name']:{a:total([r for r in rows if r['case']==c['name'] and r['arm']==a]) for a in arms} for c in tasks})
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['all']),flush=True)
    return int(not all(r['passed'] and r['usage_complete'] for r in rows))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--repeats',type=int,default=2)
    raise SystemExit(run(p.parse_args()))
