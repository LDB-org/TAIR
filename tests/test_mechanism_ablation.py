import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
spec = importlib.util.spec_from_file_location('mechanism_ablation', ROOT / 'benchmarks/benchmark_mechanism_ablation.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_each_comparison_changes_exactly_its_declared_factor():
    configs = m.configurations('fixed-tokenizer-revision')
    assert len(configs) == 10
    for arm, (parent, flag) in m.EDGES.items():
        assert {k for k in configs[arm] if configs[arm][k] != configs[parent][k]} == {flag}
    assert configs['continuation']['PIJIT_TOKENIZER_REVISION'] == 'fixed-tokenizer-revision'
    assert configs['routing']['PIJIT_DISABLE_CODEBOOK'] == '0'
    assert configs['context']['PIJIT_BATCH_TOOLS'] == '1'
    assert all(c['PIJIT_JIT_ACTIONS'] == c['PIJIT_SCHEMA_ACTIONS'] == '0' for c in configs.values())
