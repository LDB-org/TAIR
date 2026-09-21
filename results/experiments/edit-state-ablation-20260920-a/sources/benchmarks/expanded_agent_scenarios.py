"""Broader stdlib-only Agent workloads and offline oracle reference fixtures."""
import copy
import json
from benchmark_schema_jit_agent import SCENARIOS as ORIGINAL
from benchmark_general_pijit import SCENARIOS as GENERAL

SCENARIOS = copy.deepcopy(ORIGINAL)
SCENARIOS['multifile_feature'] = copy.deepcopy(GENERAL['multifile_feature'])
SCENARIOS['nested_package'] = {
    'files': {'app.py': 'from pkg.stats import moving_average\n', 'pkg/__init__.py': '',
              'pkg/stats.py': 'def moving_average(values, window):\n    return [sum(values)/len(values)]\n',
              'test_app.py': '''import unittest
from app import moving_average
class TestAverage(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(moving_average([1,2,3,4],2),[1.5,2.5,3.5])
    def test_empty(self):
        self.assertEqual(moving_average([],2),[])
    def test_invalid(self):
        with self.assertRaises(ValueError): moving_average([1],0)
'''},
    'prompt': 'Inspect app.py and follow its imports. Fix moving_average(values, window) in the nested package: return the mean of every contiguous full window in order, [] if input is shorter than the window, and raise ValueError for window<=0 even on empty input. Handle negative and float values without mutating inputs. Preserve public imports and existing tests. Run python -m unittest -v and summarize.',
    'check': '''from app import moving_average
for xs in [[],[2],[1,2,3,4],[-2.5,1.5,-3,8]]:
 for w in range(1,7):
  before=list(xs)
  expected=[sum(xs[i:i+w])/w for i in range(max(0,len(xs)-w+1))]
  assert moving_average(xs,w)==expected
  assert xs==before
for w in [0,-1,-12]:
 try: moving_average([],w)
 except ValueError: pass
 else: raise AssertionError('invalid window accepted')
'''}
SCENARIOS['quoted_csv'] = {
    'files': {'app.py': '''def parse_people(text):
    return [{'name': parts[0], 'age': int(parts[1]), 'active': parts[2]=='yes'}
            for line in text.splitlines()[1:] if line.strip()
            for parts in [line.split(',')]]
''', 'test_app.py': '''import unittest
from app import parse_people
class TestCSV(unittest.TestCase):
    def test_comma(self):
        self.assertEqual(parse_people('name,age,active\\n"Doe, Jane",31,yes\\n'),[{'name':'Doe, Jane','age':31,'active':True}])
    def test_empty(self):
        self.assertEqual(parse_people('name,age,active\\n'),[])
'''},
    'prompt': 'Fix parse_people(text) to parse CSV using the standard library, including quoted commas, escaped quotes, quoted embedded newlines, and CRLF. The header fields are name, age, active; return dictionaries preserving name text, converting age with int, and active true only for the literal yes. Ignore blank records. Invalid ages must raise ValueError. Keep existing tests unchanged. Run python -m unittest -v and summarize.',
    'check': '''import csv,io
from app import parse_people
rows=[['Doe, Jane','31','yes'],['He said "Hi"','-2','no'],['Multi'+chr(10)+'line','7','YES'],['  spaced  ','0','yes']]
s=io.StringIO(); writer=csv.writer(s);writer.writerow(['name','age','active']);writer.writerows(rows)
assert parse_people(s.getvalue())==[{'name':r[0],'age':int(r[1]),'active':r[2]=='yes'} for r in rows]
assert parse_people('name,age,active\\n\\n')==[]
try: parse_people('name,age,active\\nAlice,invalid,yes\\n')
except ValueError: pass
else: raise AssertionError('invalid age swallowed')
'''}
CONFIG = {'server': {'port': 8080, 'host': '127.0.0.1'}, 'retry': {'count': 1, 'backoff': 0.5},
          'features': ['metrics'], 'metadata': {'owner': 'example', 'revision': 7}}
SCENARIOS['json_config'] = {
    'files': {'app.py': '''import json
from pathlib import Path
def settings():
    return json.loads((Path(__file__).parent/'config/settings.json').read_text())
''', 'config/settings.json': json.dumps(CONFIG, indent=2)+'\n',
              'docs/notes.md': 'Existing configuration notes. Preserve this file.\n',
              'test_app.py': '''import unittest
from app import settings
class TestSettings(unittest.TestCase):
    def test_update(self):
        c=settings()
        self.assertEqual(c['server']['port'],9090)
        self.assertEqual(c['retry']['count'],4)
        self.assertEqual(c['features'],['metrics','tracing'])
'''},
    'prompt': 'Update config/settings.json: server.port=9090, retry.count=4, append tracing to features without removing metrics. Preserve all other fields, app.py, docs, and tests exactly. Run python -m unittest -v and summarize.',
    'check': "from app import settings\nassert settings()=="+repr({**CONFIG, 'server': {**CONFIG['server'], 'port': 9090}, 'retry': {**CONFIG['retry'], 'count': 4}, 'features': ['metrics','tracing']})+'\n'}
SCENARIOS['exception_boundary'] = {
    'files': {'app.py': '''import json
def load_record(path):
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except Exception:
        return {}
''', 'test_app.py': '''import tempfile,unittest
from pathlib import Path
from app import load_record
class TestRecords(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(load_record(Path(d)/'missing.json'))
    def test_bad_json(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text('{bad')
            with self.assertRaises(json.JSONDecodeError):load_record(p)
'''},
    'prompt': 'Fix load_record(path): return None only when opening a nonexistent file raises FileNotFoundError. Preserve UTF-8 JSON decoding. Malformed JSON, permission errors, directory errors and other exceptions must propagate. Do not change tests. Run python -m unittest -v and summarize.',
    'check': '''import json,tempfile
from pathlib import Path
from unittest.mock import patch
from app import load_record
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'data.json';p.write_text(json.dumps({'name':'雪','value':0}),encoding='utf-8')
 assert load_record(p)=={'name':'雪','value':0}
 assert load_record(Path(d)/'missing') is None
 p.write_text('{broken')
 try: load_record(p)
 except json.JSONDecodeError: pass
 else: raise AssertionError('decode error swallowed')
for error in [PermissionError('denied'),IsADirectoryError('directory'),RuntimeError('other')]:
 with patch('builtins.open',side_effect=error):
  try: load_record('unused')
  except type(error): pass
  else: raise AssertionError('wrong exception boundary')
'''}
SCENARIOS['cross_file_behavior'] = {
    'files': {'app.py': 'from service import render_users\n',
              'formatter.py': "def display_name(user):\n    return user.get('name', '')\n",
              'service.py': "from formatter import display_name\ndef render_users(users):\n    return '\\n'.join(display_name(u) for u in users)\n",
              'test_app.py': '''import unittest
from app import render_users
class TestUsers(unittest.TestCase):
    def test_names(self):
        self.assertEqual(render_users([{'name':' Zoe '},{'name':'alice'},{'name':' '}]),'alice\\nUnknown\\nZoe')
    def test_empty(self):
        self.assertEqual(render_users([]),'')
'''},
    'prompt': 'Inspect app.py and the imported modules. Update display_name(user) to strip name whitespace and return Unknown for missing, None, or whitespace-only names. Update render_users(users) to join display names with newlines sorted by casefold, preserving the original order for equal sort keys. Do not mutate users or their dictionaries. Preserve public imports and existing tests. Run python -m unittest -v and summarize.',
    'check': '''import copy
from app import render_users
from formatter import display_name
for u,expected in [({},'Unknown'),({'name':None},'Unknown'),({'name':'  '},'Unknown'),({'name':' 雪 '},'雪')]:
 before=copy.deepcopy(u);assert display_name(u)==expected;assert u==before
users=[{'name':'b'},{'name':'A'},{'name':'a'},{'name':' B '},{'other':3}]
before=copy.deepcopy(users)
assert render_users(users)=='A\\na\\nb\\nB\\nUnknown'
assert users==before
assert render_users([])==''
'''}
NOISE = {f'unrelated_{i:03}.py': ''.join(f'def untouched_{i}_{j}():\n    return {i*100+j}\n\n' for j in range(30)) for i in range(80)}
SCENARIOS['wide_project'] = {
    'files': {**NOISE, 'app.py': 'from engine.normalize import unique_names\n', 'engine/__init__.py': '',
              'engine/normalize.py': 'def unique_names(names):\n    return sorted(set(names))\n',
              'test_app.py': '''import unittest
from app import unique_names
class TestNames(unittest.TestCase):
    def test_order(self):
        self.assertEqual(unique_names([' B ','a','b',' A ','']),['B','a'])
    def test_empty(self):
        self.assertEqual(unique_names([]),[])
'''},
    'prompt': 'This project contains many unrelated modules. Start from app.py and follow its imports. Fix unique_names(names): strip each string, drop empty strings, deduplicate by casefold while preserving the first stripped spelling and encounter order. Preserve input contents, public imports, all unrelated files and existing tests. Run python -m unittest -v and summarize.',
    'check': '''from app import unique_names
for xs,expected in [([],[]),([' B ','a','b',' A ',''],['B','a']),(['Straße','STRASSE','雪',' 雪 '],['Straße','雪']),(['x','X','y','x'],['x','y'])]:
 before=list(xs);assert unique_names(xs)==expected;assert xs==before
'''}

REFERENCES = {
    'multifile_feature': {'app.py': '''import argparse
from textutil import slugify
def main():
    p=argparse.ArgumentParser();p.add_argument('text');p.add_argument('--slug',action='store_true')
    args=p.parse_args();print(slugify(args.text) if args.slug else args.text)
if __name__=='__main__':main()
''', 'textutil.py': "def slugify(text):\n    return '-'.join(text.lower().split())\n",
    'README.md': '# Text CLI\nRun python app.py --slug "Hello World".\n',
    'test_app.py': '''import subprocess,sys,unittest
from textutil import slugify
class TestSlug(unittest.TestCase):
    def test_utility(self):self.assertEqual(slugify(' A  B '),'a-b')
    def test_cli(self):
        for flags,expected in [([], ' A B \\n'),(['--slug'],'a-b\\n')]:
            self.assertEqual(subprocess.check_output([sys.executable,'app.py',*flags,' A B '],text=True),expected)
'''},
    'nested_package': {'pkg/stats.py': 'def moving_average(values, window):\n    if window <= 0: raise ValueError("window")\n    return [sum(values[i:i+window])/window for i in range(max(0,len(values)-window+1))]\n'},
    'quoted_csv': {'app.py': "import csv,io\ndef parse_people(text):\n    return [{'name':r['name'],'age':int(r['age']),'active':r['active']=='yes'} for r in csv.DictReader(io.StringIO(text))]\n"},
    'json_config': {'config/settings.json': json.dumps({**CONFIG, 'server': {**CONFIG['server'], 'port': 9090}, 'retry': {**CONFIG['retry'], 'count': 4}, 'features': ['metrics','tracing']}, indent=2)+'\n'},
    'exception_boundary': {'app.py': SCENARIOS['exception_boundary']['files']['app.py'].replace('except Exception:', 'except FileNotFoundError:').replace('return {}','return None')},
    'cross_file_behavior': {'formatter.py': "def display_name(user):\n    return (user.get('name') or '').strip() or 'Unknown'\n", 'service.py': "from formatter import display_name\ndef render_users(users):\n    return '\\n'.join(sorted((display_name(u) for u in users),key=str.casefold))\n"},
    'wide_project': {'engine/normalize.py': "def unique_names(names):\n    result=[];seen=set()\n    for name in names:\n        name=name.strip();key=name.casefold()\n        if name and key not in seen:\n            result.append(name);seen.add(key)\n    return result\n"},
}

# Independent oracles run outside the agent and include an actual unittest rerun.
for name, scenario in SCENARIOS.items():
    protected = {p: text for p, text in scenario['files'].items()
                 if p.startswith('unrelated_') or (name == 'json_config' and p in ('app.py','docs/notes.md'))}
    scenario['check'] += '\nfrom pathlib import Path\n'
    for path, text in protected.items():
        import hashlib
        scenario['check'] += f"import hashlib\nassert hashlib.sha256(Path({path!r}).read_bytes()).hexdigest()=={hashlib.sha256(text.encode()).hexdigest()!r}\n"
    scenario['check'] += "\nimport subprocess,sys\nr=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)\nassert r.returncode==0,(r.stdout,r.stderr)\n"
