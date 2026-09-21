"""Source-bound typed operations for the retained-KV direct classifier endpoint."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('compact', Path(__file__).with_name('compact_structural_protocol.py'))
compact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compact)

OPS = {
    'arg': ('Add positional string arguments, such as CLI option aliases.', 'Each edit is [call_target,string_value].'),
    'kw': ('Set typed keyword arguments or defaults of existing calls.', 'Each edit is [call_target,keyword,value]. Use JSON values, not Python expression strings.'),
    'return_if': ('Insert an early conditional return at function entry.', 'Each edit is [function_target,condition_expression,result_expression]. Both expressions are Python source strings.'),
    'raise_if': ('Insert a conditional exception at function entry, before existing code.', 'Each edit is [function_target,condition_expression,exception_type,message].'),
    'catch': ('Catch an exception raised by an existing statement and return a value. Do not use a conditional guard for this.', 'Each edit is [statement_target,exception_type,return_value].'),
}


def tuple_schema(items):
    return {'type': 'array', 'prefixItems': items, 'minItems': len(items), 'maxItems': len(items), 'items': False}


def operation_tools(source, allowed):
    aliases = compact.scoped_selectors(source, allowed)
    nodes = compact.base.catalogue(source)
    const = lambda value: {'const': value}
    string = {'type': 'string'}
    scalar = {'type': ['string', 'number', 'boolean', 'null']}
    exception = {'type': 'string', 'enum': list(compact.EXCEPTIONS)}
    types = {'bool': {'type': 'boolean'}, 'int': {'type': 'integer'}, 'number': {'type': 'number'},
             'string': string, 'null': {'type': 'null'}, 'separators': tuple_schema([string, string])}
    candidates = {op: [] for op in OPS}
    for target, key in aliases['C'].items():
        candidates['arg'].append([const(target), string])
        for keyword in compact.keyword_slots(nodes[key]):
            kind = compact.value_kind(nodes[key], keyword)
            if kind:
                candidates['kw'].append([const(target), const(keyword), types[kind]])
    for target in aliases['F']:
        candidates['return_if'].append([const(target), string, string])
        candidates['raise_if'].append([const(target), string, exception, string])
    for target in aliases['S']:
        candidates['catch'].append([const(target), exception, scalar])
    tools = []
    mixed = []
    for op, choices in candidates.items():
        if not choices:
            continue
        items = {'oneOf': [tuple_schema(c) for c in choices]}
        tools.append({'name': op, 'description': OPS[op][0], 'parameters': {
            'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': items}})
        mixed.extend(tuple_schema([const(op), *c]) for c in choices)
    tools.append({'name': 'mixed', 'description': 'Use only when the task requires multiple different operation kinds.',
                  'parameters': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': {'oneOf': mixed}}})
    return tools


def continuation_instruction(op):
    if op == 'mixed':
        return 'Generate the compact typed edit array for the original task, retaining the operation name in every edit. No explanations.'
    return ('Selected operation: '+op+'. Generate ONLY an array of 1 to 8 edits. '+OPS[op][1]+
            ' Omit the operation name: the engine supplies it. Use source target names from the original instructions. Satisfy the entire original task; no source blocks or explanations.')


def decode(source, source_hash, call, allowed):
    op = call['name']
    if op not in OPS and op != 'mixed':
        raise ValueError('Unknown operation')
    args = call['arguments']
    if not isinstance(args, list) or not all(isinstance(a, list) for a in args):
        raise ValueError('Expected edit tuples')
    edits = args if op == 'mixed' else [[op, *args_] for args_ in args]
    return compact.typed_decode(source, source_hash, json.dumps(edits, separators=(',', ':'), ensure_ascii=False), 'stop', allowed)
