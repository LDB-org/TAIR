import json, subprocess, sys
from catalog import clean_names
cases = [([], []), ([' ', '\t'], []), ([' Ada ', 'Ada', '', ' Bob', 'Ada'], ['Ada', 'Bob']),
         (['乙', ' 甲 ', '乙', '甲'], ['乙', '甲']), (['B', 'A', 'B'], ['B', 'A'])]
for source, expected in cases:
    assert clean_names(source) == expected, (source, expected)
cli = subprocess.run([sys.executable, 'catalog.py'], capture_output=True, text=True, timeout=10)
assert cli.returncode == 0 and json.loads(cli.stdout) == ['Ada', 'Bob'], cli
tests = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_catalog'], capture_output=True, text=True, timeout=20)
assert tests.returncode == 0, tests.stdout + tests.stderr
print(json.dumps({'behavior_cases': len(cases) + 1, 'model_tests': tests.stderr}))
