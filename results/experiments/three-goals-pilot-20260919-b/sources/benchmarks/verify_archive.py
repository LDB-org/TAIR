"""Verify imported experiment bytes and every original checksum manifest."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    imported = json.loads((ROOT/'docs/MIGRATION_MANIFEST.json').read_text())
    count = 0
    for entry in imported['files']:
        if not entry['path'].startswith('results/experiments/'):
            continue
        path = ROOT/entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], str(path)
        count += 1
    checked = 0
    for manifest in (ROOT/'results/experiments').rglob('SHA256SUMS*'):
        for line in manifest.read_text().splitlines():
            if not line.strip():
                continue
            digest, relative = line.split(maxsplit=1)
            relative = relative.lstrip('*')
            base = ROOT if relative.startswith(('benchmarks/', 'results/')) else manifest.parent
            path = (base/relative).resolve()
            assert path.is_relative_to(ROOT), relative
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, str(path)
            checked += 1
    return {'imported_experiment_files': count, 'original_checksum_entries': checked, 'status': 'ok'}


if __name__ == '__main__':
    print(json.dumps(verify()))
