import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
spec = importlib.util.spec_from_file_location('bound_edits', ROOT / 'benchmarks/benchmark_bound_edits.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_binder_ignores_nonliteral_and_nested_values():
    source = 'workers = get_workers()\ntimeout = True\ndef inner():\n    workers = 2\n'
    assert module.bind({'app.py': source}) == [None]


def test_batch_binding_changes_requested_fields_only(tmp_path):
    case = next(c for c in module.cases() if c['name'] == 'eight_edits')
    for name, content in case['sources'].items():
        (tmp_path / name).write_text(content)
    plan = next(p for p in module.bind(case['sources']) if p and len(p['edits']) == 8)
    module.execute({'kind': 'replace', 'arguments': plan}, tmp_path)
    module.verify(case, tmp_path)
    path = tmp_path / 'service_0.py'
    path.write_text(path.read_text().replace('preserve-0', 'wrong'))
    with pytest.raises(AssertionError):
        module.verify(case, tmp_path)


def test_new_value_is_not_in_catalog():
    case = next(c for c in module.cases() if c['name'] == 'new_value')
    plans = module.bind(case['sources'])
    assert all('workers = 7' != e['new'] for p in plans if p for e in p['edits'])
