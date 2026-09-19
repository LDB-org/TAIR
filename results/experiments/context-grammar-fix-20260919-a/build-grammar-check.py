import importlib.util
import json
import tempfile
from pathlib import Path
root = Path('/Users/zacharyzcr/Projects/TAIR')
out = root / 'results/experiments/context-grammar-fix-20260919-a'
spec = importlib.util.spec_from_file_location('bridge', root / 'integrations/pijit/bridge.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
stock = json.loads((out / 'edit-tool-check.json').read_text())['parameters']
cases = []
with tempfile.TemporaryDirectory() as cwd:
    Path(cwd, 'app.py').write_text('placeholder')
    payload = {'cwd': cwd, 'context': {'messages': [
        {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'read1', 'name': 'read', 'arguments': {'path': 'app.py'}}]},
        {'role': 'toolResult', 'toolCallId': 'read1', 'content': [], 'isError': False}]}}
    for legacy in [False, True]:
        schema = stock if not legacy else {'type': 'object', 'properties': {'path': {'type': 'string'}, 'oldText': {'type': 'string'}, 'newText': {'type': 'string'}}, 'required': ['path', 'oldText', 'newText'], 'additionalProperties': False}
        tools, _ = b.contextual_tools(payload, [{'name': 'edit', 'parameters': schema}])
        plan = b.batch_tool(tools)['parameters']
        for value in ['plain text', '"port": 8080', 'first\nsecond', r'path\name', 'tab\tvalue', '中文', '']:
            edit = {'oldText': value, 'newText': 'new\n"value"\\'}
            args = {'path': 'app.py', **(edit if legacy else {'edits': [edit]})}
            cases.append({'legacy': legacy, 'schema': plan, 'payload': {'steps': [{'name': 'edit', 'arguments': args}]}, 'expected': True})
        cases.append({'legacy': legacy, 'schema': plan, 'payload': {'steps': []}, 'expected': False})
        args = {'path': 'unobserved.py', **(edit if legacy else {'edits': [edit]})}
        cases.append({'legacy': legacy, 'schema': plan, 'payload': {'steps': [{'name': 'edit', 'arguments': args}]}, 'expected': False})
(out / 'cases.json').write_text(json.dumps(cases, indent=2))
source = '''import importlib.metadata
import json
import xgrammar as xgr
CASES = json.loads(CASES_JSON)
compiler = xgr.GrammarCompiler(xgr.TokenizerInfo([bytes([i]) for i in range(256)], vocab_type=xgr.VocabType.RAW))
rows = []
for case in CASES:
    compiled = compiler.compile_json_schema(json.dumps(case['schema']))
    matcher = xgr.GrammarMatcher(compiled, terminate_without_stop_token=True)
    accepted = matcher.accept_string(json.dumps(case['payload'])) and matcher.is_terminated()
    rows.append({**case, 'accepted': accepted})
result = {'xgrammar_version': importlib.metadata.version('xgrammar'), 'scope': 'CPU matcher on full execute_plan schemas exported from patched bridge; no model inference', 'rows': rows, 'mismatches': sum(r['accepted'] != r['expected'] for r in rows)}
print(json.dumps(result, indent=2))
raise SystemExit(bool(result['mismatches']))
'''
(out / 'deployed-grammar-check.py').write_text('CASES_JSON = ' + repr(json.dumps(cases)) + '\n' + source)
