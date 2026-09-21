"""Audit one identical explicit-order fixture across frozen full-Agent experiments."""
import hashlib,json,sys
from pathlib import Path
from continuation_cases import cases
ROOT=Path(__file__).resolve().parents[1]


def main(output):
    fixture=next(c for c in cases() if c['id']=='repair_failure')
    rows=[];excluded=[]
    for manifest_path in sorted((ROOT/'results/experiments').glob('*/manifest.json')):
        folder=manifest_path.parent;report_path=folder/'report.json'
        if not report_path.exists():continue
        manifest=json.loads(manifest_path.read_text())
        job=next((j for j in manifest.get('cases',[]) if j.get('id')==fixture['id']),None)
        if job is None:continue
        if job['prompt']!=fixture['prompt'] or job['files']!=fixture['files']:
            excluded.append(dict(experiment=folder.name,reason='different prompt or initial files'));continue
        for row in json.loads(report_path.read_text()):
            if row.get('task')!=fixture['id'] or row.get('arm')=='native':continue
            events_path=folder/(fixture['id']+'-'+row['arm'])/'events.jsonl'
            if not events_path.exists():
                excluded.append(dict(experiment=folder.name,arm=row['arm'],reason='missing events'));continue
            chats=[m for m in row.get('metrics',[]) if m.get('action')=='chat' and m.get('generic_plan')]
            first=next((e for line in events_path.read_text().splitlines() if line.startswith('{') for e in [json.loads(line)] if e.get('type')=='tool_execution_start'),{})
            steps=first.get('args',{}).get('steps',[])
            first_step=steps[0] if steps else {}
            if not chats:
                excluded.append(dict(experiment=folder.name,arm=row['arm'],reason='missing generic-plan decision'));continue
            chat=chats[0];decision=chat.get('decision',{});scores=decision.get('logprobs',[]);index=decision.get('index')
            margin=None
            if isinstance(index,int) and len(scores)>1 and 0<=index<len(scores):
                margin=scores[index]-max(value for i,value in enumerate(scores) if i!=index)
            branch=chat.get('selected_branch','unknown')
            rows.append(dict(experiment=folder.name,arm=row['arm'],selected_branch=branch,
                native_selection=branch.startswith('tool:'),wrong_native_selection=branch.startswith('tool:') and branch!='tool:bash',
                first_tool=first_step.get('name'),first_arguments=first_step.get('arguments'),
                margin=margin,artifact_passed=row.get('validation',{}).get('passed'),
                report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
                events_sha256=hashlib.sha256(events_path.read_bytes()).hexdigest()))
    native=[r for r in rows if r['native_selection']];scored=[r for r in native if r['margin'] is not None]
    thresholds=[]
    for threshold in (.25,.5,1,2,4):
        routed=[r for r in scored if r['margin']<threshold]
        thresholds.append(dict(threshold=threshold,routed=len(routed),wrong_native_routed=sum(r['wrong_native_selection'] for r in routed),
            correct_native_routed=sum(not r['wrong_native_selection'] for r in routed),wrong_native_left=sum(r['wrong_native_selection'] for r in scored if r['margin']>=threshold)))
    report=dict(method='Retrospective census of identical repair_failure prompt and initial files; different experimental configurations, not IID trials. Expected first native tool is bash. This labels tool choice only, not generated command correctness. Threshold routing is hypothetical and has not executed a replacement plan.',
        prompt_sha256=hashlib.sha256(fixture['prompt'].encode()).hexdigest(),rows=rows,excluded=excluded,
        total_plan_trials=len(rows),native_selection_trials=len(native),wrong_native_selections=sum(r['wrong_native_selection'] for r in native),
        scored_native_trials=len(scored),thresholds=thresholds)
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','excluded')},indent=2))
    print('wrong native decisions',[(r['experiment'],r['arm'],r['margin']) for r in native if r['wrong_native_selection']])


if __name__=='__main__':main(Path(sys.argv[1]))
