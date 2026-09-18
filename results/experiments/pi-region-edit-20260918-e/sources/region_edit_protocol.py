"""Version-bound source regions: finite selection followed by raw replacement."""
import ast
import hashlib
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
