"""Independently verify paired evidence and summarize protocol adaptation."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from schema_toolcall import valid_call


def summarize(report):
    cases={c['id']:c for c in report['cases']}
    result={}
    for mode in ['json','json_schema','hybrid_fields']:
        rows=[r for r in report['records'] if r['mode']==mode]
        scores={'valid':0,'exact':0,'tool':0,'priority':0,'content':0}
        for row in rows:
            case=cases[row['case_id']]
            call=row['call']
            valid=row['complete'] and valid_call(call)
            tool=bool(valid and call['name']==case['name'])
            priority=bool(valid and call['arguments']['priority']==case['priority'])
            content=bool(valid and call['arguments']['content']==case['content'])
            exact=tool and priority and content
            assert row['valid']==valid and row['exact_match']==exact
            assert row['discrete_correct']==(tool and priority)
            if valid: assert json.loads(row['wire'])==call
            for key,value in zip(scores,[valid,exact,tool,priority,content]): scores[key]+=int(value)
        result[mode]={'runs':len(rows),'unique_cases':len({r['case_id'] for r in rows}),**scores,
            'median_seconds':statistics.median(r['seconds'] for r in rows),
            'output_tokens':sum(r['generated_tokens_including_eos'] for r in rows),
            'request_count':sum(r['request_count'] for r in rows),
            'failures_repeat0':[r['case_id'] for r in rows if r['repeat']==0 and not r['exact_match']]}
        assert result[mode]['median_seconds']==report['summary'][mode]['median_seconds']
        assert scores['exact']==report['summary'][mode]['exact_match']
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--trained',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    a,b=[json.loads(path.read_text()) for path in [args.base,args.trained]]
    for key in ['cases','engine_settings','versions','environment','runner_sha256','protocol_runner_sha256']:
        assert a[key]==b[key], f'Comparison mismatch: {key}'
    assert {(r['repeat'],r['case_id'],r['mode']) for r in a['records']}=={(r['repeat'],r['case_id'],r['mode']) for r in b['records']}
    result={'base':summarize(a),'trained':summarize(b),
            'source_sha256':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in [args.base,args.trained]}}
    with args.output.open('x') as f: json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
