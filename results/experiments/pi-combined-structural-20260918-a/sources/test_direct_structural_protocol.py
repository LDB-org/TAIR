import importlib.util
from pathlib import Path

import jsonschema
import pytest

spec = importlib.util.spec_from_file_location('direct_structural', Path(__file__).parents[1]/'deploy/direct_structural_protocol.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SOURCE = 'def f(x):\n    value = allocate(x, size=3)\n    return value\n'


def apply(op, args, source=SOURCE, digest=None):
    allowed = set(m.compact.base.catalogue(source))
    tools = {t['name']: t['parameters'] for t in m.operation_tools(source, allowed)}
    jsonschema.validate(args, tools[op])
    return m.decode(source, digest or m.compact.base.digest(source), {'name': op, 'arguments': args}, allowed)


def test_selected_operation_and_mixed_operations_execute():
    changed = apply('kw', [['allocate', 'size', 6]])
    assert 'size=6' in changed
    changed = apply('mixed', [['kw', 'allocate', 'size', 6], ['return_if', 'f', 'not x', '0']])
    ns = {'allocate': lambda x, size: x * size}
    exec(changed, ns)
    assert ns['f'](0) == 0
    assert ns['f'](2) == 12


@pytest.mark.parametrize('args', [[], [['missing', 'size', 6]], [['allocate', 'missing', 6]], [['allocate', 'size', '6']], [['allocate', 'size', True]]])
def test_schema_rejects_invalid_target_slot_and_type(args):
    with pytest.raises(jsonschema.ValidationError):
        apply('kw', args)


def test_stale_source_rejected_after_valid_schema():
    with pytest.raises(ValueError):
        apply('kw', [['allocate', 'size', 6]], digest='stale')


def test_source_scope_is_enforced_in_schema_and_decoder():
    source = 'a = first(size=1)\nb = second(size=2)\n'
    allowed = m.compact.task_scope(source, 'Set second size to 3.')
    tools = {t['name']: t['parameters'] for t in m.operation_tools(source, allowed)}
    call = {'name': 'kw', 'arguments': [['first', 'size', 3]]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(call['arguments'], tools['kw'])
    with pytest.raises(ValueError):
        m.decode(source, m.compact.base.digest(source), call, allowed)
