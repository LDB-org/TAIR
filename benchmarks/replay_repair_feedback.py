"""Offline replay of repair feedback against frozen real task histories."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from probe_candidate_binding import load

ROOT=Path(__file__).resolve().parents[1]


def main(output):
    b=load('feedback_bridge',ROOT/'integrations/pijit/bridge.py')
    archive=ROOT/'results/experiments/combined-reuse-ablation-20260921-a'
    manifest=json.loads((archive/'manifest.json').read_text())
    report=dict(archive=archive.name,method='Offline replay; isolated copied files and books. No inference, new tool execution, or speed claim.',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       [Path(__file__),ROOT/'deploy/tool_plan.py',ROOT/'integrations/pijit/bridge.py']},cases=[])
    for name,seed in [('unique_changed','unique_base'),('jsonl_repeat_2','jsonl_base'),('jsonl_changed','jsonl_base')]:
        with tempfile.TemporaryDirectory(prefix='tair-feedback-') as temp:
            workspace=Path(temp)/'workspace';b.STATE=Path(temp)/'state'
            folder=archive/(name+'-tair_combined');shutil.copytree(folder/'project-after',workspace)
            messages=[e['message'] for line in (folder/'events.jsonl').read_text().splitlines()
                      if (e:=json.loads(line)).get('type')=='message_end']
            task=b.text_content(next(m for m in messages if m['role']=='user')['content'])
            job=next(j for j in manifest['cases'] if j['id']==name)
            seed_job=next(j for j in manifest['cases'] if j['id']==seed)
            seed_source=(archive/(seed+'-tair_combined')/'project-after'/seed_job['primary_file']).read_text()
            book=b.tool_plan.ToolContentBook(b.paths(str(workspace))/'tool-plan-codebook.sqlite3')
            identity,=book.admit([(seed_job['prompt'],seed_source,'execution only')])
            before=[e['id'] for e in book.candidates(task,{},repair_feedback=True)]
            records=b.record_repaired_content(dict(cwd=str(workspace),context=dict(messages=messages)),task)
            after=[e['id'] for e in book.candidates(task,{},repair_feedback=True)]
            control=[e['id'] for e in book.candidates(seed_job['prompt'],{},repair_feedback=True)]
            check=subprocess.run([sys.executable,'-B','-c',job['check']],cwd=workspace,capture_output=True,timeout=15)
            assert check.returncode==0,check.stderr
            assert identity in before and identity in control
            if name=='unique_changed':assert records and identity not in after
            else:assert not records and identity in after
            # A newer contract containing identical bytes must not bypass the rejection.
            alias,=book.admit([(seed_job['prompt']+' duplicate',seed_source,'execution only')])
            after_alias=[e['id'] for e in book.candidates(task,{},repair_feedback=True)]
            if records:assert alias not in after_alias
            report['cases'].append(dict(task=name,records=records,candidate_ids_before=before,candidate_ids_after=after,
                original_task_still_eligible=True,independent_final_artifact_check=True,alias_ids_after=after_alias))
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['cases'],ensure_ascii=False,indent=2))


if __name__=='__main__':main(Path(sys.argv[1]))
