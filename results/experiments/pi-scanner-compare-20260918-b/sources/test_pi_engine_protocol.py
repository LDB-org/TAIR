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
