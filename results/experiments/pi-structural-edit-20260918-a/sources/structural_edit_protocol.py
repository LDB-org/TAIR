"""Finite edit operations with expression values and source-preserving splices."""
import ast
import hashlib
import io
import json
import re
import tokenize


def digest(source):
    return hashlib.sha256(source.encode()).hexdigest()


def catalogue(source):
    tree = ast.parse(source)
    result = {}
    for node in ast.walk(tree):
        kind = 'C' if isinstance(node, ast.Call) else 'F' if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else 'S' if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return, ast.Raise)) else None
        if kind:
            result[f'{kind}{node.lineno}_{node.col_offset}'] = node
    return result


def grammar(source):
    nodes = catalogue(source)
    string = r'"([^"\\\x00-\x1f]|\\(["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
    def target(kind):
        keys = [re.escape(k) for k in nodes if k.startswith(kind)]
        return '"('+'|'.join(keys)+')"' if keys else None
    signatures = [('arg','C',1),('kw','C',2),('guard_return','F',2),('guard_raise','F',2),('catch_return','S',2)]
    choices = [r'\["'+op+'",'+target(kind)+(','+string)*n+r'\]' for op,kind,n in signatures if target(kind)]
    edit = '('+'|'.join(choices)+')'
    return r'\['+edit+'(,'+edit+r'){0,7}\]'


def expression(value):
    if not isinstance(value, str):
        raise ValueError('Expression must be a string')
    return ast.unparse(ast.parse(value, mode='eval').body)


def offset(source, line, column):
    lines = source.splitlines(keepends=True)
    return sum(map(len,lines[:line-1])) + len(lines[line-1].encode()[:column].decode())


def span(source, node):
    return offset(source,node.lineno,node.col_offset), offset(source,node.end_lineno,node.end_col_offset)


def unit(source):
    stack = ['']; units = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.INDENT:
            if not token.string.startswith(stack[-1]):raise ValueError('Mixed indentation')
            units.add(token.string[len(stack[-1]):]);stack.append(token.string)
        elif token.type == tokenize.DEDENT:stack.pop()
    if len(units)>1:raise ValueError('Mixed indentation units')
    value=next(iter(units),'    ')
    if not (set(value)=={' '} or value=='\t'):raise ValueError('Unsupported indentation')
    return value


def statement_lines(source,node):
    lines=source.splitlines(keepends=True)
    base=lines[node.lineno-1][:node.col_offset]
    tail=lines[node.end_lineno-1].encode()[node.end_col_offset:].decode().strip()
    if base.strip() or (tail and not tail.startswith('#')):
        raise ValueError('Need an isolated whole statement')
    start=sum(map(len,lines[:node.lineno-1]));end=sum(map(len,lines[:node.end_lineno]))
    return start,end,base


def patch(source,nodes,edit):
    if not isinstance(edit,list) or len(edit) not in (3,4) or not all(isinstance(v,str) for v in edit):raise ValueError('Invalid edit')
    op,key,*values=edit
    if key not in nodes:raise ValueError('Unknown target')
    node=nodes[key]
    if op in ('arg','kw') and isinstance(node,ast.Call):
        start,end=span(source,node)
        if op=='kw':
            if len(values)!=2 or not values[0].isidentifier():raise ValueError('Invalid keyword')
            name,value=values[0],expression(values[1])
            found=next((k for k in node.keywords if k.arg==name),None)
            if found:
                a,b=span(source,found.value);return a,b,value
            additions=name+'='+value
            # Insert before the first **mapping, so explicit keywords remain legal.
            unpack=next((k for k in node.keywords if k.arg is None),None)
            if unpack:
                a,_=span(source,unpack);return a,a,additions+', '
            tokens=[t for t in tokenize.generate_tokens(io.StringIO(source[start:end]).readline)
                    if t.type not in (tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE,tokenize.ENDMARKER)]
            comma = bool(node.args or node.keywords) and tokens[-2].string != ','
            return end-1,end-1,(', ' if comma else '')+additions
        if len(values)!=1:raise ValueError('Invalid positional argument')
        value=expression(values[0])
        if node.args or node.keywords:
            first=(node.args+node.keywords)[0];a,_=span(source,first)
            return a,a,value+', '
        # Empty calls may contain comments; adding immediately after '(' preserves them.
        func_end=span(source,node.func)[1];a=source.index('(',func_end,end)+1
        return a,a,value
    if op in ('guard_return','guard_raise') and isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and len(values)==2:
        condition,value=map(expression,values)
        body=node.body
        first=body[0]
        if isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant) and isinstance(first.value.value,str):
            if len(body)<2:raise ValueError('No insertion anchor after docstring')
            first=body[1]
        start,_,base=statement_lines(source,first)
        action='return ' if op=='guard_return' else 'raise '
        return start,start,base+'if '+condition+':\n'+base+unit(source)+action+value+'\n'
    if op=='catch_return' and key.startswith('S') and len(values)==2:
        exception,value=map(expression,values)
        start,end,base=statement_lines(source,node)
        original=source[start:end]
        # Indenting physical multiline strings changes data, not just formatting.
        for token in tokenize.generate_tokens(io.StringIO(original).readline):
            if token.type==tokenize.STRING and token.start[0]!=token.end[0]:raise ValueError('Cannot move multiline literal')
        nested=''.join(unit(source)+line if line.strip() else line for line in original.splitlines(keepends=True))
        if not nested.endswith('\n'):nested+='\n'
        return start,end,base+'try:\n'+nested+base+'except '+exception+':\n'+base+unit(source)+'return '+value+'\n'
    raise ValueError('Operation does not match target')


def decode(source,expected_hash,raw,finish):
    if digest(source)!=expected_hash:raise ValueError('Stale source version')
    if finish!='stop':raise ValueError('Incomplete output')
    edits=json.loads(raw)
    if not isinstance(edits,list) or not 1<=len(edits)<=8:raise ValueError('Need 1..8 edits')
    nodes=catalogue(source);patches=sorted(patch(source,nodes,e) for e in edits)
    for left,right in zip(patches,patches[1:]):
        if right[0]<left[1] or right[0]==left[0]:raise ValueError('Overlapping edits')
    for start,end,value in reversed(patches):source=source[:start]+value+source[end:]
    compile(source,'<structural-edit>','exec')
    return source


def prompt(source):
    return ('Return only a compact JSON array of 1..8 operations. Choose operations and targets yourself; generate Python EXPRESSIONS only for values. Runtime preserves source and builds indentation/control flow. '
        'Operations: ["arg",callID,expression] prepends a positional argument; ["kw",callID,keywordName,expression] adds/replaces a keyword; '
        '["guard_return",functionID,conditionExpression,returnExpression] inserts an early if/return after the function docstring; '
        '["guard_raise",functionID,conditionExpression,exceptionExpression] inserts an early if/raise; '
        '["catch_return",statementID,exceptionTypeExpression,returnExpression] wraps exactly that existing statement in try/except returning the value. '
        'Do not generate old code, statements, indentation or function bodies. JSON string values containing Python string literals must include Python quotes. Make ALL changes requested. '
        'Example unrelated to this file: [["kw","C8_4","enabled","True"]]. IDs encode original line and UTF-8 column. C=call, F=function, S=statement. '
        'Available targets: '+', '.join(catalogue(source))+'\nSOURCE HASH: '+digest(source))
