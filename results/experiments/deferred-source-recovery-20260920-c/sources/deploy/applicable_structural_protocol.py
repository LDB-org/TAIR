"""Conservative, generation-time applicability constraints for structural edits."""
import ast
import importlib.util
from pathlib import Path
import re

spec=importlib.util.spec_from_file_location('compact',Path(__file__).with_name('compact_structural_protocol.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def entry_expressions(node):
    """Bounded expression language: parameters, scalar literals and small containers."""
    args=node.args
    names=[a.arg for a in args.posonlyargs+args.args+args.kwonlyargs]
    names += [a.arg for a in (args.vararg,args.kwarg) if a is not None]
    if not names:return None
    name='('+'|'.join(map(re.escape,names))+')'
    literal='('+m.NUMBER+r"|'[^'\"\\\x00-\x1f]*'|True|False|None)"
    comparator=r' *(==|!=|<=|>=|<|>| is not | is ) *'
    comparison='('+name+comparator+literal+'|'+literal+comparator+name+'('+comparator+literal+')?)'
    atom='(not )?('+comparison+'|'+name+')'
    condition='"'+atom+'(( and | or )'+atom+'){0,3}"'
    scalar='('+name+'|'+literal+')'
    empty=r'(\[\]|\{\}|\(\))'
    element='('+scalar+'|'+empty+')'
    sequence=r'(\['+element+'(, *'+element+r'){0,3}\]|\('+element+'(, *'+element+r'){1,3}\))'
    result='"('+scalar+'|'+empty+'|'+sequence+')"'
    return condition,result


def guards_supported(source,node):
    try:
        # Checks insertion anchor and source indentation without executing code.
        key=next(k for k,n in m.base.catalogue(source).items() if k.startswith('F') and n.lineno==node.lineno and n.col_offset==node.col_offset)
        m.base.patch(source,{key:node},['guard_return',key,'True','None'])
        return entry_expressions(node) is not None
    except (ValueError,SyntaxError):return False


def catch_supported(source,key,node):
    functions=[n for k,n in m.base.catalogue(source).items() if k.startswith('F')]
    if not any((f.lineno,f.col_offset)<(node.lineno,node.col_offset) and (node.end_lineno,node.end_col_offset)<=(f.end_lineno,f.end_col_offset) for f in functions):return False
    try:
        m.base.patch(source,{key:node},['catch_return',key,'Exception','None'])
        return True
    except (ValueError,SyntaxError,m.base.tokenize.TokenError):return False


def grammar(source,allowed=None):
    mapping=m.scoped_selectors(source,allowed);nodes=m.base.catalogue(source);choices=[]
    patterns={'bool':'(true|false)','int':m.INTEGER,'number':m.NUMBER,'string':m.STRING,'null':'null',
              'separators':r'\[", ?",": ?"\]'}
    exception='('+'|'.join(map(m.quoted,m.EXCEPTIONS))+')'
    for target,key in mapping['C'].items():
        node=nodes[key]
        # Unknown APIs only expose string insertion when their existing first arg is a string.
        if node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
            choices.append(r'\["arg",'+m.quoted(target)+','+m.STRING+r'\]')
        for name in m.keyword_slots(node):
            kind=m.value_kind(node,name)
            if kind:choices.append(r'\["kw",'+m.quoted(target)+','+m.quoted(name)+','+patterns[kind]+r'\]')
    for target,key in mapping['F'].items():
        node=nodes[key]
        if not guards_supported(source,node):continue
        condition,result=entry_expressions(node)
        choices.append(r'\["return_if",'+m.quoted(target)+','+condition+','+result+r'\]')
        choices.append(r'\["raise_if",'+m.quoted(target)+','+condition+','+exception+','+m.STRING+r'\]')
    for target,key in mapping['S'].items():
        if catch_supported(source,key,nodes[key]):
            choices.append(r'\["catch",'+m.quoted(target)+','+exception+','+m.SCALAR+r'\]')
    # A no-op route marker is available even when no structural operation applies.
    edit='('+'|'.join(choices)+')' if choices else None
    batch=r'\['+edit+'(,'+edit+r'){0,7}\]' if edit else None
    return '('+batch+r'|\["native"\])' if batch else r'\["native"\]'


def decode(source,expected_hash,raw,finish,allowed=None):
    if m.base.digest(source)!=expected_hash:raise ValueError('Stale source version')
    if finish!='stop':raise ValueError('Incomplete output')
    if re.fullmatch(grammar(source,allowed),raw) is None:raise ValueError('Inapplicable operation or expression')
    if raw=='["native"]':raise ValueError('Native route requested')
    return m.typed_decode(source,expected_hash,raw,finish,allowed)


def prompt(source,allowed=None):
    return m.typed_prompt(source,allowed)+('\nEntry conditions may reference ONLY function parameters, using truth tests, scalar comparisons, and/or. '
        'Entry results allow only parameters, literals and small containers; no calls, attributes, arithmetic or later local variables. '
        'JSON separators must preserve comma/colon syntax. For unsupported edits output ["native"]. This routes to a separate native request; its cost is counted.')
