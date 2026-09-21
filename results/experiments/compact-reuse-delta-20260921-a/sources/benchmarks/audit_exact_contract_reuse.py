"""Counterfactual exact-contract policy on recorded executed content reuse."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def main(experiment,output):
    if experiment!='first-tool-reuse-ablation-20260921-a':
        raise ValueError('This audit uses the matching frozen first-content oracle only')
    root=ROOT/'results/experiments'/experiment
    rows=json.loads((root/'report.json').read_text())
    jobs={j['id']:j for j in json.loads((root/'manifest.json').read_text())['cases']}
    evidence=json.loads((ROOT/'docs/FIRST_TOOL_REUSE_CONTENT_AUDIT.json').read_text())
    origins={};decisions=[]
    for row in rows:
        if row['arm']!='tair_general_reuse':continue
        chats={m['request_id']:m for m in row['metrics'] if m.get('action')=='chat' and m.get('request_id')}
        for metric in row['metrics']:
            for identity in metric.get('admitted',[]):
                parent=metric['parent_tool_call_id']
                assert parent in chats
                origins[identity]=dict(task=row['task'],contract=chats[parent]['plan_task'])
        checked=next(item for item in evidence if item['task']==row['task'] and item['arm']==row['arm'])
        for identity in checked.get('matched_reused_ids',[]):
            origin=origins[identity];current=chats[checked['request_id']]['plan_task']
            previous=origin['contract']
            source_path=jobs[origin['task']]['primary_file'];target_path=jobs[row['task']]['primary_file']
            decisions.append(dict(task=row['task'],entry_id=identity,origin_task=origin['task'],
                initial_content_passed=checked['initial_content_passed'],exact_contract_matches=previous==current,
                fixture_path_normalized_matches=previous.replace(source_path,'<destination>')==current.replace(target_path,'<destination>'),
                contract_sha256=hashlib.sha256(previous.encode()).hexdigest(),current_task_sha256=hashlib.sha256(current.encode()).hexdigest()))
    assert len(decisions)==5
    report=dict(experiment=experiment,arm='tair_general_reuse',decisions=decisions,
        correct_reuses_rejected_by_exact=sum(r['initial_content_passed'] and not r['exact_contract_matches'] for r in decisions),
        wrong_reuses_rejected_by_exact=sum(not r['initial_content_passed'] and not r['exact_contract_matches'] for r in decisions),
        method='Offline counterfactual on actual first executed reuse, admission-parent correlation, and prior independent first-content oracle. No model rerun or changed runtime policy.',
        limitation='Path-normalized diagnostic uses known benchmark primary-file metadata. It is not a general natural-language intent parser or a production applicability guarantee.')
    inputs=[root/'report.json',root/'manifest.json',ROOT/'docs/FIRST_TOOL_REUSE_CONTENT_AUDIT.json',Path(__file__)]
    report['input_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main(sys.argv[1],Path(sys.argv[2]))
