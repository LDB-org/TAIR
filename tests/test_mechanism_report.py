from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location('mechanism_report', Path(__file__).parents[1] / 'benchmarks/report_mechanism_ablation.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_failed_and_timed_out_attempts_remain_in_cost_and_usage():
    def row(seconds, passed, complete):
        return {'validated_seconds': seconds, 'base_passed': passed, 'passed': passed,
                'timed_out': not complete, 'usage_complete': complete,
                'metrics': [{'action': 'chat', 'accounting': {'inference_requests': 2,
                    'known_input_tokens': 100, 'known_generated_argument_tokens': 3,
                    'known_classification_control_records': 2}}]}
    result = m.agent_summary([row(2, True, True), row(120, False, False)])
    assert result['tasks'] == 2 and result['audited_passed'] == 1
    assert result['wall_seconds'] == 122
    assert result['counts_are_lower_bounds'] and not result['usage_complete']
    assert result['inference_requests'] == 4
    assert result['known_generated_argument_tokens'] == 6
    assert result['known_classification_control_records'] == 4
    assert result['known_input_tokens'] == 200


def test_slowdown_is_negative_savings_and_zero_baseline_has_no_percentage():
    result = m.change(10, 15)
    assert result['saved_seconds'] == -5 and result['saved_percent'] == -50
    assert m.change(0, 1)['saved_percent'] is None
