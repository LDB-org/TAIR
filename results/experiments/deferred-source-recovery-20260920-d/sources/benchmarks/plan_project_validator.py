"""Independent expected behaviors for pinned-project adapter experiments."""
import argparse
import ast
import hashlib
import importlib.util
from pathlib import Path
import sys


def verify(project, variant, candidate, workspace):
    sys.path.insert(0, str(workspace))
    spec = importlib.util.spec_from_file_location('candidate_adapter', candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if project == 'rich':
        pairs = [('[bold]snow 雪[/bold]', 'snow 雪'), ('plain', 'plain'), ('[red]a[/red] [blue]b[/blue]', 'a b'), ('', '')]
        for value, stripped in pairs:
            assert module.render_plain(value) == (value if variant else stripped)
    elif project == 'cpython':
        for paths, expected in [([], []), (['b/A.txt', 'a/b.py', 'c/A.txt'], ['A.txt', 'b.py']), (['x/雪', '/'], ['', '雪'])]:
            original = list(paths)
            if variant:
                expected = [Path(p).name for p in paths]
            assert module.leaf_names(paths) == expected
            assert paths == original
    elif project == 'tair':
        for source in ['x=1\n', 'x = 1\n', 'def f():\n    return 2\n']:
            value = source if variant else ast.dump(ast.parse(source, type_comments=True), include_attributes=False)
            assert module.fingerprint(source) == hashlib.sha256(value.encode()).hexdigest()
        if not variant:
            assert module.fingerprint('def (') is None
    else:
        raise ValueError(project)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('project'); p.add_argument('variant', type=int)
    p.add_argument('candidate', type=Path); p.add_argument('contract'); p.add_argument('workspace', type=Path)
    a = p.parse_args()
    verify(a.project, a.variant, a.candidate, a.workspace)
    print('Independent project behavior checks passed')
