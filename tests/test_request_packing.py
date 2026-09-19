from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from benchmark_request_packing import execute, scenarios, tools_for


def test_executor_rejects_unknown_source_and_outside_files(tmp_path):
    (tmp_path/'a.py').write_text('original')
    with pytest.raises(ValueError):
        execute(dict(op='write',path='a.py',content='replacement'),tmp_path,['a.py'],set())
    with pytest.raises(ValueError):
        execute(dict(op='write',path='../outside.py',content='x'),tmp_path,['a.py'],set())
    known=set()
    assert execute(dict(op='read',path='a.py'),tmp_path,['a.py'],known)['content']=='original'
    execute(dict(op='replace',path='a.py',old='original',new='changed'),tmp_path,['a.py'],known)
    assert (tmp_path/'a.py').read_text()=='changed'


def test_interfaces_preserve_operation_choices_and_observation_boundary():
    assert len(tools_for('single_plan'))==1
    assert tools_for('single_plan')[0]['function']['parameters']['properties']['steps']['maxItems']==8
    assert tools_for('single_step')[0]['function']['parameters']['properties']['steps']['maxItems']==1
    assert len(tools_for('native_multi'))==4
    seen,unseen=scenarios()[1:]
    assert seen['files']==unseen['files'] and seen['task']==unseen['task']
    assert seen['observed'] and not unseen['observed']


def test_only_unobserved_reads_require_yielding():
    from benchmark_request_packing import crosses_observation_boundary
    steps=[dict(op='read',path='a.py'),dict(op='write',path='a.py',content='changed')]
    assert crosses_observation_boundary(steps,set())
    assert not crosses_observation_boundary(steps,{'a.py'})
    assert not crosses_observation_boundary(steps[:1],set())
