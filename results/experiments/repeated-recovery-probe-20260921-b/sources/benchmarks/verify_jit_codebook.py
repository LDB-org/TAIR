"""Capture and verify actual direct-classifier worker traces for a JIT probe."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess


def verify(root, events):
    rows=[json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()]
    ids=[q['request_id'] for r in rows for q in r['requests'] if q['route']=='/v1/completions']
    checks=[]
    for request_id in ids:
        trace=[e for e in events if e.get('request_id','').startswith(request_id) and e['event']=='classify']
        assert trace and all(e['sampler_bypassed'] and e['runner']=='v2' for e in trace),request_id
        checks.append({'request_id':request_id,'sampler_bypassed':True,'events':len(trace)})
    entries=json.loads((root/'codebook.json').read_text())
    assert len(entries)==sum(r['admitted'] for r in rows)
    assert all(r['generated_validation']['passed'] for r in rows if r['admitted'])
    assert all(r['cached_validation']['passed'] and not r['generated'] for r in rows if r['cache_hit'])
    return {'verified_classifications':len(checks),'validated_admissions':len(entries),'checks':checks}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--host');p.add_argument('--container',default='vllm-deepseek-v4-sm120-situ');a=p.parse_args()
    event_path=a.root/'engine-events.jsonl'
    if a.host:
        rows=[json.loads(line) for line in (a.root/'rows.jsonl').read_text().splitlines()]
        ids=[q['request_id'] for r in rows for q in r['requests'] if q['route']=='/v1/completions']
        code='import json\nids='+repr(ids)+'\nfor line in open("/tmp/openjev-direct-events.jsonl"):\n try:e=json.loads(line)\n except ValueError:continue\n if any(e.get("request_id","").startswith(i) for i in ids):print(line,end="")'
        result=subprocess.run(['ssh',a.host,'docker exec '+shlex.quote(a.container)+' python3 -c '+shlex.quote(code)],capture_output=True,text=True,check=True)
        with event_path.open('x') as f:f.write(result.stdout)
    result=verify(a.root,[json.loads(line) for line in event_path.read_text().splitlines()])
    with (a.root/'verification.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
