import json, sys, subprocess
sys.path.insert(0, '/work')
from statistics_app import summarize_numbers
for values in [[], [0], [-4,-2], [3,3,1], [0.25,-1,2.5], [3,-1,3,0.5]]:
    before = list(values)
    expected = dict(count=len(values), total=sum(values), min=min(values) if values else None, max=max(values) if values else None)
    assert summarize_numbers(values) == expected, (values, summarize_numbers(values))
    assert values == before
result = subprocess.run([sys.executable, 'statistics_app.py'], capture_output=True, text=True, timeout=10)
assert result.returncode == 0 and json.loads(result.stdout) == dict(count=4,total=5.5,min=-1,max=3)
tests = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_statistics_app'], capture_output=True, text=True, timeout=20)
assert tests.returncode == 0, tests.stdout + tests.stderr
print(json.dumps({'behavior_checks': 7, 'model_tests': tests.stderr}))
