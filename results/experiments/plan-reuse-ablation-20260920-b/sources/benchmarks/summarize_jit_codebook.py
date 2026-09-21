"""Account for cold calls, cache selection, failed gates and generated fallback."""
import argparse
import json
from pathlib import Path


def summarize(root):
    manifest=json.loads((root/'manifest.json').read_text())
    rows=[json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()]
    expected={(c[0],a) for c in manifest['cases'] for a in ['baseline','jit']}
    assert len(rows)==len(expected) and {(r['case'],r['arm']) for r in rows}==expected
    assert all(r['usage_complete'] for r in rows),'Incomplete usage; do not claim savings'
    output={}
    for arm in ['baseline','jit']:
        selected=[r for r in rows if r['arm']==arm]
        requests=[q for r in selected for q in r['requests'] if q['usage'] is not None]
        controls=sum(r['control_records'] for r in selected)
        usage={key:sum(r['usage'][key] for r in selected) for key in ['prompt_tokens','completion_tokens','total_tokens']}
        metrics=[q['metrics'] for q in requests]
        assert all(m and all(m.get(k) is not None for k in ['time_to_first_token_ms','generation_time_ms','queue_time_ms']) for m in metrics)
        output[arm]={'tasks':len(selected),'passed':sum(r['passed'] for r in selected),'inference_requests':len(requests),'tokenize_requests':sum(q['route']=='/tokenize' for r in selected for q in r['requests']),
                     'generated_tokens':usage['completion_tokens']-controls,'control_records':controls,'usage':usage,
                     'wall_seconds':sum(r['seconds'] for r in selected),'scheduled_inference_seconds':sum(m['time_to_first_token_ms']+m['generation_time_ms'] for m in metrics)/1000,
                     'queue_seconds':sum(m['queue_time_ms'] for m in metrics)/1000,
                     'cache_hits':sum(r['cache_hit'] for r in selected),'gate_accepts':sum(r['gate_accepted'] for r in selected),
                     'false_accepts_before_oracle':sum(r['false_acceptance'] for r in selected),'admissions':sum(r['admitted'] for r in selected)}
    output['rows']=[{k:r[k] for k in ['case','arm','passed','cache_hit','gate_accepted','false_acceptance','admitted','usage','seconds']} for r in rows]
    output['limitations']='Hand-authored oracle admission/rejection; uncalibrated fixed gate; keyword-only templates; small sequential related workload on shared server; not arbitrary-prompt or production proof.'
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();result=summarize(a.root)
    with (a.root/'summary.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
