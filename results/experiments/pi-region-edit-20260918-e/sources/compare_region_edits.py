"""Paired native Pi edit versus version-bound region selection; create-only."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('region', ROOT/'deploy/region_edit_protocol.py')
region = importlib.util.module_from_spec(spec)
spec.loader.exec_module(region)
PI = '/home/Kei/.nvm/versions/node/v24.14.0/lib/node_modules/@earendil-works/pi-coding-agent'
REMOTE = '''import json,sys,time,urllib.request
p=json.load(sys.stdin); started=time.perf_counter()
r=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(r,timeout=180) as f:d=json.load(f)
print(json.dumps({'response':d,'seconds':time.perf_counter()-started},ensure_ascii=False))
'''
CASES = {
 'finite_timeout': 'Fix CLI timeout validation to reject nan, inf, -inf as well as zero and negatives with argparse exit code 2. Keep ordinary positive finite timeouts working. Make the smallest necessary change; do not add imports.',
 'range_step': 'Extend parse_port_spec to support inclusive stepped ranges START-END/STEP, e.g. 20-26/2 gives 20,22,24,26. STEP must be a positive integer; /STEP is only allowed on a range, never on a single port. Keep existing comma/range/deduplication/validation behavior. Modify only parse_port_spec; retain its name and signature.',
 'socket_context': 'Refactor only scan_port to manage its socket with a with context manager, eliminating the explicit try/finally close logic. Preserve True on connect_ex==0, False on nonzero or OSError, and close the socket both on success and failure. Keep its signature; no new imports.',
 'strict_ascii_ports': 'Tighten parse_port_spec to accept only ASCII decimal digits in each port or range endpoint after trimming surrounding whitespace. Reject leading plus signs, underscores, fullwidth or other Unicode digits, for both single ports and range endpoints. Preserve existing ASCII ranges, deduplication, bounds checking and surrounding whitespace support. Modify only parse_port_spec; no new imports.',
}
CHECK = '''import ast,json,subprocess,sys,socket,unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,'.')
import port_scanner as m
case=sys.argv[1]
if case=='finite_timeout':
 for value in ['nan','inf','-inf','0','-0.1']:
  p=subprocess.run([sys.executable,'port_scanner.py','--host','127.0.0.1','--ports','1','--timeout='+value],capture_output=True,text=True,timeout=5)
  assert p.returncode==2,(value,p.returncode,p.stdout,p.stderr)
elif case=='range_step':
 for text,expected in [('20-26/2,80,20',[20,22,24,26,80]),('1-7/3',[1,4,7]),('80-80/2',[80]),('10-13/2,12-14',[10,12,13,14])]:
  assert m.parse_port_spec(text)==expected,(text,m.parse_port_spec(text))
 for text in ['1-5/0','1-5/-1','1-5/x','80/2','5-1/2','1-65536/2','1-5/2/3']:
  try:m.parse_port_spec(text)
  except ValueError:pass
  else:raise AssertionError(text)
elif case=='strict_ascii_ports':
 for text in ['+80','8_0','８０','١٢','1-+3','1-3_0','1-３','١-٣']:
  try:m.parse_port_spec(text)
  except ValueError:pass
  else:raise AssertionError(text)
 assert m.parse_port_spec(' 80 , 81 - 83 ,80 ')==[80,81,82,83]
elif case=='socket_context':
 tree=ast.parse(open('port_scanner.py').read()); fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='scan_port')
 assert any(isinstance(n,ast.With) for n in ast.walk(fn)),'Context manager missing'
 assert not any(isinstance(n,ast.Try) and n.finalbody for n in ast.walk(fn)),'Explicit finally remains'
 for outcome,expected in [(0,True),(111,False),(OSError('test'),False)]:
  sock=MagicMock();sock.__enter__.return_value=sock
  if isinstance(outcome,Exception):sock.connect_ex.side_effect=outcome
  else:sock.connect_ex.return_value=outcome
  with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',12345,.1) is expected
  sock.__exit__.assert_called_once();sock.settimeout.assert_called_once_with(.1)
p=subprocess.run([sys.executable,'-m','unittest','-v','test_port_scanner'],capture_output=True,text=True,timeout=25)
assert p.returncode==0,p.stdout+p.stderr
print(json.dumps({'status':'passed','case':case,'regression_output':p.stderr}))
'''


def validate(work, case, checkfile):
    command = ['bwrap','--unshare-all','--die-with-parent','--new-session','--clearenv',
               '--setenv','PATH','/usr/bin:/bin','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin',
               '--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp',
               '--ro-bind',str(work),'/work','--ro-bind',str(checkfile),'/check.py','--chdir','/work',
               '/usr/bin/python3','/check.py',case]
    p = subprocess.run(command,text=True,capture_output=True,timeout=40)
    return {'passed':p.returncode==0,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}


def main(out, host, repeats, readable=False, examples=False, selected=None):
    out=out.resolve();out.mkdir()
    original=ROOT/'results/experiments/pi-scanner-20260918-run1/workspace'
    source=(original/'port_scanner.py').read_text()
    regions=region.catalogue(source,readable=readable)
    checkfile=out/'check.py';checkfile.write_text(CHECK)
    (out/'regions.json').write_text(json.dumps(regions,indent=2))
    cases={key:CASES[key] for key in (selected or list(CASES))}
    (out/'cases.json').write_text(json.dumps(cases,indent=2))
    module=Path(PI)/'dist/core/tools/edit.js'
    script='const {createEditTool}=await import(process.argv[1]);console.log(JSON.stringify(createEditTool("/work").parameters));'
    schema=json.loads(subprocess.check_output(['node','--input-type=module','-e',script,module.as_uri()],text=True))
    (out/'native-schema.json').write_text(json.dumps(schema,indent=2))
    numbered=''.join(f'{i}: {line}' for i,line in enumerate(source.splitlines(keepends=True),1))
    catalog='\n'.join(f"{key}: lines {r['start']}-{r['end']}" for key,r in regions.items())
    if readable:
        catalog='Single nonblank line N is LN (e.g. line 152 is L152). Available multi-line AST blocks: '+', '.join(k for k,r in regions.items() if r['start']!=r['end'])
    pristine=out/'pristine';shutil.copytree(original,pristine,ignore=shutil.ignore_patterns('__pycache__'))
    prechecks={case:validate(pristine,case,checkfile) for case in cases}
    (out/'before-tests.json').write_text(json.dumps(prechecks,indent=2))
    assert all(not r['passed'] for r in prechecks.values()),'A regression test did not fail before modification'
    for repeat in range(repeats):
        for case,task in cases.items():
            for mode in (['native','region'] if repeat%2==0 else ['region','native']):
                name=f'{case}-{repeat}-{mode}';folder=out/name;folder.mkdir()
                work=folder/'workspace';shutil.copytree(pristine,work)
                common='Edit the supplied existing Python file to satisfy the task. Make the smallest necessary change, preserve unrelated behavior, no explanations. Return one edit operation only.\nTASK: '+task+'\nFILE: port_scanner.py\nSOURCE (line numbers are not file content):\n'+numbered
                if examples:
                    common+='\nCURRENT TASK (apply a real change, not a copy of unchanged source): '+task
                payload={'model':'/model','temperature':0,'max_tokens':4096,'return_token_ids':True,
                         'cache_salt':uuid.uuid4().hex,'chat_template_kwargs':{'thinking':False,'enable_thinking':False}}
                if mode=='native':
                    system='Use the edit tool once with path port_scanner.py and edits containing the minimal unique oldText/newText replacements. Do not emit ordinary assistant text.'
                    payload.update(tools=[{'type':'function','function':{'name':'edit','description':'Apply unique exact text replacements to a file.','parameters':schema}}],tool_choice='auto',parallel_tool_calls=False)
                else:
                    system='Output exactly a region ID from the catalogue, then one newline, then RAW replacement source for that entire region. Preserve indentation. No JSON or fences. Empty replacement deletes the region. The runtime binds the region to the supplied source hash.\nSOURCE HASH: '+region.digest(source)+'\nREGIONS:\n'+catalog
                    if readable:
                        system=system.replace('Preserve indentation.', 'Start replacement at relative column zero (no leading spaces on first line). Preserve relative indentation on subsequent lines. Runtime adds the selected region\'s original base indentation to all lines.')
                    if examples:
                        system+='\nFORMAT EXAMPLE on unrelated toy source: line 8 is "    return 3" and the task asks to return 4. Correct output is exactly:\nL8\nreturn 4\nEND EXAMPLE. For the actual task, first identify the faulty source lines, select the smallest applicable region, then output corrected replacement code. Do not output the example.'
                    payload['structured_outputs']={'regex':region.regex(regions,relative_indent=readable)}
                payload['messages']=[{'role':'system','content':system},{'role':'user','content':common}]
                (folder/'request.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
                started=time.perf_counter()
                process=subprocess.run(['ssh','-o','BatchMode=yes',host,'python3 -c '+shlex.quote(REMOTE)],input=json.dumps(payload),capture_output=True,text=True,timeout=200)
                elapsed=time.perf_counter()-started
                result={'case':case,'repeat':repeat,'mode':mode,'seconds':elapsed,'passed':False}
                try:
                    process.check_returncode(); response=json.loads(process.stdout)
                    (folder/'response.json').write_text(json.dumps(response,ensure_ascii=False,indent=2))
                    d=response['response'];choice=d['choices'][0];message=choice['message'];result.update(usage=d['usage'],metrics=d.get('metrics'))
                    if mode=='native':
                        calls=message.get('tool_calls',[])
                        if choice['finish_reason'] not in ['stop','tool_calls'] or len(calls)!=1 or calls[0]['function']['name']!='edit':raise ValueError('Invalid native edit')
                        args=json.loads(calls[0]['function']['arguments'])
                        p=subprocess.run(['node',str(ROOT/'integrations/pi/apply_edit.mjs'),PI,str(work)],input=json.dumps(args),text=True,capture_output=True,timeout=15)
                        (folder/'apply.json').write_text(json.dumps({'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}))
                        p.check_returncode()
                    else:
                        raw=message.get('content') or ''
                        updated=region.decode((work/'port_scanner.py').read_text(),region.digest(source),regions,raw,choice['finish_reason'],relative_indent=readable)
                        (work/'port_scanner.py').write_text(updated)
                        result['region']=raw.partition('\n')[0]
                    result['validation']=validate(work,case,checkfile);result['passed']=result['validation']['passed']
                except Exception as exc:
                    result['error']=type(exc).__name__+': '+str(exc)
                    result['stderr']=process.stderr
                with (folder/'result.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
                with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
                print(name,'passed',result['passed'],'tokens',result.get('usage'),'seconds',round(elapsed,2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--host',default='rs-yuesheng-gpu-vps');p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--readable-regions',action='store_true')
    p.add_argument('--examples',action='store_true')
    p.add_argument('--cases',nargs='+',choices=list(CASES))
    a=p.parse_args();main(a.out,a.host,a.repeats,a.readable_regions,a.examples,a.cases)
