from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'benchmarks'))
from robustness_cases import cases
from continuation_cases import mutation_cases


@pytest.mark.parametrize('changed', [False, True])
@pytest.mark.parametrize('drop_positive', [False, True])
def test_nullable_oracle_checks_positive_groups(tmp_path, changed, drop_positive):
    job=next(j for j in cases() if j['id']==('nullable_changed' if changed else 'nullable_base'))
    query='SELECT station, COALESCE(SUM(value),0) AS total FROM readings GROUP BY station'
    conditions=[]
    if changed: conditions.append('COUNT(value)>0')
    if drop_positive: conditions.append('COALESCE(SUM(value),0)<=0')
    if conditions: query+=' HAVING '+' AND '.join(conditions)
    query+=' ORDER BY station'
    (tmp_path/job['primary_file']).write_text(query)
    check=subprocess.run([sys.executable,'-B','-c',job['check']],cwd=tmp_path,capture_output=True,timeout=10)
    assert (check.returncode==0) == (not drop_positive),check.stderr


def test_mutation_oracle_rejects_stale_content_under_identical_request(tmp_path):
    import json
    base,repeat,changed=mutation_cases()
    assert base['prompt']==repeat['prompt']==changed['prompt']
    assert base['files']==repeat['files'] and base['files']!=changed['files']
    for fixture,passed in [(base,False),(changed,True)]:
        content=json.loads(fixture['files']['service.json']);content['service']['port']=8443
        (tmp_path/'service.json').write_text(json.dumps(content))
        check=subprocess.run([sys.executable,'-B','-c',changed['check']],cwd=tmp_path,capture_output=True,timeout=10)
        assert (check.returncode==0)==passed,check.stderr
