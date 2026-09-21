"""Report all predefined categories and completion failures without cherry-picking."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

from compare_protocol_sft import summarize


def audit(report):
    # Recompute field scores first; do not trust stored aggregate claims.
    summarize(report)
    cases={row['id']:row for row in report['cases']}
    groups={}
    for category in sorted({c['category'] for c in cases.values()}):
        groups[category]={}
        for mode in ['json','json_schema','hybrid_fields']:
            rows=[r for r in report['records'] if r['mode']==mode and cases[r['case_id']]['category']==category]
            groups[category][mode]={'runs':len(rows),'exact':sum(r['exact_match'] for r in rows),
                'valid':sum(r['valid'] for r in rows),'median_seconds':statistics.median(r['seconds'] for r in rows)}
    failures=[{'case_id':r['case_id'],'repeat':r['repeat'],'mode':r['mode'],
        'complete':r['complete'],'finish_reason':r['trace'][-1].get('finish_reason'),
        'tokens':r['generated_tokens_including_eos']} for r in report['records'] if not r['valid']]
    hybrid=[r for r in report['records'] if r['mode']=='hybrid_fields' and r['repeat']==0]
    contents=Counter(r['call']['arguments']['content'] for r in hybrid if r['valid'])
    repeated=[{'content':text,'count':count} for text,count in contents.items() if count>1]
    repeat_agreement=all(r['call']==other['call'] and r['complete']==other['complete']
        for r in report['records'] if r['repeat']==0
        for other in report['records'] if other['repeat']>0 and other['case_id']==r['case_id'] and other['mode']==r['mode'])
    return {'categories':groups,'incomplete_or_invalid':failures,
            'hybrid_repeated_contents_repeat0':repeated,'repeats_agree':repeat_agreement}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    report=json.loads(args.report.read_text())
    result={'source_sha256':hashlib.sha256(args.report.read_bytes()).hexdigest(),**audit(report)}
    with args.output.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False)
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
