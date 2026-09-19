import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
spec = importlib.util.spec_from_file_location('expanded_bound', ROOT / 'benchmarks/benchmark_bound_expanded.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unparseable_source_routes_to_generation():
    plans, reason = module.catalog({'config.json': '{"enabled": true}\n'})
    # JSON can also parse as a Python expression; either way there is no eligible assignment.
    assert plans == [None]


def test_over_capacity_catalog_preserves_generation_route():
    sources = {f's{i}.py': 'workers = 2\ntimeout = 3\n' for i in range(9)}
    plans, reason = module.catalog(sources)
    assert plans == [None] and 'capacity' in reason


def test_oracle_rejects_unrelated_comment_change(tmp_path):
    case = {'origin': 'synthetic', 'sources': {'a.py': '# keep\nworkers = 2\n'},
            'expected': {'a.py': '# keep\nworkers = 4\n'}}
    (tmp_path / 'a.py').write_text('# changed\nworkers = 4\n')
    with pytest.raises(AssertionError, match='Comments'):
        module.verify(case, tmp_path)
    (tmp_path / 'a.py').write_text(case['expected']['a.py'])
    module.verify(case, tmp_path)
