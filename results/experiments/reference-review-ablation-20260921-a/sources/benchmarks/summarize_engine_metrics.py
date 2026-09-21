"""Summarize engine timings without equating client SSE cadence with decode."""
import argparse
import json
from pathlib import Path
import statistics


def main():
    p=argparse.ArgumentParser();p.add_argument('--rows',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();rows=[json.loads(l) for l in Path(args.rows).read_text().splitlines()]
    summary={}
    for mode in dict.fromkeys(r['mode'] for r in rows):
        selected=[r for r in rows if r['mode']==mode];timings=[];missing=[]
        for r in selected:
            trace=r['result'].get('trace',[])
            m=trace[0].get('engine_metrics') if len(trace)==1 else None
            keys=['queue_time_ms','time_to_first_token_ms','generation_time_ms']
            if not m or any(m.get(k) is None for k in keys):missing.append([r['id'],r.get('repeat')]);continue
            t={k:float(m[k]) for k in keys}
            t['wall_ms']=r['wall_seconds']*1000
            t['unaccounted_ms']=t['wall_ms']-sum(t[k] for k in keys)
            t['scheduled_to_last_ms']=t['time_to_first_token_ms']+t['generation_time_ms']
            if m.get('mean_itl_ms') is not None:t['mean_itl_ms']=float(m['mean_itl_ms'])
            timings.append(t)
        summary[mode]={'n':len(selected),'exact':sum(r['exact'] for r in selected),'metrics_n':len(timings),'missing_metrics':missing,
          'completion_tokens':sum(r['result'].get('completion_tokens',0) for r in selected)}
        if timings:
            summary[mode]['mean']={k:statistics.mean(t[k] for t in timings if k in t) for k in set().union(*timings)}
            summary[mode]['median']={k:statistics.median(t[k] for t in timings if k in t) for k in set().union(*timings)}
            summary[mode]['negative_residual_over_20ms']=sum(t['unaccounted_ms'] < -20 for t in timings)
    with Path(args.out).open('x') as f:json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
