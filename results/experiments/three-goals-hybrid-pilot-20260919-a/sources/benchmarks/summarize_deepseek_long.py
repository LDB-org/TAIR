"""Summarize long-call fidelity, paired costs, and trusted-fixture execution."""
import argparse
import ast
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile


def validate_code(content):
    compile(content, 'report.py', 'exec')
    with tempfile.TemporaryDirectory(prefix='openjev-long-') as tmp:
        root = Path(tmp)
        (root/'report.py').write_text(content)
        (root/'data.csv').write_text('category,amount\nfood,1.20\ntravel,3.00\nfood,-0.10\n')
        result = subprocess.run([sys.executable, '-I', '-S', str(root/'report.py'), str(root/'data.csv')],
                                capture_output=True, text=True, timeout=5, check=True)
        assert json.loads(result.stdout) == [
            {'category': 'food', 'count': 2, 'total': '1.10'},
            {'category': 'travel', 'count': 1, 'total': '3.00'}]
        markdown = subprocess.run([sys.executable, '-I', '-S', str(root/'report.py'), str(root/'data.csv'), '--format', 'markdown'],
                                  capture_output=True, text=True, timeout=5, check=True)
        assert markdown.stdout == 'Category | Count | Total\n--- | ---: | ---:\nfood | 2 | 1.10\ntravel | 1 | 3.00\n'
    return True


def summarize(directory):
    rows = [json.loads(line) for line in (directory/'rows.jsonl').read_text().splitlines()]
    cases = json.loads((directory/'cases.json').read_text())
    expected = {name: {'name': name, 'arguments': args} for name, _, args in cases}
    # Only execute the known fixture, and only when model output matches it exactly.
    code_valid = validate_code(expected['write']['arguments']['content'])
    edits = expected['edit']['arguments']['edits']
    config = edits[0]['oldText']
    assert config.count(edits[0]['oldText']) == 1
    config = config.replace(edits[0]['oldText'], edits[0]['newText'], 1)
    compile(config, 'config.py', 'exec')
    services = ast.literal_eval(ast.parse(config).body[0].value)
    assert len(services) == 16 and all(v['enabled'] and v['timeout'] == 30 for v in services.values())
    groups = {}
    for name in [*expected, 'all']:
        groups[name] = {}
        for mode in ['whole', 'direct']:
            rs = [r for r in rows if r['mode'] == mode and (name == 'all' or r['case'] == name)]
            if not rs:
                continue
            groups[name][mode] = {'n': len(rs), 'complete': sum(r['complete'] for r in rs),
                'exact': sum(r.get('call') == expected[r['case']] for r in rs),
                'generated_tokens': sum(r['tokens'] for r in rs),
                'internal_control_records': sum(r.get('response', {}).get('classification_control_records', 0) for r in rs),
                'total_seconds': sum(r['seconds'] for r in rs),
                'median_seconds': statistics.median(r['seconds'] for r in rs)}
    pairs = []
    for name in expected:
        for repeat in sorted({r['repeat'] for r in rows}):
            arms = {r['mode']: r for r in rows if r['case'] == name and r['repeat'] == repeat}
            if len(arms) != 2:
                continue
            same = arms['whole'].get('call') == arms['direct'].get('call') == expected[name]
            pairs.append({'case': name, 'repeat': repeat, 'both_exact': same,
                'token_difference': arms['whole']['tokens']-arms['direct']['tokens'],
                'seconds_difference': arms['whole']['seconds']-arms['direct']['seconds']})
    diagnostics = []
    for row in rows:
        detail = {k: row[k] for k in ['case', 'repeat', 'mode']}
        args = row.get('call', {}).get('arguments', {})
        try:
            if row['case'] == 'write':
                actual = args['content']
                compile(actual, 'generated-report.py', 'exec')
                detail['syntax_valid'] = True
                equivalent = ast.dump(ast.parse(actual)) == ast.dump(ast.parse(expected['write']['arguments']['content']))
                detail['ast_matches_fixture'] = equivalent
                detail['runtime_passed'] = validate_code(actual) if equivalent else None
            elif row['case'] == 'edit':
                actual = edits[0]['oldText']
                for change in args['edits']:
                    assert actual.count(change['oldText']) == 1
                    actual = actual.replace(change['oldText'], change['newText'], 1)
                compile(actual, 'generated-config.py', 'exec')
                detail['applied_file_exact'] = actual == edits[0]['newText']
            else:
                actual = args['content']
                detail['matches_except_final_newline'] = actual.rstrip('\n') == expected['reply_user']['arguments']['content'].rstrip('\n')
        except (SyntaxError, KeyError, AssertionError, TypeError, ValueError) as error:
            detail['validation_error'] = str(error) or type(error).__name__
        diagnostics.append(detail)
    return {'groups': groups, 'pairs': pairs, 'known_python_fixture_runs': code_valid,
            'exact_python_outputs_covered_by_fixture_test': sum(r['case'] == 'write' and r.get('call') == expected['write'] for r in rows),
            'known_edit_fixture_applies_and_compiles': True,
            'posthoc_diagnostics_not_replacements_for_exact_score': diagnostics,
            'scope': 'Fixed long-content reproduction, not autonomous long-horizon agent tasks'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    print(json.dumps(summarize(a.directory), indent=2))
