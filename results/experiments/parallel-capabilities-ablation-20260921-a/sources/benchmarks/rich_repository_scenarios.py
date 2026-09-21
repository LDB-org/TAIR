"""New repository tasks on Rich 13.7.1; upstream sources stay outside Git evidence."""
import ast
from pathlib import Path
import subprocess

COMMIT = '7f580bdcf07a3b269a0e786b6a3aa9c804f393cf'
JSON_PATH = 'rich/json.py'
SIZE_PATH = 'rich/filesize.py'


def cli_ast(source, default=None, alias=None, utf8=False):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == 'read_text' and utf8:
            node.keywords.append(ast.keyword(arg='encoding', value=ast.Constant('utf-8')))
        if node.func.attr != 'add_argument' or not any(isinstance(a, ast.Constant) and a.value == '--indent' for a in node.args):
            continue
        if default is not None:
            next(k for k in node.keywords if k.arg == 'default').value = ast.Constant(default)
        if alias is not None:
            node.args.append(ast.Constant(alias))
        node.args.sort(key=lambda a: a.value)
    return ast.dump(tree)


def cli_check(source, default=2, alias=None, utf8=False):
    expected = cli_ast(source, default=default, alias=alias, utf8=utf8)
    return f'''import ast,json,os,subprocess,sys,tempfile
from pathlib import Path
data={{"nested":{{"value":[1,2]}},"text":{"雪" if utf8 else "plain"!r}}}
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TERM='dumb',NO_COLOR='1',COLUMNS='160',LC_ALL='C',PYTHONUTF8='0',PYTHONCOERCECLOCALE='0',PYTHONIOENCODING='utf-8')
with tempfile.TemporaryDirectory() as temp:
 path=Path(temp)/'sample.json';path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
 for flags,width in [([], {default}),(['-i','1'],1),(['--indent','3'],3)]+{[([alias,'5'],5)] if alias else []!r}:
  for target in [str(path),'-']:
   run=subprocess.run([sys.executable,'-m','rich.json',*flags,target],input=path.read_bytes(),capture_output=True,env=env,timeout=10)
   assert run.returncode==0,run.stderr
   assert run.stdout.decode('utf-8')==json.dumps(data,indent=width,ensure_ascii=False)+'\\n',run.stdout
 run=subprocess.run([sys.executable,'-m','rich.json','--unknown-flag'],capture_output=True,env=env,timeout=10)
 assert run.returncode==2
from rich.json import JSON
assert JSON(json.dumps(data)).text.plain==json.dumps(data,indent=2,ensure_ascii=False)
tree=ast.parse(Path({JSON_PATH!r}).read_text())
for node in ast.walk(tree):
 if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='add_argument' and any(isinstance(a,ast.Constant) and a.value=='--indent' for a in node.args):
  node.args.sort(key=lambda a:a.value)
  node.keywords=[k for k in node.keywords if not (k.arg=='dest' and isinstance(k.value,ast.Constant) and k.value.value=='indent')]
assert ast.dump(tree)=={expected!r},'Unrelated AST change'
'''


def scenarios_for(repository):
    repository = Path(repository).resolve()
    assert subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
    paths = [repository / p for p in ['LICENSE', 'README.md', 'pyproject.toml']]
    paths += sorted((repository / 'rich').rglob('*.py')) + [repository / 'rich/py.typed']
    files = {str(p.relative_to(repository)): p.read_text() for p in paths}
    source = files[JSON_PATH]
    scenarios = {}
    for name, changes in [('rich_json_default', [dict(default=n) for n in [4,4,6]]),
                           ('rich_json_short_alias', [dict(alias=a) for a in ['-I','-I','-J']])]:
        variants = []
        for change in changes:
            clause = (f"Change --indent default to {change['default']}." if 'default' in change
                      else f"Add alias {change['alias']} to --indent.")
            variants.append(dict(prompt=f'Read {JSON_PATH}. {clause} Modify only the CLI argument declaration; preserve the public JSON class defaults, help text, stdin support and explicit -i/--indent overrides. Verify python -m rich.json using temporary files and stdin, then summarize.',
                                 check=cli_check(source, **change)))
        scenarios[name] = dict(primary_file=JSON_PATH, variants=variants, **variants[0])
    scenarios['rich_json_utf8'] = dict(primary_file=JSON_PATH,
        prompt=f'In the CLI section of {JSON_PATH}, make the Path.read_text call explicitly use encoding="utf-8", so UTF-8 JSON files work with C locale, UTF-8 mode off and locale coercion off. Change only that call; retain stdin support and all formatting options. Verify the actual CLI with Unicode JSON in a temporary file and stdin, then summarize.',
        check=cli_check(source, utf8=True))
    tree = ast.parse(files[SIZE_PATH])
    tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == 'decimal')]
    check = f'''import ast
from pathlib import Path
from rich.filesize import decimal
for size in [-1,-1000,-10**18]:
 try:decimal(size)
 except ValueError as error:assert 'non-negative' in str(error)
 else:raise AssertionError('Negative filesize accepted')
for size,expected in [(0,'0 bytes'),(1,'1 byte'),(999,'999 bytes'),(1000,'1.0 kB'),(1530,'1.5 kB'),(1000000,'1.0 MB')]:
 assert decimal(size)==expected
assert decimal(1530,precision=2,separator='')=='1.53kB'
tree=ast.parse(Path({SIZE_PATH!r}).read_text())
tree.body=[n for n in tree.body if not (isinstance(n,ast.FunctionDef) and n.name=='decimal')]
assert ast.dump(tree)=={ast.dump(tree)!r},'Changed code outside decimal'
'''
    scenarios['rich_filesize_negative'] = dict(primary_file=SIZE_PATH,
        prompt=f'Update decimal in {SIZE_PATH} to reject negative sizes by raising ValueError with a message containing "non-negative". Preserve zero, singular byte, SI units, precision and separator behavior. Modify only decimal, leaving helpers and other code unchanged. Run Python checks covering these behaviors, then summarize.', check=check)
    for scenario in scenarios.values():
        scenario.update(files=files, protected=[p for p in files if p != scenario['primary_file']], upstream_commit=COMMIT)
    return scenarios


def reference_source(name, source, variant):
    if name == 'rich_json_default':
        value = variant['prompt'].split('default to ')[1].split('.')[0]
        return source.replace('default=2,', f'default={value},', 1)
    if name == 'rich_json_short_alias':
        alias = variant['prompt'].split('Add alias ')[1].split()[0]
        return source.replace('        "--indent",', f'        "--indent",\n        {alias!r},', 1)
    if name == 'rich_json_utf8':
        return source.replace('Path(args.path).read_text()', 'Path(args.path).read_text(encoding="utf-8")')
    if name == 'rich_filesize_negative':
        return source.replace('    return _to_str(', '    if size < 0:\n        raise ValueError("size must be non-negative")\n    return _to_str(', 1)
    raise ValueError(name)
