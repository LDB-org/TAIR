"""Audit and summarize expanded bound-edit runs without exporting upstream fixtures."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


def report(root):
    rows=[json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()]
    manifest=json.loads((root/'manifest.json').read_text())
    coverage=json.loads((root/'coverage.json').read_text())
    complete=json.loads((root/'complete.json').read_text())
    arms=manifest['arms'];expected=len(manifest['cases'])*len(arms)*manifest['repeats']
    assert complete['completed']==expected==len(rows)
    assert len({(r['case'],r['arm'],r['repeat']) for r in rows})==expected
    specs={r['case']:r for r in coverage}
    def group(row):
        spec=specs[row['case']]
        return 'bound' if spec['correct_candidates'] else 'empty' if not spec['candidates'] else 'nonempty_miss'
    success_keys=set.intersection(*[{(r['case'],r['repeat']) for r in rows if r['arm']==arm and r['passed']} for arm in arms])
    summaries=[]
    scopes=['all','bound','empty','nonempty_miss','cpython','common_success']
    for scope in scopes:
        for arm in arms:
            selected=[r for r in rows if r['arm']==arm and (scope=='all' or group(r)==scope
                or scope=='cpython' and r['origin']=='cpython'
                or scope=='common_success' and (r['case'],r['repeat']) in success_keys)]
            summaries.append(dict(scope=scope,arm=arm,n=len(selected),passed=sum(r['passed'] for r in selected),
                false_bindings=sum(r['false_binding'] for r in selected),
                bound_selections=sum(r.get('bound_selected',False) for r in selected),
                empty_skips=sum(r.get('skipped_empty_classification',False) for r in selected),
                fallback=sum(r['fallback'] for r in selected),
                median_seconds=statistics.median(r['total_seconds'] for r in selected) if selected else None,
                **{k:sum(r[k] for r in selected) for k in ['total_seconds','preparation_seconds','inference_seconds','inference_requests','generated_tokens','controls','logical_input_tokens']}))
    percase=[]
    for spec in coverage:
        record={k:spec[k] for k in ['case','origin','candidates']};record['group']=group({'case':spec['case']})
        record['arms']={}
        for arm in arms:
            selected=[r for r in rows if r['case']==spec['case'] and r['arm']==arm]
            record['arms'][arm]=dict(n=len(selected),passed=sum(r['passed'] for r in selected),
                mean_seconds=statistics.mean(r['total_seconds'] for r in selected),
                false_bindings=sum(r['false_binding'] for r in selected))
        percase.append(record)
    checks=[]
    for name in ['benchmark_bound_expanded.py','benchmark_bound_edits.py','benchmark_engine_plan.py','repository_scenarios.py']:
        archived=(root/name).read_bytes();live=(Path(__file__).parent/name).read_bytes()
        assert archived==live, 'Source changed: '+name
        checks.append(dict(file=name,sha256=hashlib.sha256(archived).hexdigest()))
    events=[json.loads(line) for line in (root/'engine-events.jsonl').read_text().splitlines()]
    classified=[r['responses'][0]['id'] for r in rows if r['controls']]
    assert all(any(e.get('request_id','').startswith(rid) and e.get('sampler_bypassed') for e in events) for rid in classified)
    index={(s['scope'],s['arm']):s for s in summaries}
    errors=[]
    for row in rows:
        if not row['false_binding'] or not row['controls']:
            continue
        scores=sorted(row['responses'][0]['choices'][0]['logprobs']['top_logprobs'][0].values(),reverse=True)
        errors.append(dict(case=row['case'],repeat=row['repeat'],top_token_probability=math.exp(scores[0]),
                           top_two_margin=scores[0]-scores[1] if len(scores)>1 else None))
    return dict(total_attempts=len(rows),passed=sum(r['passed'] for r in rows),scenario_count=len(coverage),
        covered_scenarios=sum(bool(s['correct_candidates']) for s in coverage),source_checks=checks,
        verified_classifications=len(classified),summaries=summaries,percase=percase,false_binding_diagnostics=errors,
        all_task_time_ratio={arm:index['all',arm]['total_seconds']/index['all','generate']['total_seconds'] for arm in arms},
        raw_scope='Local pinned CPython sources retained outside Git. Metrics contain no upstream fixture source.',
        limitations='Single observed-source edit stage, small per-case repeats, shared server. Not a complete Agent, blind benchmark or production guarantee.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();data=report(args.root);args.out.write_text(json.dumps(data,indent=2))
    print(json.dumps({k:v for k,v in data.items() if k not in ('source_checks','percase','summaries')},indent=2))
    print(json.dumps([s for s in data['summaries'] if s['scope']=='all'],indent=2))
