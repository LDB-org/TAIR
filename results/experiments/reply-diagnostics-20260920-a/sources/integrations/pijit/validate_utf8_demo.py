"""Trusted fixed-task demo validator, NOT a validator for arbitrary Python tasks.

Task: read_text(path), write_text(path,text,*,append=False), UTF-8, overwrite or
append, str/Path, missing reads raise, no automatic parent directory creation.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks'))
from benchmark_adaptive_plan import check_module

if __name__ == '__main__':
    candidate, contract, workspace = sys.argv[1:]
    check_module(Path(candidate), 'utf8')
    print('Fixed UTF-8 demo behavior checks passed; not a general task validator.')
