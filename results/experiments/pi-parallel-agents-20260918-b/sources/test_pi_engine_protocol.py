import importlib.util
import io
import json
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


def test_raw_required_tail_preserves_optional_parameters_and_multiline_command():
    bash = tool('bash', {'command': {'type': 'string'}, 'timeout': {'type': 'number'}}, ['command'])
    p = Protocol([bash], raw_required_tail=True)
    command = 'python3 - <<\'PY\'\nprint("中文\\n[]")\nPY\n'
    for args, head in [({'command': command}, '[null]'), ({'command': command, 'timeout': 10}, '[10]')]:
        call = {'name': 'bash', 'arguments': args}
        frame = 'A\n' + head + '\n' + command
        assert p.encode(call) == frame
        assert p.decode(frame, 'stop') == call
        with pytest.raises(ValueError):
            p.decode(frame, 'length')
    with pytest.raises(ValueError):
        p.decode('A\n["bad timeout"]\n' + command, 'stop')


def test_raw_required_tail_does_not_displace_required_nested_array():
    edit = tool('edit', {'path': {'type': 'string'}, 'edits': {'type': 'array', 'items': {'type': 'string'}}}, ['path', 'edits'])
    call = {'name': 'edit', 'arguments': {'path': 'x.py', 'edits': ['a', 'b']}}
    old, new = Protocol([edit]), Protocol([edit], raw_required_tail=True)
    assert old.encode(call) == new.encode(call)
    assert new.decode(new.encode(call), 'stop') == call


@pytest.mark.parametrize('name,field', [('read', 'path'), ('find', 'pattern'), ('grep', 'pattern')])
def test_raw_optimization_keeps_short_identifiers_in_bounded_tuple(name, field):
    schema = tool(name, {field: {'type': 'string'}, 'limit': {'type': 'number'}}, [field])
    old, new = Protocol([schema]), Protocol([schema], raw_required_tail=True)
    assert old.regex == new.regex
    assert new.decode('A\n["catalog.py",null]', 'stop')['arguments'] == {field: 'catalog.py'}
    with pytest.raises(ValueError):
        new.decode('A\n[null]\ncatalog.py\nB\n[]\necho hi', 'stop')


@pytest.mark.parametrize('finish,accepted', [('tool_calls', True), ('length', False)])
def test_native_baseline_preserves_prose_and_rejects_truncation(monkeypatch, finish, accepted):
    sent = []
    def response(req, timeout):
        sent.append(json.loads(req.data))
        return io.StringIO(json.dumps({'choices': [{'finish_reason': finish, 'message': {
            'content': 'Working.', 'tool_calls': [{'function': {'name': 'write',
                'arguments': json.dumps({'path': 'x.py', 'content': 'print("ok")\n'})}}]}}]}))
    monkeypatch.setattr(module.urllib.request, 'urlopen', response)
    result = module.infer({'protocol_mode': 'native', 'systemPrompt': 'Use tools', 'session_id': 'test',
                          'tools': [tool('write', {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content'])],
                          'messages': [{'role': 'user', 'content': 'Write a file'}]}, 'http://localhost')
    assert (result['call'] is not None) == accepted
    assert 'structured_outputs' not in sent[0]
    assert sent[0]['tools'][0]['function']['name'] == 'write'
    if accepted:
        assert result['native_text'] == 'Working.'
        assert result['call']['arguments']['content'] == 'print("ok")\n'
