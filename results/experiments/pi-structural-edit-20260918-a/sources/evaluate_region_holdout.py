"""Frozen-protocol paired screening, with one native fallback and all costs retained."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil
import shlex
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bench',ROOT/'benchmarks/compare_region_edits.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
spec=importlib.util.spec_from_file_location('structural',ROOT/'deploy/structural_edit_protocol.py')
structural=importlib.util.module_from_spec(spec);spec.loader.exec_module(structural)
CASES={
 'short_flags':'Add -H, -p, -t, and -w as aliases for --host, --ports, --timeout, and --workers respectively. Preserve long flags, required arguments, defaults and all other behavior.',
 'compact_json':'Make main emit compact JSON without spaces after separators. Preserve the trailing newline, sorted keys, all existing fields and values, and exit behavior.',
 'empty_scan':'Make scan_ports return ([], []) immediately for an empty ports sequence, without DNS lookup or constructing a thread pool. Preserve all nonempty behavior.',
 'unique_scan':'Make scan_ports scan every distinct port only once even when its ports argument contains duplicates. Return sorted unique open and closed lists. Preserve its signature and other behavior.',
 'socket_creation':'Make scan_port return False if socket.socket itself raises OSError, as it already does for connection OSError. Preserve successful connections, timeout handling and closing successfully created sockets.',
 'exact_flags':'Disable argparse long-option abbreviation: --hos, --por, --time and --work must be rejected with exit code 2. Preserve complete option names, help and all other existing behavior.',
 'pool_cap':'In scan_ports, cap ThreadPoolExecutor max_workers to the number of ports for nonempty input so a request for 100 workers on 2 ports creates a pool with max_workers=2. Preserve the caller worker limit when smaller, all return values, and other behavior.',
 'socket_timeout_guard':'In scan_port, reject timeout values <=0 with ValueError before creating a socket. Preserve positive timeout behavior, return values, and socket cleanup. No new imports.',
 'default_workers_six':'Change build_parser so --workers defaults to 6, preserving explicit overrides, other defaults and all existing behavior.',
 'timeout_upper_guard':'In scan_port, reject timeout values greater than 60 with ValueError before creating a socket. Preserve timeout=60, ordinary positive timeout behavior, return values, and socket cleanup. No new imports.',
}
CHECK='''import json,sys,subprocess,unittest,socket,io,contextlib
from unittest.mock import patch,MagicMock
sys.path.insert(0,'.')
import port_scanner as m
case=sys.argv[1]
if case=='default_workers_six':
 parser=m.build_parser()
 assert parser.parse_args(['--host','127.0.0.1','--ports','80']).workers==6
 assert parser.parse_args(['--host','127.0.0.1','--ports','80','--workers','3']).workers==3
elif case=='timeout_upper_guard':
 for timeout in [60.01,100]:
  with patch.object(m.socket,'socket') as create:
   try:m.scan_port('127.0.0.1',80,timeout)
   except ValueError:pass
   else:raise AssertionError(timeout)
   create.assert_not_called()
 for timeout in [.1,60]:
  sock=MagicMock();sock.connect_ex.return_value=0
  with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',80,timeout) is True
  sock.close.assert_called_once()
elif case=='pool_cap':
 original=m.ThreadPoolExecutor
 for workers,expected in [(100,2),(1,1)]:
  with patch.object(m,'ThreadPoolExecutor',wraps=original) as pool,patch.object(m,'scan_port',return_value=False):
   assert m.scan_ports('127.0.0.1',[80,81],.1,workers)==([],[80,81])
   pool.assert_called_once_with(max_workers=expected)
elif case=='socket_timeout_guard':
 for timeout in [0,-.1,-100]:
  with patch.object(m.socket,'socket') as create:
   try:m.scan_port('127.0.0.1',80,timeout)
   except ValueError:pass
   else:raise AssertionError(timeout)
   create.assert_not_called()
 sock=MagicMock();sock.connect_ex.return_value=0
 with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',80,.1) is True
 sock.close.assert_called_once()
elif case=='short_flags':
 p=m.build_parser()
 for flags in [['-H','127.0.0.1','-p','80','-t','.2','-w','3'],['--host','127.0.0.1','--ports','80','--timeout','.2','--workers','3']]:
  a=p.parse_args(flags);assert (a.host,a.ports,a.timeout,a.workers)==('127.0.0.1','80',.2,3)
elif case=='compact_json':
 stream=io.StringIO()
 with patch.object(m,'scan_ports',return_value=([80],[81])),contextlib.redirect_stdout(stream):
  assert m.main(['--host','127.0.0.1','--ports','80,81'])==0
 value={'host':'127.0.0.1','open_ports':[80],'closed_ports':[81]}
 assert stream.getvalue()==json.dumps(value,sort_keys=True,separators=(',',':'))+'\\n',repr(stream.getvalue())
elif case=='empty_scan':
 with patch.object(m.socket,'getaddrinfo',side_effect=AssertionError('DNS must not run')),patch.object(m,'ThreadPoolExecutor',side_effect=AssertionError('pool must not run')):
  assert m.scan_ports('invalid',[],.1,1)==([],[])
  assert m.scan_ports('invalid',(),.1,1)==([],[])
elif case=='unique_scan':
 with patch.object(m,'scan_port',side_effect=lambda host,port,timeout:port==80) as scan:
  assert m.scan_ports('127.0.0.1',[81,80,81,80],.1,2)==([80],[81])
  assert scan.call_count==2,scan.call_count
elif case=='socket_creation':
 with patch.object(m.socket,'socket',side_effect=OSError('allocation failed')):
  assert m.scan_port('127.0.0.1',80,.1) is False
 for result in [0,111]:
  sock=MagicMock();sock.connect_ex.return_value=result
  with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',80,.1) is (result==0)
  sock.close.assert_called_once()
elif case=='exact_flags':
 for flag,value in [('--hos','127.0.0.1'),('--por','1'),('--time','.1'),('--work','1')]:
  with contextlib.redirect_stderr(io.StringIO()):
   try:m.build_parser().parse_args(['--host','127.0.0.1','--ports','1',flag,value])
   except SystemExit as e:assert e.code==2
   else:raise AssertionError(flag)
p=subprocess.run([sys.executable,'-m','unittest','-v','test_port_scanner'],capture_output=True,text=True,timeout=25)
assert p.returncode==0,p.stdout+p.stderr
print(json.dumps({'passed':True,'regression':p.stderr}))
'''

def attempt(folder,payload,source,regions,pristine,check,case,mode,host,line_protocol=False,structural_protocol=False):
 folder.mkdir();work=folder/'workspace';shutil.copytree(pristine,work)
 payload=json.loads(json.dumps(payload));payload['cache_salt']=uuid.uuid4().hex
 (folder/'request.json').write_text(json.dumps(payload,indent=2))
 start=time.perf_counter();result={'passed':False,'mode':mode}
 try:
  p=subprocess.run(['ssh','-o','BatchMode=yes',host,'python3 -c '+shlex.quote(b.REMOTE)],input=json.dumps(payload),capture_output=True,text=True,timeout=200)
  result['transport_seconds']=time.perf_counter()-start;p.check_returncode()
  data=json.loads(p.stdout);(folder/'response.json').write_text(json.dumps(data,indent=2))
  d=data['response'];result.update(usage=d['usage'],metrics=d.get('metrics'))
  choice=d['choices'][0];message=choice['message']
  if mode=='native':
   calls=message.get('tool_calls',[])
   if choice['finish_reason'] not in ['stop','tool_calls'] or len(calls)!=1 or calls[0]['function']['name']!='edit':raise ValueError('Invalid native edit')
   p=subprocess.run(['node',str(ROOT/'integrations/pi/apply_edit.mjs'),b.PI,str(work)],input=calls[0]['function']['arguments'],text=True,capture_output=True,timeout=15)
   (folder/'apply.json').write_text(json.dumps({'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}));p.check_returncode()
  else:
   if structural_protocol:
    updated=structural.decode(source,structural.digest(source),message.get('content') or '',choice['finish_reason'])
   else:
    decoder=b.region.decode_lines if line_protocol else b.region.decode_multi
    updated=decoder(source,b.region.digest(source),regions,message.get('content') or '',choice['finish_reason'])
   (work/'port_scanner.py').write_text(updated)
  result['validation']=b.validate(work,case,check);result['passed']=result['validation']['passed']
 except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
 result['seconds']=time.perf_counter()-start
 (folder/'result.json').write_text(json.dumps(result,indent=2));return result

def main(out,host,repeats,line_protocol=False,structural_protocol=False,selected=None):
 out=out.resolve();out.mkdir()
 pristine=out/'pristine';shutil.copytree(ROOT/'results/experiments/pi-scanner-20260918-run1/workspace',pristine,ignore=shutil.ignore_patterns('__pycache__'))
 source=(pristine/'port_scanner.py').read_text();regions=b.region.catalogue(source,True)
 check=out/'check.py';check.write_text(CHECK)
 cases={key:CASES[key] for key in (selected or CASES)}
 templates={mode:json.loads((ROOT/f'results/experiments/pi-multi-region-20260918-{suffix}/strict_ascii_ports-0-{mode}/request.json').read_text()) for mode,suffix in [('native','b'),('multi','c')]}
 templates['multi']['structured_outputs']={'regex':b.region.multi_regex(regions,False)}
 if line_protocol:
  regions=b.region.statement_catalogue(source)
  templates['multi']['structured_outputs']={'regex':b.region.line_regex(regions)}
  templates['multi']['messages'][0]['content']='Return only a compact JSON array of 1 to 8 [regionID,lines] edits. Each region is a COMPLETE Python statement in the original snapshot. Each lines value is an array of [relativeIndentDepth,singleLineCode] pairs. Depth is an integer 0..16; first line depth is 0. Do not put indentation whitespace in code strings: runtime renders indentation from depth and original source style. Use depth 1 for a nested suite, 0 again for except/else or a sibling statement. No physical newlines or tabs inside code strings; use multiple line pairs. For multiline string values use escaped newlines inside Python string literals. Empty lines array deletes the region. Do not duplicate statements following your selected region. Multiple edits must not overlap. Choose the smallest COMPLETE statement regions; prefer one-line calls where convenient. Example: [["L8",[[0,"if ready:"],[1,"return 4"],[0,"return 0"]]]]. No explanation.\nSOURCE HASH: '+b.region.digest(source)+'\nAVAILABLE REGIONS: '+', '.join(regions)
 if structural_protocol:
  templates['multi']['structured_outputs']={'regex':structural.grammar(source)}
  templates['multi']['messages'][0]['content']=structural.prompt(source)
 sources=out/'sources';sources.mkdir()
 for path in [Path(__file__),ROOT/'benchmarks/compare_region_edits.py',ROOT/'deploy/region_edit_protocol.py',ROOT/'deploy/structural_edit_protocol.py',ROOT/'integrations/pi/apply_edit.mjs']:
  shutil.copyfile(path,sources/path.name)
 manifest={'cases':cases,'repeats':repeats,'seed':20260918,'policy':'native: one request; hybrid: structured edit then at most one fresh native fallback on any failure; pristine reset; task tests serve as oracle','scope':'single edit plus tool execution and tests, not full autonomous agent or production safety certification','cache':'new salt every request','templates':templates,'acceptance':'screen only; success no worse, mean end-to-end >=15% lower, clustered bootstrap lower bound >0, p95 <= baseline; small sample cannot certify stability'}
 manifest['line_protocol']=line_protocol
 manifest['structural_protocol']=structural_protocol
 manifest['previously_evaluated_cases']=[k for k in cases if k in list(CASES)[:8]]
 manifest['new_cases']=[k for k in cases if k in list(CASES)[8:]]
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 before={case:b.validate(pristine,case,check) for case in cases};(out/'before-tests.json').write_text(json.dumps(before,indent=2))
 assert all(not r['passed'] for r in before.values())
 jobs=[(case,rep) for rep in range(repeats) for case in cases];random.Random(20260918).shuffle(jobs)
 for index,(case,rep) in enumerate(jobs):
  payloads={}
  for mode,template in templates.items():
   payload=json.loads(json.dumps(template));old=b.CASES['strict_ascii_ports']
   payload['messages'][1]['content']=payload['messages'][1]['content'].replace(old,CASES[case]);payloads[mode]=payload
  for arm in (['native','hybrid'] if index%2==0 else ['hybrid','native']):
   folder=out/f'{case}-{rep}-{arm}';folder.mkdir();start=time.perf_counter()
   modes=['native'] if arm=='native' else ['multi','native'];attempts=[]
   for num,mode in enumerate(modes):
    r=attempt(folder/f'attempt{num}',payloads[mode],source,regions,pristine,check,case,mode,host,line_protocol,structural_protocol);attempts.append(r)
    if r['passed']:break
   row={'case':case,'repeat':rep,'arm':arm,'passed':attempts[-1]['passed'],'seconds':time.perf_counter()-start,'attempts':attempts,'usage_complete':all('usage' in a for a in attempts),'usage':{key:sum(a.get('usage',{}).get(key,0) for a in attempts) for key in ['prompt_tokens','completion_tokens','total_tokens']}}
   (folder/'result.json').write_text(json.dumps(row,indent=2))
   with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   print(case,rep,arm,row['passed'],len(attempts),row['usage'],round(row['seconds'],2),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);p.add_argument('--host',default='rs-yuesheng-gpu-vps');p.add_argument('--repeats',type=int,default=2)
 p.add_argument('--line-protocol',action='store_true')
 p.add_argument('--structural-protocol',action='store_true');p.add_argument('--cases',nargs='+',choices=list(CASES))
 a=p.parse_args()
 if a.line_protocol and a.structural_protocol:p.error('Choose one protocol')
 main(a.out,a.host,a.repeats,a.line_protocol,a.structural_protocol,a.cases)
