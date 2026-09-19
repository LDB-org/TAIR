from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from benchmark_three_goals import configuration


def differences(left, right):
    return {key for key in left.keys() | right.keys() if left.get(key) != right.get(key)}


def test_strong_native_controls_change_only_tool_parallel_flag():
    one, multi = (configuration(a, 'revision') for a in ('native_single', 'native_multi'))
    assert differences(one, multi) == {'TAIR_NATIVE_PARALLEL_TOOLS'}
    assert one['TAIR_NATIVE_PREFIX_CACHE'] == multi['TAIR_NATIVE_PREFIX_CACHE'] == '1'


def test_hybrid_codebook_control_changes_only_codebook_enablement():
    on, off = (configuration(a, 'revision') for a in ('hybrid', 'hybrid_no_book'))
    assert differences(on, off) == {'PIJIT_DISABLE_CODEBOOK'}
    assert on['PIJIT_BOUND_REUSE'] == on['PIJIT_NATIVE_PLANNER'] == '1'
    assert on['PIJIT_COMPLETION_CHECKS'] == '0'
