import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('engine_plan', Path(__file__).resolve().parents[1] / 'benchmarks/benchmark_engine_plan.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_executor_rejects_path_escape(tmp_path):
    plan = {'kind': 'write', 'arguments': {'files': [{'path': '../escape.txt', 'content': 'bad'}]}}
    with pytest.raises(ValueError, match='outside'):
        module.execute(plan, tmp_path)
    assert not (tmp_path.parent / 'escape.txt').exists()


def test_failed_step_stops_later_edits(tmp_path):
    file = tmp_path / 'app.py'
    file.write_text('x = 1\n')
    plan = {'kind': 'replace', 'arguments': {'edits': [
        {'path': 'app.py', 'old': 'absent', 'new': 'bad'},
        {'path': 'app.py', 'old': 'x = 1', 'new': 'x = 2'}]}}
    with pytest.raises(ValueError, match='exactly once'):
        module.execute(plan, tmp_path)
    assert file.read_text() == 'x = 1\n'


def test_oracle_rejects_original_function(tmp_path):
    case = next(c for c in module.cases() if c['name'] == 'function')
    (tmp_path / 'app.py').write_text(case['files']['app.py'])
    with pytest.raises(AssertionError):
        module.verify(case, {'kind': 'replace'}, tmp_path, None)
    (tmp_path / 'app.py').write_text('def total(values):\n    return sum(values)\n')
    module.verify(case, {'kind': 'replace'}, tmp_path, None)
