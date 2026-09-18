"""Compact source-derived selectors and bounded keyword slots for structural edits."""
import ast
import builtins
import importlib.util
import inspect
import json
import math
from pathlib import Path
import re

spec=importlib.util.spec_from_file_location('structural',Path(__file__).with_name('structural_edit_protocol.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
SIGNATURES={'print':builtins.print,'json.dumps':json.dumps}
KINDS={'arg':'C','kw':'C','guard_return':'F','guard_raise':'F','catch_return':'S'}
STRING=r'"([^"\\\x00-\x1f]|\\(["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'


def selectors(source):
    result={kind:{} for kind in 'CFS'}
    for key,node in base.catalogue(source).items():
        kind=key[0]
        if kind=='F':name=node.name
        elif kind=='C':
            name=node.args[0].value if node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str) else ast.unparse(node.func)
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            name=ast.unparse(node.targets[0] if isinstance(node,ast.Assign) else node.target)
        else:name=f'{type(node).__name__.lower()}@{node.lineno}'
        # Keep locators small and prevent source text from becoming instructions.
        if not re.fullmatch(r'[\w.@-]{1,60}',name):name=key
        if name in result[kind]:name=f'{name}@{node.lineno}_{node.col_offset}'
        result[kind][name]=key
    return result


def keyword_slots(node):
    names={k.arg for k in node.keywords if k.arg is not None}
    function=SIGNATURES.get(ast.unparse(node.func))
    if function:
        names.update(k for k,p in inspect.signature(function).parameters.items()
                     if p.kind in (p.KEYWORD_ONLY,p.POSITIONAL_OR_KEYWORD))
    # A positional parameter already supplied cannot also be supplied by keyword.
    if function:
        positional=[k for k,p in inspect.signature(function).parameters.items()
                    if p.kind in (p.POSITIONAL_ONLY,p.POSITIONAL_OR_KEYWORD)]
        names.difference_update(positional[:len(node.args)])
    return sorted(names)


def quoted(value):
    return re.escape(json.dumps(value,ensure_ascii=False))


def grammar(source):
    mapping=selectors(source);nodes=base.catalogue(source);choices=[]
    for op,kind in KINDS.items():
        for name,key in mapping[kind].items():
            if op=='kw':
                slots=keyword_slots(nodes[key])
                if slots:choices.append(r'\["kw",'+quoted(name)+',('+ '|'.join(map(quoted,slots))+'),'+STRING+r'\]')
            else:
                count=1 if op=='arg' else 2
                choices.append(r'\['+quoted(op)+','+quoted(name)+(','+STRING)*count+r'\]')
    edit='('+'|'.join(choices)+')'
    return r'\['+edit+'(,'+edit+r'){0,7}\]'


def decode(source,expected_hash,raw,finish):
    if base.digest(source)!=expected_hash:raise ValueError('Stale source version')
    if finish!='stop':raise ValueError('Incomplete output')
    edits=json.loads(raw)
    if not isinstance(edits,list) or not 1<=len(edits)<=8:raise ValueError('Need 1..8 edits')
    mapping=selectors(source);nodes=base.catalogue(source);translated=[]
    for edit in edits:
        if not isinstance(edit,list) or len(edit) not in (3,4) or not all(isinstance(v,str) for v in edit):raise ValueError('Invalid edit')
        op,target,*args=edit
        if op not in KINDS or target not in mapping[KINDS[op]]:raise ValueError('Unknown operation or target')
        key=mapping[KINDS[op]][target]
        if op=='kw' and (len(args)!=2 or args[0] not in keyword_slots(nodes[key])):raise ValueError('Unsupported keyword slot')
        if op=='guard_raise' and (len(args)!=2 or not isinstance(ast.parse(args[1],mode='eval').body,(ast.Name,ast.Attribute,ast.Call))):raise ValueError('Expected exception expression')
        translated.append([op,key,*args])
    return base.decode(source,expected_hash,json.dumps(translated),finish)


def prompt(source):
    mapping=selectors(source);nodes=base.catalogue(source)
    calls='; '.join(name+(' {'+','.join(keyword_slots(nodes[key]))+'}' if keyword_slots(nodes[key]) else '') for name,key in mapping['C'].items())
    return ('Return one compact JSON array of edits; satisfy the whole task. Values are Python expressions encoded as JSON strings. '
        '["arg",call,value] prepends a positional argument (including option aliases). '
        '["kw",call,key,value] sets only a listed keyword. '
        '["guard_return",function,condition,value] inserts if/return at entry. '
        '["guard_raise",function,condition,exception] inserts if/raise at entry. '
        '["catch_return",statement,exceptionType,value] wraps the existing statement in try/except returning value. '
        'Runtime builds all code structure and preserves old code. No code blocks, whitespace or old source to generate. '
        'Target names are from source. Calls with a simple string first argument use that string as name. '
        'Functions: '+','.join(mapping['F'])+'\nCalls {allowed keyword slots}: '+calls+'\nStatements: '+','.join(mapping['S']))


EXCEPTIONS=('ValueError','OSError','Exception','RuntimeError','TypeError','KeyError','TimeoutError','LookupError')
NUMBER=r'-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?'
INTEGER=r'-?(0|[1-9][0-9]*)'
SCALAR='('+STRING+'|'+NUMBER+'|true|false|null)'


def value_kind(node,name):
    if ast.unparse(node.func)=='json.dumps' and name=='separators':return 'separators'
    found=next((k.value for k in node.keywords if k.arg==name),None)
    if isinstance(found,ast.Constant):value=found.value
    else:
        function=SIGNATURES.get(ast.unparse(node.func))
        param=inspect.signature(function).parameters.get(name) if function else None
        if param is None or param.default is inspect.Parameter.empty:return None
        value=param.default
    return {bool:'bool',int:'int',float:'number',str:'string',type(None):'null'}.get(type(value))


def typed_grammar(source):
    mapping=selectors(source);nodes=base.catalogue(source);choices=[]
    patterns={'bool':'(true|false)','int':INTEGER,'number':NUMBER,'string':STRING,'null':'null','separators':r'\['+STRING+','+STRING+r'\]'}
    exception='('+'|'.join(map(quoted,EXCEPTIONS))+')'
    for target,key in mapping['C'].items():
        choices.append(r'\["arg",'+quoted(target)+','+STRING+r'\]')
        for name in keyword_slots(nodes[key]):
            kind=value_kind(nodes[key],name)
            if kind:choices.append(r'\["kw",'+quoted(target)+','+quoted(name)+','+patterns[kind]+r'\]')
    for target in mapping['F']:
        choices.append(r'\["return_if",'+quoted(target)+','+STRING+','+STRING+r'\]')
        choices.append(r'\["raise_if",'+quoted(target)+','+STRING+','+exception+','+STRING+r'\]')
    for target in mapping['S']:
        choices.append(r'\["catch",'+quoted(target)+','+exception+','+SCALAR+r'\]')
    edit='('+'|'.join(choices)+')'
    return r'\['+edit+'(,'+edit+r'){0,7}\]'


def typed_decode(source,expected_hash,raw,finish):
    if base.digest(source)!=expected_hash:raise ValueError('Stale source version')
    if finish!='stop':raise ValueError('Incomplete output')
    # Revalidate grammar before translating types, even when not using constrained decoding.
    if not isinstance(raw,str) or re.fullmatch(typed_grammar(source),raw) is None:raise ValueError('Invalid typed operation')
    edits=json.loads(raw);translated=[]
    for op,target,*values in edits:
        if op=='arg':translated.append(['arg',target,repr(values[0])])
        elif op=='kw':
            name,value=values
            if isinstance(value,float) and not math.isfinite(value):raise ValueError('Nonfinite value')
            translated.append(['kw',target,name,repr(value)])
        elif op=='return_if':translated.append(['guard_return',target,*values])
        elif op=='raise_if':
            condition,exception,message=values
            translated.append(['guard_raise',target,condition,exception+'('+repr(message)+')'])
        else:
            exception,value=values
            if isinstance(value,float) and not math.isfinite(value):raise ValueError('Nonfinite value')
            translated.append(['catch_return',target,exception,repr(value)])
    return decode(source,expected_hash,json.dumps(translated),finish)


def typed_prompt(source):
    aliases=selectors(source)
    exceptional=[name for entries in aliases.values() for name in entries if '@' in name or re.fullmatch(r'[CFS][0-9]+_[0-9]+',name)]
    return ('Output one JSON array containing all required edits. Engine preserves source and builds indentation. '
        '["arg",call,string] adds a positional string argument, e.g. an option alias. '
        '["kw",call,key,value] changes a typed keyword value; use plain JSON values, not Python strings representing values. '
        '["return_if",function,condition_expr,result_expr] inserts if/return. '
        '["raise_if",function,condition_expr,exception_type,message] inserts if/raise BEFORE execution. '
        '["catch",statement,exception_type,value] wraps an EXISTING statement in try/except returning the JSON value. '
        'Only condition_expr and result_expr contain Python expression text. '
        'Function targets are their names. Call targets are their first simple string argument (e.g. --option), otherwise the callee name (e.g. module.func). '
        'Assignment targets are the assigned variable name. Other/disambiguated targets: '+','.join(exceptional))
