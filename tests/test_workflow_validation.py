from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'benchmarks'))
from workflow_validation import validate_workflow, apply_workflow_result


@pytest.mark.parametrize('command,expected',[
    ('python3 check_calc.py',True),('command -- python3 check_calc.py',True),
    ('cd . && python3 check_calc.py',True),('cd . && command -- python3 check_calc.py',True),
    ('cd /different-workspace && python3 check_calc.py',False),
    ('python3 other.py',False),('python3 check_calc.py; true',False),('"unterminated',False)])
@pytest.mark.parametrize('plan',[False,True])
def test_first_command_validation(tmp_path,command,expected,plan):
    job=dict(workflow=dict(first_command=['python3','check_calc.py']))
    step=dict(name='bash',arguments=dict(command=command))
    event=dict(type='tool_execution_start',toolName='plan' if plan else 'bash',
               args=dict(steps=[step]) if plan else step['arguments'])
    assert validate_workflow(job,[event],tmp_path)['passed']==expected


def test_successful_artifact_cannot_hide_wrong_order_or_modified_checker(tmp_path):
    job=dict(workflow=dict(first_command=['python3','check_calc.py'],unchanged_files=['check_calc.py']),files={'check_calc.py':'assert True\n'})
    (tmp_path/'check_calc.py').write_text(job['files']['check_calc.py'])
    event=dict(type='tool_execution_start',toolName='plan',args=dict(steps=[dict(name='read',arguments=dict(path='calc.py')),dict(name='bash',arguments=dict(command='python3 check_calc.py'))]))
    result=validate_workflow(job,[event],tmp_path)
    assert not result['passed'] and result['checks']['unchanged:check_calc.py']
    row=dict(passed=True,validation=dict(passed=True))
    apply_workflow_result(row,result)
    assert row['artifact_passed'] and not row['passed']
    event['args']['steps']=event['args']['steps'][1:]
    (tmp_path/'check_calc.py').write_text('different checker')
    result=validate_workflow(job,[event],tmp_path)
    assert result['checks']['requested_command_first'] and not result['passed']
    (tmp_path/'check_calc.py').unlink()
    assert not validate_workflow(job,[event],tmp_path)['passed']


def test_no_workflow_metadata_preserves_artifact_result(tmp_path):
    validation=validate_workflow({},[],tmp_path)
    assert validation==dict(passed=True,checks={})
    row=dict(passed=False,validation=dict(passed=False))
    apply_workflow_result(row,validation)
    assert not row['passed']
