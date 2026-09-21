"""Validate independent workload oracles before consuming GPU time."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from expanded_agent_scenarios import SCENARIOS, REFERENCES


def verify():
    results = []
    for name, replacements in REFERENCES.items():
        scenario = SCENARIOS[name]
        with tempfile.TemporaryDirectory(prefix='tair-oracle-preflight-') as temp:
            project = Path(temp)
            for filename, content in scenario['files'].items():
                path = project / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            command = [sys.executable, '-B', '-c', scenario['check']]
            baseline = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=20)
            for filename, content in replacements.items():
                path = project / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            reference = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=20)
            result = {'case': name, 'baseline_rejected': baseline.returncode != 0,
                      'reference_passed': reference.returncode == 0, 'reference_stderr': reference.stderr}
            results.append(result)
    return results


if __name__ == '__main__':
    results = verify()
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(r['baseline_rejected'] and r['reference_passed'] for r in results) else 1)
