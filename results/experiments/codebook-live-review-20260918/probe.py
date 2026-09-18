import ast
import importlib.util
import json
import os
from pathlib import Path
import random
import shlex
import sys

ROOT = Path(__file__).resolve().parent
os.environ['PIJIT_URL'] = 'http://127.0.0.1:8000'
for key in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_TOKENIZER_REVISION'):
    os.environ.pop(key, None)
spec = importlib.util.spec_from_file_location('bridge', ROOT / 'integrations/pijit/bridge.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
SOURCE = "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n    p.add_argument('--workers', type=int, default=4)\n    return p\n"
CASES = [
    ('cold', 'Change --workers default to 6.', SOURCE, 6, False),
    ('repeat', 'Change --workers default to 6.', SOURCE, 6, False),
    ('new_value', 'Change --workers default to 8.', SOURCE, 8, False),
    ('paraphrase', 'Set the default value for --workers to 10.', SOURCE, 10, False),
    ('source_change', 'Change --workers default to 12.', SOURCE + '# unrelated comment\n', 12, False),
    ('alias_cold', 'Add alias -w to --workers.', SOURCE, 4, True),
    ('alias_repeat', 'Add alias -w to --workers.', SOURCE, 4, True),
]
OUT = ROOT / 'evidence'
OUT.mkdir(exist_ok=False)
(OUT / 'manifest.json').write_text(json.dumps({'commit': '4772970c061837e78a8af23da946c0ecfb4c3d26', 'cases': CASES, 'repeats': 2, 'seed': 918, 'arms': ['generate', 'codebook'], 'scope': 'edit only; existing default dynamic codebook; fresh state per repeat and arm; restore declared source before every task; retain codebook across tasks; no label cache; shared live backend; full bridge wall time including oracle; no retries'}, indent=2))
rng = random.Random(918)
with (OUT / 'rows.jsonl').open('x') as stream:
    for repeat in range(2):
        for name, task, source, value, alias in CASES:
            arms = ['generate', 'codebook']
            rng.shuffle(arms)
            for arm in arms:
                root = OUT / f'{repeat}-{arm}'
                project = root / 'project'
                project.mkdir(parents=True, exist_ok=True)
                app = project / 'app.py'
                app.write_text(source)
                b.STATE = root / 'state'
                oracle = root / 'oracle.py'
                extra = 'assert p.parse_args(["-w", "9"]).workers == 9\n' if alias else ''
                oracle.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()))\nfrom app import build_parser\np=build_parser()\n' + f'assert p.parse_args([]).workers == {value}\n' + 'assert p.parse_args(["--workers", "7"]).workers == 7\nassert len(p._actions) == 2\n' + extra)
                os.environ['PIJIT_DISABLE_CODEBOOK'] = str(int(arm == 'generate'))
                os.environ['PIJIT_VERIFY_CMD'] = shlex.join([sys.executable, '-B', str(oracle)])
                result = b.run({'action': 'edit', 'cwd': str(project), 'path': 'app.py', 'task': task})
                row = {'repeat': repeat, 'case': name, 'arm': arm, 'correct': result['status'] == 'ok', 'result': result, 'after': app.read_text()}
                stream.write(json.dumps(row) + '\n')
                stream.flush()
                book = b.paths(project) / 'codebook.json'
                if book.exists():
                    (OUT / f'{repeat}-{name}-{arm}-book.json').write_bytes(book.read_bytes())
                print(json.dumps({'repeat': repeat, 'case': name, 'arm': arm, 'correct': row['correct'], 'seconds': round(result['wall_seconds'], 3), 'hit': result.get('cache_hit'), 'admitted': result.get('admitted'), 'tokens': result['accounting']['known_generated_argument_tokens'], 'error': result.get('error')}), flush=True)
