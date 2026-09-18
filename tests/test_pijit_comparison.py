import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    'pijit_comparison', Path(__file__).parents[1] / 'benchmarks/compare_pijit_c4.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def test_pairs_share_sources_and_failed_attempts_remain_in_totals(tmp_path, monkeypatch):
    inputs = []
    def fake_run(payload):
        project = Path(payload['cwd'])
        inputs.append((payload['session_id'], (project / 'app.py').read_text()))
        number = int(payload['task'].split()[-1][:-1])
        failed = len(inputs) == 1
        if not failed:
            (project / 'app.py').write_text(c.source_for(number))
        return {'status': 'error' if failed else 'ok', 'cache_hit': False, 'stage_seconds': {},
                'accounting': {'usage_complete': not failed, 'unknown_usage_requests': int(failed),
                               'inference_requests': 1, 'known_input_tokens': 10,
                               'known_generated_argument_tokens': 3,
                               'known_classification_control_records': 1}}
    monkeypatch.setattr(c.bridge, 'run', fake_run)
    monkeypatch.setattr(c.bridge, 'STATE', tmp_path / 'state')
    monkeypatch.setenv('PIJIT_DISABLE_CODEBOOK', '0')
    monkeypatch.setenv('PIJIT_VERIFY_CMD', '')
    args = SimpleNamespace(out=tmp_path / 'run', seed=42, repeats=1, values=[6, 8])
    summary = c.run(args)
    assert inputs[0][1] == inputs[1][1] == c.source_for(4)
    assert inputs[2][1] == inputs[3][1] == c.source_for(6)
    assert sum(a['passed'] for a in summary['arms'].values()) == 3
    assert sum(a['inference_requests'] for a in summary['arms'].values()) == 4
    assert sum(a['unknown_usage_requests'] for a in summary['arms'].values()) == 1
    assert summary['observed_generation_over_c4_wall_ratio'] is None
    assert len((args.out / 'rows.jsonl').read_text().splitlines()) == 4
    with pytest.raises(FileExistsError):
        c.run(args)
