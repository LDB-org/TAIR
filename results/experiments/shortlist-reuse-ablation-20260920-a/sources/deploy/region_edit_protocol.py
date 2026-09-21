"""Version-bound source regions: finite selection followed by raw replacement."""
import ast
import hashlib
import io
import json
import re
import textwrap
import tokenize


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def catalogue(source, readable=False):
    lines = source.splitlines(keepends=True)
    spans = {(i, i) for i, line in enumerate(lines, 1) if line.strip()}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.stmt) and hasattr(node, 'end_lineno'):
            spans.add((node.lineno, node.end_lineno))
    return {(('L'+str(a) if a==b else f'B{a}_{b}') if readable else f'R{i}'): {'start': a, 'end': b, 'text': ''.join(lines[a-1:b])}
            for i, (a, b) in enumerate(sorted(spans))}


def decode(source, expected_hash, regions, raw, finish, relative_indent=False):
    if digest(source) != expected_hash:
        raise ValueError('Stale source version')
    if finish != 'stop':
        raise ValueError('Incomplete output')
    key, separator, replacement = raw.partition('\n')
    if not separator or key not in regions:
        raise ValueError('Unknown region')
    region = regions[key]
    lines = source.splitlines(keepends=True)
    if ''.join(lines[region['start']-1:region['end']]) != region['text']:
        raise ValueError('Region mismatch')
    # Newline is deterministic framing, not model content or heuristic JSON repair.
    replacement = replacement.rstrip('\n') + '\n' if replacement else ''
    if relative_indent and replacement:
        if replacement[0].isspace():
            raise ValueError('Replacement must start at relative column zero')
        indent = re.match(r'[ \t]*', region['text']).group()
        replacement = textwrap.indent(replacement, indent)
    return ''.join(lines[:region['start']-1]) + replacement + ''.join(lines[region['end']:])


def regex(regions, relative_indent=False):
    return '(' + '|'.join(re.escape(k) for k in regions) + (r')\n(\S[\s\S]*)?' if relative_indent else r')\n[\s\S]*')


def multi_regex(regions, allow_single=True):
    """One raw edit or a bounded list of [region ID, replacement] values."""
    # Nonempty replacements must begin at relative column zero, including in JSON.
    string = r'(""|"([^\s"\\\x00-\x1f]|\\["\\/])([^"\\\x00-\x1f]|\\(["\\/bfnrt]|u[0-9a-fA-F]{4}))*")'
    choice = '(' + '|'.join(re.escape(k) for k in regions) + ')'
    pair = r'\["' + choice + '",' + string + r'\]'
    batch = r'\[' + pair + '(,' + pair + r'){0,7}\]'
    return '(' + regex(regions, relative_indent=True) + '|' + batch + ')' if allow_single else batch


def decode_multi(source, expected_hash, regions, raw, finish):
    """Validate the whole batch against one snapshot before returning any edit."""
    if digest(source) != expected_hash:
        raise ValueError('Stale source version')
    if finish != 'stop':
        raise ValueError('Incomplete output')
    if not raw.startswith('['):
        result = decode(source, expected_hash, regions, raw, finish, relative_indent=True)
        ast.parse(result)
        return result
    edits = json.loads(raw)
    if not isinstance(edits, list) or not 1 <= len(edits) <= 8:
        raise ValueError('Need 1..8 edits')
    lines = source.splitlines(keepends=True)
    patches = []
    for edit in edits:
        if not isinstance(edit, list) or len(edit) != 2 or not all(isinstance(v, str) for v in edit):
            raise ValueError('Expected [region ID, replacement]')
        key, replacement = edit
        if key not in regions:
            raise ValueError('Unknown region')
        r = regions[key]
        # Reuse single-edit checks and indentation semantics against the original snapshot.
        one = decode(source, expected_hash, regions, key+'\n'+replacement, finish, relative_indent=True)
        before = ''.join(lines[:r['start']-1])
        after = ''.join(lines[r['end']:])
        value = one[len(before):len(one)-len(after) if after else len(one)]
        value.encode('utf-8')
        patches.append((r['start'], r['end'], value))
    patches.sort()
    for previous, current in zip(patches, patches[1:]):
        if current[0] <= previous[1]:
            raise ValueError('Duplicate or overlapping regions')
    for start, end, value in reversed(patches):
        lines[start-1:end] = [value]
    result = ''.join(lines)
    ast.parse(result)
    return result


def statement_catalogue(source):
    """Only whole statements, never a compound header or continuation line."""
    spans = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.stmt):
            start = min([node.lineno] + [d.lineno for d in getattr(node, 'decorator_list', [])])
            spans.add((start, node.end_lineno))
    lines = source.splitlines(keepends=True)
    return {(f'L{start}' if start == end else f'B{start}_{end}'):
            {'start': start, 'end': end, 'text': ''.join(lines[start-1:end])}
            for start, end in sorted(spans)}


def indentation_unit(source):
    """Infer a uniform suite indentation unit; reject ambiguous mixed styles."""
    stack = ['']; units = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.INDENT:
            if not token.string.startswith(stack[-1]):
                raise ValueError('Inconsistent source indentation')
            units.add(token.string[len(stack[-1]):]); stack.append(token.string)
        elif token.type == tokenize.DEDENT:
            stack.pop()
    if not units:
        return '    '
    if len(units) != 1:
        raise ValueError('Mixed source indentation units')
    unit = units.pop()
    if not unit or not (set(unit) == {' '} or unit == '\t'):
        raise ValueError('Unsupported source indentation unit')
    return unit


def line_regex(regions):
    """Finite regions, integer indentation levels, bounded single-line values."""
    # Disallow escaped physical newlines/tabs, including Unicode aliases. Literal
    # backslash-n inside Python strings is encoded as \\n and remains available.
    string = r'(""|"([^\s"\\\x00-\x1f]|\\["\\/])([^"\\\x00-\x1f]|\\["\\/])*")'
    line = r'\[([0-9]|1[0-6]),' + string + r'\]'
    body = r'\[(' + line + '(,' + line + r'){0,255})?\]'
    edit = r'\["(' + '|'.join(re.escape(k) for k in regions) + ')",' + body + r'\]'
    return r'\[' + edit + '(,' + edit + r'){0,7}\]'


def decode_lines(source, expected_hash, regions, raw, finish):
    """Render explicit relative indentation without dedenting or guessing code."""
    if digest(source) != expected_hash:
        raise ValueError('Stale source version')
    if finish != 'stop':
        raise ValueError('Incomplete output')
    safe = statement_catalogue(source)
    if regions != safe:
        raise ValueError('Statement catalogue mismatch')
    edits = json.loads(raw)
    if not isinstance(edits, list) or not 1 <= len(edits) <= 8:
        raise ValueError('Need 1..8 edits')
    unit = indentation_unit(source); patches = []
    source_lines = source.splitlines(keepends=True)
    for edit in edits:
        if not isinstance(edit, list) or len(edit) != 2:
            raise ValueError('Expected [region ID, lines]')
        key, body = edit
        if not isinstance(key, str) or key not in safe:
            raise ValueError('Unknown statement region')
        if not isinstance(body, list) or len(body) > 256:
            raise ValueError('Need 0..256 lines')
        rendered = []
        for row in body:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError('Expected [depth, line]')
            depth, value = row
            if type(depth) is not int or not 0 <= depth <= 16 or not isinstance(value, str):
                raise ValueError('Invalid line depth or value')
            if any(ord(c) < 32 or c in '\x7f\u2028\u2029' for c in value) or (value and value[0].isspace()):
                raise ValueError('Line must have no leading whitespace or physical controls')
            if not rendered and depth != 0:
                raise ValueError('First line depth must be zero')
            rendered.append(unit * depth + value if value else '')
        replacement = '\n'.join(rendered) + ('\n' if rendered else '')
        # Indenting a physical multiline string would change its value. Require
        # escaped string newlines instead; never silently rewrite literal data.
        for token in tokenize.generate_tokens(io.StringIO(replacement).readline):
            if token.type == tokenize.STRING and token.start[0] != token.end[0]:
                raise ValueError('Use escaped newlines in string literals')
        r = safe[key]
        base = re.match(r'[ \t]*', r['text']).group()
        value = textwrap.indent(replacement, base)
        value.encode('utf-8')
        patches.append((r['start'], r['end'], value))
    patches.sort()
    if any(right[0] <= left[1] for left, right in zip(patches, patches[1:])):
        raise ValueError('Duplicate or overlapping regions')
    for start, end, value in reversed(patches):
        source_lines[start-1:end] = [value]
    result = ''.join(source_lines)
    ast.parse(result)
    return result
