"""Bounded feedback repair of failed region trials; retains all retry costs."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bench',ROOT/'benchmarks/compare_region_edits.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)


def main(root,out,host):
    root=root.resolve();out=out.resolve();out.mkdir()
    rows=[json.loads(s) for s in (root/'rows.jsonl').read_text().splitlines()]
    source=(root/'pristine/port_scanner.py').read_text()
    regions=json.loads((root/'regions.json').read_text())
    results=[]
    for original in rows:
        if original['mode']!='multi' or original['passed']:continue
        name=f"{original['case']}-{original['repeat']}-multi"
        payload=json.loads((root/name/'request.json').read_text())
        response=json.loads((root/name/'response.json').read_text())['response']
        previous=original
        costs=[original['usage']]
        for attempt in range(1,3):
            folder=out/(name+f'-repair{attempt}');folder.mkdir()
            work=folder/'workspace';shutil.copytree(root/'pristine',work)
            error=previous.get('error') or previous.get('validation',{}).get('stderr','Validation failed')
            payload['messages'].extend([
                {'role':'assistant','content':response['choices'][0]['message'].get('content') or ''},
                {'role':'user','content':'The proposed edit was NOT committed. Runtime/test feedback:\n'+error+
                 '\nCorrect your edit against the SAME original source. Each L ID replaces exactly ONE line; use a listed B region to replace a whole compound statement. Replacement first lines start at relative column zero, without original base indentation. Subsequent lines use relative indentation. Avoid duplicate/overlapping regions. Return the corrected compact array only.'}])
            (folder/'request.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
            started=time.perf_counter()
            p=subprocess.run(['ssh','-o','BatchMode=yes',host,'python3 -c '+shlex.quote(bench.REMOTE)],input=json.dumps(payload),capture_output=True,text=True,timeout=200)
            result={'case':original['case'],'repeat':original['repeat'],'attempt':attempt,'seconds':time.perf_counter()-started,'passed':False}
            try:
                p.check_returncode();data=json.loads(p.stdout);response=data['response']
                (folder/'response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
                result.update(usage=response['usage'],metrics=response.get('metrics'));costs.append(response['usage'])
                choice=response['choices'][0];raw=choice['message'].get('content') or ''
                updated=bench.region.decode_multi(source,bench.region.digest(source),regions,raw,choice['finish_reason'])
                (work/'port_scanner.py').write_text(updated)
                result['selected_regions']=[e[0] for e in json.loads(raw)]
                result['validation']=bench.validate(work,original['case'],root/'check.py')
                result['passed']=result['validation']['passed']
            except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
            (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
            print(name,'attempt',attempt,'passed',result['passed'],'usage',result.get('usage'),flush=True)
            previous=result
            if result['passed']:break
        results.append({'trial':name,'passed':previous['passed'],'retries':previous['attempt'],
                        'total_usage_including_initial':{k:sum(c[k] for c in costs) for k in ['prompt_tokens','completion_tokens','total_tokens']}})
    (out/'summary.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--host',default='rs-yuesheng-gpu-vps')
    a=p.parse_args();main(a.root,a.out,a.host)
