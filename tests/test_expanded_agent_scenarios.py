import json
from pathlib import Path
import subprocess
import sys


def test_expanded_oracles_reject_originals_and_accept_reference_implementations():
    root = Path(__file__).parents[1]
    result = subprocess.run([sys.executable, '-B', str(root/'benchmarks/verify_expanded_scenarios.py')],
                            cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(result.stdout)
    assert len(rows) == 7
    assert all(r['baseline_rejected'] and r['reference_passed'] for r in rows)
