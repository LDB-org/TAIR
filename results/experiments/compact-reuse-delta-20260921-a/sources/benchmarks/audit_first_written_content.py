"""Audit first completed relative primary-file writes for JSONL/JavaScript fixtures.

Usage: python benchmarks/audit_first_written_content.py EXPERIMENT OUTPUT_JSON
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
experiment=ROOT/'results/experiments'/sys.argv[1]
manifest=json.loads((experiment/'manifest.json').read_text())
rows=json.loads((experiment/'report.json').read_text());audit=[]
for row in rows:
    if row['arm']=='native':continue
    job=next(j for j in manifest['cases'] if j['id']==row['task'])
    assert job['group'] in ('jsonl','unique')
    records={m['request_id']:m for m in row['metrics'] if m.get('action')=='chat' and m.get('request_id')}
    events=[json.loads(l) for l in (experiment/(row['task']+'-'+row['arm'])/'events.jsonl').read_text().splitlines() if l.startswith('{')]
    starts={};found=None
    for event in events:
        if event.get('type')=='tool_execution_start':starts[event['toolCallId']]=event
        if event.get('type')!='tool_execution_end' or event.get('toolName')!='plan':continue
        start=starts[event['toolCallId']];steps=start['args']['steps']
        blocks=event['result'].get('content',[])
        texts=[b['text'] for b in blocks if b.get('type')=='text']
        parsed=json.loads(''.join(texts))
        completed=parsed['completed'] if event.get('isError') else parsed['results']
        assert len(completed)<=len(steps)
        for step,done in zip(steps,completed):
            assert done['name']==step['name']
            if step['name']!='write' or step['arguments']['path']!=job['primary_file']:continue
            source=step['arguments']['content'];assert isinstance(source,str)
            metric=records[event['toolCallId']]
            found=dict(source=source,request_id=event['toolCallId'],reused_ids=metric.get('reused_content_ids',[]),selected_id=metric.get('selected_content_id'))
            break
        if found:break
    item=dict(task=row['task'],arm=row['arm'],phase=row['phase'],final_artifact_passed=row['validation']['passed'],first_completed_relative_write_found=bool(found))
    if found:
        digest=hashlib.sha256(found['source'].encode()).hexdigest()
        book={r[0]:r[1] for r in json.loads((experiment/('final-book-'+row['arm']+'.json')).read_text())}
        matched=[identity for identity in found['reused_ids'] if book.get(identity)==digest]
        with tempfile.TemporaryDirectory(prefix='tair-first-content-oracle-') as temp:
            project=Path(temp)
            for name,content in job['files'].items():(project/name).write_text(content)
            (project/job['primary_file']).write_text(found['source'])
            check=subprocess.run([sys.executable,'-B','-c',job['check']],cwd=project,capture_output=True,text=True,timeout=15)
        item.update(source_sha256=digest,request_id=found['request_id'],selected_id=found['selected_id'],matched_reused_ids=matched,initial_content_passed=check.returncode==0,oracle_stderr=check.stderr)
    audit.append(item)
Path(sys.argv[2]).write_text(json.dumps(audit,indent=2)+'\n')
print(json.dumps(audit,indent=2))
