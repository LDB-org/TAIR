"""Replay archived recovery admission locally; no model inference or speed claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge', ROOT/'integrations/pijit/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def main(output):
    archive = ROOT/'results/experiments/write-references-ablation-20260920-b'
    manifest = json.loads((archive/'manifest.json').read_text())
    report = dict(method='Offline replay of actual saved tool results against copied final files. '
                  'No inference, no new Agent task, no latency comparison. Candidate availability is not a hit.',
                  archive=archive.name, manifest_sha256=hashlib.sha256((archive/'manifest.json').read_bytes()).hexdigest(),
                  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__), ROOT/'integrations/pijit/bridge.py']}, cases=[])
    with tempfile.TemporaryDirectory(prefix='tair-recovery-admission-') as temporary:
        root = Path(temporary)
        bridge.STATE = root/'state'
        workspace = root/'workspace'
        for task in ['unique_base', 'unique_repeat', 'nullable_changed']:
            folder = archive/(task+'-tair')
            if workspace.exists():
                shutil.rmtree(workspace)
            shutil.copytree(folder/'project-after', workspace)
            events = [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
            messages = [e['message'] for e in events if e.get('type')=='message_end']
            prompt = next(m['content'] for m in messages if m['role']=='user')
            prompt = bridge.text_content(prompt)
            book = bridge.tool_plan.ToolContentBook(bridge.paths(str(workspace))/'tool-plan-codebook.sqlite3')
            before = book.count()
            candidates = book.candidates(prompt, {})
            start = time.perf_counter()
            learned = bridge.admit_recovered_mutations(dict(cwd=str(workspace),context=dict(messages=messages)),prompt)
            elapsed = time.perf_counter()-start
            job = next(j for j in manifest['cases'] if j['id']==task)
            check = subprocess.run([sys.executable,'-B','-c',job['check']],cwd=workspace,capture_output=True,timeout=15)
            assert check.returncode==0,check.stderr.decode()
            report['cases'].append(dict(task=task, entries_before=before, candidate_ids_before=[e['id'] for e in candidates],
                                       learning=learned, entries_after=book.count(), local_admission_seconds=elapsed,
                                       independent_artifact_check=True))
        first, repeat, already_admitted = report['cases']
        assert first['entries_before']==0 and first['learning']['admission_count']==1
        assert repeat['candidate_ids_before'] and repeat['learning']['admission_count']==1
        assert already_admitted['learning'] is None
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['cases'],ensure_ascii=False,indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]))
