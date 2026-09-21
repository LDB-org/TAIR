import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
from recovery_admission_cases import cases


@pytest.mark.parametrize('job',cases(),ids=lambda job:job['id'])
def test_transient_checker_fails_once_then_checks_semantics_and_cannot_be_modified(tmp_path,job):
    for name,content in job['files'].items():
        (tmp_path/name).write_text(content)
    source='''import json
def parse_jsonl(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('duplicate')
            result[key]=value
        return result
    return [json.loads(line, object_pairs_hook=HOOK) for line in text.splitlines() if line.strip()]
'''.replace('HOOK','pairs' if job['phase']=='changed' else 'None')
    (tmp_path/job['primary_file']).write_text(source)
    first=subprocess.run([sys.executable,'check_output.py'],cwd=tmp_path,capture_output=True)
    assert first.returncode!=0 and b'SIMULATED_TRANSIENT_SETUP_FAILURE' in first.stderr
    second=subprocess.run([sys.executable,'check_output.py'],cwd=tmp_path,capture_output=True)
    assert second.returncode==0,second.stderr
    accepted=subprocess.run([sys.executable,'-c',job['check']],cwd=tmp_path,capture_output=True)
    assert accepted.returncode==0,accepted.stderr
    (tmp_path/'check_output.py').write_text('pass\n')
    assert subprocess.run([sys.executable,'-c',job['check']],cwd=tmp_path,capture_output=True).returncode!=0


def test_repeated_workload_keeps_task_and_initial_state_identical():
    from benchmark_expanded_reuse import repeat_cases
    original=cases()
    repeated=repeat_cases(original,3)
    assert [j['phase'] for j in repeated]==['base','repeat','repeat','repeat','changed']
    assert len({j['id'] for j in repeated})==5
    for job in repeated[1:4]:
        assert {k:v for k,v in job.items() if k!='id'}=={k:v for k,v in original[1].items() if k!='id'}
    repeated[1]['files']['new']='changed'
    assert 'new' not in original[1]['files'] and 'new' not in repeated[2]['files']
    with pytest.raises(ValueError):repeat_cases(original,0)
