"""Matched cold/warm edit calls, separating schema, generated JIT and overhead."""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge', ROOT / 'integrations/pijit/bridge.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
SOURCE = "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n    p.add_argument('--timeout', type=float, default=1.5, help='old')\n    return p\n"
CASES = [
    ('float', 'Change --timeout default to 2.5.', SOURCE.replace('default=1.5', 'default=2.5'),
     'assert p.parse_args([]).timeout==2.5\nassert p.parse_args(["--timeout","0.25"]).timeout==0.25\n'),
    ('help', 'Change --timeout help to "Wait time".', SOURCE.replace("help='old'", "help='Wait time'"),
     'assert "Wait time" in p.format_help()\nassert p.parse_args([]).timeout==1.5\n'),
    ('alias', 'Add alias -t to --timeout.', SOURCE.replace("'--timeout'", "'-t', '--timeout'"),
     'assert p.parse_args(["-t","0.5"]).timeout==0.5\nassert p.parse_args(["--timeout","0.25"]).timeout==0.25\nassert p.parse_args([]).timeout==1.5\n'),
]


def main(args):
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    (out / 'sources').mkdir()
    for src in ['benchmarks/benchmark_schema_jit_edits.py', 'integrations/pijit/bridge.py',
                'deploy/schema_actions.py', 'deploy/preset_edits.py', 'deploy/jit_codebook.py']:
        shutil.copyfile(ROOT / src, out / 'sources' / Path(src).name)
    (out / 'manifest.json').write_text(json.dumps({'repeats': 3, 'rounds': 2, 'cases': CASES,
        'arms': ['generate', 'schema_only', 'schema_jit'],
        'timing': 'bridge.run wall includes HTTP preparation, inference, backup/apply and identical configured AST+behavior oracle, excludes fixture restore and final metrics append.',
        'pairing': 'Restore same original source at same path for second round; retain learned book and label cache. No preseeded action. Arm order reversed in round two and rotated across repeats.',
        'tokenizer_revision': os.environ.get('PIJIT_TOKENIZER_REVISION')}, indent=2))
    with tempfile.TemporaryDirectory(prefix='tair-jit-edits-') as tmp, (out / 'rows.jsonl').open('x') as stream:
        for repeat in range(3):
            for name, task, expected, check in CASES:
                for round_ in (1, 2):
                    arms = ['generate', 'schema_only', 'schema_jit']
                    arms = arms[repeat:] + arms[:repeat]
                    if round_ == 2: arms.reverse()
                    for arm in arms:
                        root = Path(tmp) / f'{repeat}-{name}-{arm}'
                        project = root / 'project'; project.mkdir(parents=True, exist_ok=True)
                        b.STATE = root / 'state'
                        (project / 'app.py').write_text(SOURCE)
                        oracle = root / 'oracle.py'
                        oracle.write_text('import ast,sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()))\nfrom app import build_parser\np=build_parser()\n' + check +
                            f'assert ast.dump(ast.parse(Path("app.py").read_text()))=={ast.dump(ast.parse(expected))!r}\n')
                        os.environ.update(PIJIT_SCHEMA_ACTIONS=str(int(arm != 'generate')),
                            PIJIT_JIT_ACTIONS=str(int(arm == 'schema_jit')),
                            PIJIT_DISABLE_CODEBOOK=str(int(arm != 'schema_jit')),
                            PIJIT_VERIFY_CMD=shlex.join([sys.executable, '-B', str(oracle)]))
                        result = b.run({'action': 'edit', 'cwd': str(project), 'path': 'app.py', 'task': task})
                        correct = result['status'] == 'ok' and ast.dump(ast.parse((project / 'app.py').read_text())) == ast.dump(ast.parse(expected))
                        row = {'repeat': repeat, 'round': round_, 'case': name, 'arm': arm, 'correct': correct, 'result': result}
                        stream.write(json.dumps(row) + '\n'); stream.flush()
                        print(name, arm, round_, correct, round(result['wall_seconds'], 4), result.get('jit_hit'), flush=True)
                        book = b.paths(project) / 'jit-actions.json'
                        if book.exists(): shutil.copyfile(book, out / f'{repeat}-{name}-{arm}-round{round_}-book.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args())
