import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'deploy'))
from plan_template import capture, bind


def test_capture_and_bind_only_destination_without_shell_interpolation():
    original=[dict(name='write',arguments=dict(path='old.py',content='value = "old.py"\n')),
              dict(name='bash',arguments=dict(command='python3 -m py_compile old.py'))]
    source=capture(original)
    destination='nested/a; touch PWNED $(id).py'
    steps=bind(source,destination)
    assert steps[0]['arguments']==dict(path=destination,content='value = "old.py"\n')
    assert shlex.split(steps[1]['arguments']['command'])==['python3','-m','py_compile',destination]
    assert capture(steps)==source


def test_does_not_learn_unknown_or_extra_shell_operations():
    write=dict(name='write',arguments=dict(path='x.py',content='x=1'))
    for command in ['python3 -m py_compile x.py; echo bad', 'python3 x.py', 'python3 -m py_compile other.py']:
        assert capture([write,dict(name='bash',arguments=dict(command=command))]) is None
    assert capture([write]) is None


def test_template_decode_expands_to_native_tools_and_keeps_eight_step_limit():
    import pytest
    from tool_plan import branches, decode, obj
    tools=[dict(name='write',description='write',parameters=obj(dict(path=dict(type='string'),content=dict(type='string')))),
           dict(name='bash',description='bash',parameters=obj(dict(command=dict(type='string'))))]
    entry=dict(id='template',source=json.dumps(dict(version=1,content='x=1')),contract='write and compile',plan_template=True)
    options=branches(tools,[entry])
    def response(steps):
        return dict(decision=dict(index=2),same_engine_session=True,finish_reason='stop',classification_control_records=1,
                    call=dict(name='plan',arguments=dict(steps=steps)))
    reuse=dict(name='reuse_plan',arguments=dict(path='new.py'))
    call,ids=decode(response([reuse]),tools,[entry],options)
    assert ids==['template'] and [s['name'] for s in call['arguments']['steps']]==['write','bash']
    with pytest.raises(Exception):
        decode(response([reuse]*5),tools,[entry],options)
