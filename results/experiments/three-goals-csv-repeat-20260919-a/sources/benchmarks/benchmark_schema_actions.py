"""Small matched edit benchmark; state/cache outside evidence directory."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge', ROOT / 'integrations/pijit/bridge.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
SOURCE = 'import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n    p.add_argument("--workers", type=int, default=4)\n    return p\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = [('english', 'Change --workers default to 6.', 6),
             ('chinese', '将 --workers 的默认值改为 8。', 8),
             ('fallback', 'Update the default value for --workers to 7.', 7)]
    with args.output.open('x') as out, tempfile.TemporaryDirectory(prefix='tair-schema-') as tmp:
        b.STATE = Path(tmp) / 'state'
        for repeat in range(3):
            for name, task, expected in cases:
                arms = ['generate', 'schema'] if repeat % 2 == 0 else ['schema', 'generate']
                for arm in arms:
                    cwd = Path(tmp) / f'{repeat}-{name}-{arm}'
                    cwd.mkdir()
                    (cwd / 'app.py').write_text(SOURCE)
                    os.environ['PIJIT_SCHEMA_ACTIONS'] = str(int(arm == 'schema'))
                    os.environ['PIJIT_DISABLE_CODEBOOK'] = '1'
                    result = b.run({'action': 'edit', 'cwd': str(cwd), 'path': 'app.py', 'task': task})
                    actual = (cwd / 'app.py').read_text()
                    row = {'repeat': repeat, 'case': name, 'arm': arm, 'task': task,
                           'correct': actual == SOURCE.replace('default=4', f'default={expected}'),
                           'result': result}
                    out.write(json.dumps(row, ensure_ascii=False) + '\n')
                    out.flush()
                    print(name, arm, result['status'], row['correct'], round(result['wall_seconds'], 3), flush=True)


if __name__ == '__main__':
    main()
