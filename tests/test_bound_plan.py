import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
spec = importlib.util.spec_from_file_location('bound_plan', ROOT / 'benchmarks/benchmark_bound_plan.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_binding_preserves_literal_contents_and_does_not_choose_task():
    source = {'a': '中文\n"quoted"\\\n', 'b': 'another\n'}
    plans, descriptions = module.bind(source, {'a': 'out/a', 'b': 'out/b'})
    assert len(plans) == 4
    assert plans[0]['files'][0]['content'] == source['a']
    assert plans[2]['files'] == plans[0]['files'] + plans[1]['files']
    assert plans[-1] is None and descriptions[-1] is None
    assert descriptions[0] == {'copy': [{'source': 'a', 'destination': 'out/a'}]}


def test_binding_rejects_unobserved_source():
    with pytest.raises(ValueError, match='Missing observed'):
        module.bind({}, {'missing': 'out/a'})


def test_binding_rejects_conflicting_destinations():
    with pytest.raises(ValueError, match='Duplicate destination'):
        module.bind({'a': 'one', 'b': 'two'}, {'a': 'out', 'b': 'out'})
