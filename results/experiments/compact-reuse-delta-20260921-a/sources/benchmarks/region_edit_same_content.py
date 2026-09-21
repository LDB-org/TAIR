"""Counterfactual token count only: encode successful native edits as region frames."""

import os
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import textwrap

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('region',ROOT/'deploy/region_edit_protocol.py')
region=importlib.util.module_from_spec(spec);spec.loader.exec_module(region)
REMOTE='''import json,sys,urllib.request
out=[]
for row in json.load(sys.stdin):
 p={'model':'/model','prompt':row['frame'],'add_special_tokens':False}
 r=urllib.request.Request('http://127.0.0.1:8000/tokenize',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=30) as f:d=json.load(f)
 out.append(dict(row,region_tokens_with_eos=len(d['tokens'])+1,token_ids=d['tokens']))
print(json.dumps(out,ensure_ascii=False))
'''


def frame_for_result(source,modified):
    regions=region.catalogue(source,readable=True)
    lines=source.splitlines(keepends=True)
    candidates=[]
    for key,r in regions.items():
        before=''.join(lines[:r['start']-1]);after=''.join(lines[r['end']:])
        if not modified.startswith(before) or not modified.endswith(after):continue
        replacement=modified[len(before):len(modified)-len(after) if after else len(modified)]
        frame=key+'\n'+textwrap.dedent(replacement)
        try:rebuilt=region.decode(source,region.digest(source),regions,frame,'stop',relative_indent=True)
        except ValueError:continue
        if rebuilt==modified:candidates.append((len(replacement),frame))
    if not candidates:raise ValueError('No single region can represent this edit')
    return min(candidates)[1]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--host',default=os.environ.get('TAIR_ENGINE_HOST', os.environ.get('ENGINE_TOOLCALL_HOST', 'localhost')));a=p.parse_args()
    source=(a.root/'pristine/port_scanner.py').read_text();rows=[]
    for folder in sorted(a.root.glob('*-0-native')):
        result=json.loads((folder/'result.json').read_text())
        if not result['passed']:raise ValueError('Native edit did not pass acceptance')
        modified=(folder/'workspace/port_scanner.py').read_text()
        frame=frame_for_result(source,modified)
        rows.append({'case':result['case'],'native_output_tokens':result['usage']['completion_tokens'],
                     'frame':frame,'exact_final_file_match':True})
    with (a.root/'same-content-tokens.json').open('x') as f:
        r=subprocess.run(['ssh','-o','BatchMode=yes',a.host,'python3 -c '+shlex.quote(REMOTE)],input=json.dumps(rows),capture_output=True,text=True,check=True,timeout=60)
        f.write(r.stdout)
    for row in json.loads(r.stdout):print(row['case'],row['native_output_tokens'],row['region_tokens_with_eos'])
