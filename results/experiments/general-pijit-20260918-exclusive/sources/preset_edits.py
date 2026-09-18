"""Versioned, deterministic edit templates; no model calls or executable expressions."""
import ast

PRESET_ID = 'argparse_int_default/v1'
TOOL = {
    'name': 'set_cli_default',
    'description': 'Set one existing integer argparse option default in a Python file. '
                   'Read source first. Supply its option name, observed integer default and new integer value. '
                   'Requires a unique option, explicit type=int and a simple argparse.ArgumentParser binding. '
                   'Only the default literal changes; other edits use compact_edit.',
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {'path': {'type': 'string'}, 'option': {'type': 'string'},
                       'expected_default': {'type': 'integer'}, 'value': {'type': 'integer'}},
        'required': ['path', 'option', 'expected_default', 'value'],
    },
}


def set_cli_default(source, option, expected_default, value):
    if not isinstance(option, str) or not option.startswith('-'):
        raise ValueError('Expected a CLI option name')
    if type(expected_default) is not int or type(value) is not int:
        raise ValueError('Preset requires integer expected_default and value')
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == 'add_argument'
             and any(isinstance(a, ast.Constant) and a.value == option for a in n.args)]
    if len(calls) != 1:
        raise ValueError('Preset requires a unique option target')
    call = calls[0]
    if not isinstance(call.func.value, ast.Name):
        raise ValueError('Unsupported parser receiver')
    parser = call.func.value.id
    owners = [n for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef))
              and any(isinstance(s, ast.Expr) and s.value is call for s in n.body)]
    if len(owners) != 1:
        raise ValueError('Preset requires a direct statement in a function or module')
    owner = owners[0]
    bindings = [n for n in owner.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == parser
                and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'argparse.ArgumentParser'
                and n.lineno < call.lineno]
    stores = [n for n in ast.walk(owner) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
              and n.id == parser]
    if len(bindings) != 1 or len(stores) != 1 or parser in ('argparse', 'int'):
        raise ValueError('Preset requires an unambiguous argparse.ArgumentParser binding')
    if not any(isinstance(n, ast.Import) and any(a.name == 'argparse' and a.asname in (None, 'argparse')
               for a in n.names) for n in tree.body):
        raise ValueError('Preset requires import argparse')
    for node in ast.walk(tree):
        if ((isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in ('argparse', 'int'))
                or (isinstance(node, ast.arg) and node.arg in ('argparse', 'int', parser))
                or (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in ('argparse', 'int'))):
            raise ValueError('Shadowed parser or builtin binding is unsupported')
        if isinstance(node, ast.ImportFrom) and any((a.asname or a.name) in ('argparse', 'int') or a.name == '*'
                                                  for a in node.names):
            raise ValueError('Shadowed parser or builtin import is unsupported')
        if isinstance(node, ast.Import) and any((a.asname or a.name.split('.')[0]) in ('argparse', 'int')
                                               and a.name != 'argparse' for a in node.names):
            raise ValueError('Shadowed parser or builtin import is unsupported')
    keywords = {k.arg: k.value for k in call.keywords}
    if None in keywords or len(keywords) != len(call.keywords):
        raise ValueError('Expanded or duplicate keywords are unsupported')
    if not isinstance(keywords.get('type'), ast.Name) or keywords['type'].id != 'int':
        raise ValueError('Preset requires explicit type=int')
    default = keywords.get('default')
    try:
        old = ast.literal_eval(default)
    except (ValueError, TypeError):
        raise ValueError('Preset requires an existing literal integer default') from None
    if type(old) is not int or old != expected_default:
        raise ValueError('Default changed or has an unsupported type')
    # AST offsets are UTF-8 byte offsets, not Python character indices.
    lines = source.encode('utf-8').splitlines(keepends=True)
    begin = sum(map(len, lines[:default.lineno - 1])) + default.col_offset
    end = sum(map(len, lines[:default.end_lineno - 1])) + default.end_col_offset
    encoded = source.encode('utf-8')
    updated = (encoded[:begin] + str(value).encode() + encoded[end:]).decode('utf-8')
    compile(updated, '<preset-edit>', 'exec')
    return updated
