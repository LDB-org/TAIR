import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('pi_engine_protocol', Path(__file__).parents[1] / 'deploy/pi_engine_protocol.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Protocol = module.Protocol


def tool(name, props, required):
    return {'name': name, 'description': name, 'parameters': {'type': 'object', 'properties': props, 'required': required}}


def test_raw_code_is_not_a_structural_delimiter():
    p = Protocol([tool('write', {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content'])])
    call = {'name': 'write', 'arguments': {'path': 'a"b.py', 'content': '\nB\n[]\n"\\中文\n\x00'}}
    assert p.decode(p.encode(call), 'stop') == call
    with pytest.raises(ValueError):
        p.decode(p.encode(call), 'length')


def test_nested_edit_and_optional_values():
    edit = tool('edit', {'path': {'type': 'string'}, 'edits': {'type': 'array', 'items': {
        'type': 'object', 'properties': {'oldText': {'type': 'string'}, 'newText': {'type': 'string'}},
        'required': ['oldText', 'newText']}}}, ['path', 'edits'])
    bash = tool('bash', {'command': {'type': 'string'}, 'timeout': {'type': 'number'}}, ['command'])
    p = Protocol([edit, bash])
    call = {'name': 'edit', 'arguments': {'path': 'x.py', 'edits': [{'oldText': 'a\nb', 'newText': '\\"'}]}}
    assert p.decode(p.encode(call), 'stop') == call
    assert p.decode('B\n["echo hi",null]', 'stop')['arguments'] == {'command': 'echo hi'}
    for raw in ['Z\n[]', 'B\n["echo hi"]', 'B\n["echo hi","3"]', 'B\n[null,null]', 'B\n["hi",1e999]', 'B\n["hi",null]\nextra']:
        with pytest.raises(ValueError):
            p.decode(raw, 'stop')


def test_unsupported_constraints_fail_closed():
    with pytest.raises(ValueError):
        Protocol([tool('x', {'s': {'type': 'string', 'minLength': 1}}, ['s'])])
    with pytest.raises(ValueError):
        Protocol([tool('x', {'s': {'type': 'string'}}, ['unknown'])])
