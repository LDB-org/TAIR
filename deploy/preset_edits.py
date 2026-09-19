"""Versioned, deterministic edit templates; no model calls or executable expressions."""
import ast
import math

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
    return set_cli_keyword(source, option, 'default', expected_default, value)


def set_cli_keyword(source, option, keyword, expected_default, value):
    if keyword not in ('default', 'help', 'required'):
        raise ValueError('Unsupported CLI keyword')
    if type(value) not in (int, float, str, bool) or type(value) is not type(expected_default):
        raise ValueError('Expected same-type literal values')
    if type(value) is float and not math.isfinite(value):
        raise ValueError('Nonfinite default')
    if keyword == 'help' and type(value) is not str or keyword == 'required' and type(value) is not bool:
        raise ValueError('Wrong keyword value type')
    protected = ('argparse', 'int', 'float', 'str', 'bool')
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
    main_guards = [n for n in tree.body if isinstance(n, ast.If)
                   and ast.dump(n.test) == ast.dump(ast.parse('__name__ == "__main__"', mode='eval').body)]
    owners = [n for n in ast.walk(tree) if (isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef))
              or n in main_guards)
              and any(isinstance(s, ast.Expr) and s.value is call for s in n.body)]
    if len(owners) != 1:
        raise ValueError('Preset requires a direct statement in a function, module or top-level main guard')
    owner = owners[0]
    bindings = [n for n in owner.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == parser
                and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'argparse.ArgumentParser'
                and n.lineno < call.lineno]
    scope = tree if owner in main_guards else owner
    stores = [n for n in ast.walk(scope) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
              and n.id == parser]
    if len(bindings) != 1 or len(stores) != 1 or parser in protected:
        raise ValueError('Preset requires an unambiguous argparse.ArgumentParser binding')
    imports = tree.body + (owner.body if owner in main_guards else [])
    if not any(isinstance(n, ast.Import) and (owner not in main_guards or n.lineno < bindings[0].lineno)
               and any(a.name == 'argparse' and a.asname in (None, 'argparse') for a in n.names)
               for n in imports):
        raise ValueError('Preset requires import argparse')
    for node in ast.walk(tree):
        if ((isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in protected)
                or (isinstance(node, ast.arg) and node.arg in (*protected, parser))
                or (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in protected)):
            raise ValueError('Shadowed parser or builtin binding is unsupported')
        if isinstance(node, ast.ImportFrom) and any((a.asname or a.name) in protected or a.name == '*'
                                                  for a in node.names):
            raise ValueError('Shadowed parser or builtin import is unsupported')
        if isinstance(node, ast.Import) and any((a.asname or a.name.split('.')[0]) in protected
                                               and a.name != 'argparse' for a in node.names):
            raise ValueError('Shadowed parser or builtin import is unsupported')
    keywords = {k.arg: k.value for k in call.keywords}
    if None in keywords or len(keywords) != len(call.keywords):
        raise ValueError('Expanded or duplicate keywords are unsupported')
    if keyword == 'default':
        converter = keywords.get('type')
        expected_type = {int: 'int', float: 'float', str: 'str', bool: None}[type(value)]
        implicit_string = type(value) is str and converter is None
        boolean_action = (type(value) is bool and converter is None
                          and isinstance(keywords.get('action'), ast.Constant)
                          and keywords['action'].value in ('store_true', 'store_false'))
        if not (implicit_string or boolean_action or isinstance(converter, ast.Name)
                and converter.id == expected_type):
            raise ValueError('Unsupported argument converter')
    default = keywords.get(keyword)
    try:
        old = ast.literal_eval(default)
    except (ValueError, TypeError):
        raise ValueError('Requires an existing literal keyword') from None
    if type(old) is not type(expected_default) or old != expected_default:
        raise ValueError('Keyword changed or has an unsupported type')
    # AST offsets are UTF-8 byte offsets, not Python character indices.
    lines = source.encode('utf-8').splitlines(keepends=True)
    begin = sum(map(len, lines[:default.lineno - 1])) + default.col_offset
    end = sum(map(len, lines[:default.end_lineno - 1])) + default.end_col_offset
    encoded = source.encode('utf-8')
    updated = (encoded[:begin] + repr(value).encode() + encoded[end:]).decode('utf-8')
    compile(updated, '<preset-edit>', 'exec')
    return updated
