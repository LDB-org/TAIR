"""The independent AST oracle must represent signed values as parsed Python."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'safe_benchmark', Path(__file__).resolve().parents[1] / 'benchmarks/benchmark_safe_codebook.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_negative_default_oracle_accepts_correct_edit_and_rejects_wrong_sign():
    case = next(c for c in benchmark.expanded_cases() if c['name'] == 'negative_default')
    expected = benchmark.expected_ast(case['source'], case)
    assert benchmark.normalize(case['source'].replace('default=4', 'default=-2')) == expected
    assert benchmark.normalize(case['source'].replace('default=4', 'default=2')) != expected
