"""Version-bound source regions: finite selection followed by raw replacement."""
import ast
import hashlib
import json
import re
import textwrap


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
