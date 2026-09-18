"""Summarize paired edit tasks, including failures and native fallback costs."""
import argparse
import json
import math
from pathlib import Path
import random


def percentile(xs,q):
 xs=sorted(xs);index=(len(xs)-1)*q;lo=int(index);hi=math.ceil(index)
 return xs[lo]+(xs[hi]-xs[lo])*(index-lo)


def summarize(root):
 rows=[json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()]
 manifest=json.loads((root/'manifest.json').read_text())
 assert len(rows)==2*len(manifest['cases'])*manifest['repeats'],'Incomplete run'
 assert {(r['case'],r['repeat'],r['arm']) for r in rows}=={(c,n,a) for c in manifest['cases'] for n in range(manifest['repeats']) for a in ['native','hybrid']},'Missing or duplicate pair'
 assert all(r['usage_complete'] for r in rows),'Missing usage; do not report a zero-cost failure'
 result={}
 for arm in ['native','hybrid']:
  rs=[r for r in rows if r['arm']==arm]
  result[arm]={'n':len(rs),'passed':sum(r['passed'] for r in rs),'first_attempt_passed':sum(r['attempts'][0]['passed'] for r in rs),'fallbacks':sum(len(r['attempts'])-1 for r in rs),'seconds':sum(r['seconds'] for r in rs),'p95_seconds':percentile([r['seconds'] for r in rs],.95),'usage':{k:sum(r['usage'][k] for r in rs) for k in ['prompt_tokens','completion_tokens','total_tokens']}}
  for key in ['queue_time_ms','generation_time_ms']:
   values=[a.get('metrics',{}).get(key) for r in rs for a in r['attempts']]
   result[arm][key]=sum(values) if all(v is not None for v in values) else None
 native=result['native'];hybrid=result['hybrid']
 result['reductions']={k:1-hybrid['usage'][k]/native['usage'][k] for k in native['usage']}
 result['reductions']['wall_seconds']=1-hybrid['seconds']/native['seconds']
 cases=list(manifest['cases']);sums={c:{arm:sum(r['seconds'] for r in rows if r['case']==c and r['arm']==arm) for arm in ['native','hybrid']} for c in cases}
 rng=random.Random(20260918);boots=[]
 for _ in range(10000):
  sample=rng.choices(cases,k=len(cases));boots.append(1-sum(sums[c]['hybrid'] for c in sample)/sum(sums[c]['native'] for c in sample))
 result['case_cluster_bootstrap_wall_reduction_95ci']=[percentile(boots,.025),percentile(boots,.975)]
 result['screen_gate']=hybrid['passed']>=native['passed'] and result['reductions']['wall_seconds']>=.15 and result['case_cluster_bootstrap_wall_reduction_95ci'][0]>0 and hybrid['p95_seconds']<=native['p95_seconds']
 result['limitations']='6 related tasks, shared server, task-test oracle fallback, single-edit workflow; screening only, no production or stable speed claim'
 with (root/'summary.json').open('x') as f:json.dump(result,f,indent=2)
 print(json.dumps(result,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);summarize(p.parse_args().root)
