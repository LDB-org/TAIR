"""Pinned upstream CPython tool tasks, including generated-template transfer and unsupported fixes."""
import ast
from pathlib import Path
import subprocess

COMMIT = 'de54cf5be371a6f5e2e9f208c38def5f81d3ef02'
DIFF = 'Tools/scripts/diff.py'
UPDATE = 'Tools/scripts/update_file.py'


def expected_cli(source, *, default=None, alias=None):
    tree = ast.parse(source)
    call, = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'add_argument' and any(isinstance(a, ast.Constant) and a.value == '--lines' for a in n.args)]
    if default is not None:
        keyword, = [k for k in call.keywords if k.arg == 'default']
        keyword.value = ast.Constant(value=default)
    if alias is not None:
        call.args.append(ast.Constant(value=alias))
    call.args.sort(key=lambda a: a.value)
    return ast.dump(tree, include_attributes=False)


def diff_check(default=3, alias=None, utf8=False):
    changed = '雪 changed\n' if utf8 else 'changed\n'
    first = '雪 left\n' if utf8 else 'line 0\n'
    return f'''import difflib,os,subprocess,sys,tempfile
from pathlib import Path
script=Path({DIFF!r}).resolve()
with tempfile.TemporaryDirectory() as temp:
 a,b=Path(temp)/'a.txt',Path(temp)/'b.txt'
 left=[f"line {{i}}\\n" for i in range(20)]
 left[0]={first!r}
 right=list(left);right[9]={changed!r}
 a.write_text(''.join(left),encoding='utf-8');b.write_text(''.join(right),encoding='utf-8')
 for flags,n in [([], {default}),(['-l','1'],1),(['--lines','2'],2)]+{[([alias,'4'],4)] if alias else []!r}:
  env=dict(os.environ,LC_ALL='C',PYTHONUTF8='0',PYTHONCOERCECLOCALE='0',PYTHONIOENCODING='utf-8')
  p=subprocess.run([sys.executable,str(script),'-u',*flags,str(a),str(b)],capture_output=True,env=env,timeout=10)
  assert p.returncode==0,p.stderr
  actual=p.stdout.decode('utf-8').splitlines(keepends=True)[2:]
  expected=list(difflib.unified_diff(left,right,n=n))[2:]
  assert actual==expected,(actual,expected)
 p=subprocess.run([sys.executable,str(script),'--unknown-flag'],capture_output=True,timeout=10)
 assert p.returncode==2
'''


def cli_variant(source, *, default=None, alias=None):
    clause = f'Change --lines default to {default}.' if default is not None else f'Add alias {alias} to --lines.'
    prompt = (f'Read {DIFF}. {clause} Preserve all other behavior and existing options, including explicit context-length overrides. '
              'Modify only this script; keep existing help text unchanged. Use temporary files to check actual CLI diff output with default and explicit context lengths, then summarize.')
    check = diff_check(default if default is not None else 3, alias)
    check += f'''import ast
source=Path({DIFF!r}).read_text()
tree=ast.parse(source)
call,=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='add_argument' and any(isinstance(a,ast.Constant) and a.value=='--lines' for a in n.args)]
call.args.sort(key=lambda a:a.value)
call.keywords=[k for k in call.keywords if not (k.arg=='dest' and isinstance(k.value,ast.Constant) and k.value.value=='lines')]
assert ast.dump(tree,include_attributes=False)=={expected_cli(source,default=default,alias=alias)!r},'Unrelated code or option changed'
'''
    return {'prompt':prompt,'check':check}


def scenarios_for(repository):
    repository = Path(repository).resolve()
    actual = subprocess.check_output(['git','-C',str(repository),'rev-parse','HEAD'],text=True).strip()
    if actual != COMMIT:
        raise ValueError(f'Expected CPython {COMMIT}, got {actual}')
    paths = [repository/'LICENSE', repository/'README.rst', *sorted((repository/'Tools/scripts').rglob('*'))]
    files = {str(p.relative_to(repository)):p.read_text() for p in paths if p.is_file() and '__pycache__' not in p.parts}
    source = files[DIFF]
    scenarios = {}
    for name, variants in {
        'cpython_diff_default':[cli_variant(source,default=n) for n in (5,5,7)],
        'cpython_diff_alias':[cli_variant(source,alias=a) for a in ('--context-lines','--context-lines','--context-size')],
        'cpython_diff_short_alias':[cli_variant(source,alias=a) for a in ('-C','-C','-N')],
    }.items():
        scenarios[name]={'files':files,'primary_file':DIFF,'protected':[p for p in files if p!=DIFF],
                         **variants[0],'variants':variants,'upstream_commit':COMMIT}
    scenarios['cpython_diff_utf8']={'files':files,'primary_file':DIFF,'protected':[p for p in files if p!=DIFF],
        'prompt':f'Update {DIFF} to explicitly read both input files as UTF-8, so Unicode diffs work even when Python UTF-8 mode and locale coercion are disabled in the C locale. Preserve output formats and command-line options. Modify only this script. Verify actual CLI behavior with Unicode files and explicit context lengths using temporary files, then summarize.',
        'check':diff_check(utf8=True),'upstream_commit':COMMIT}
    original_functions={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(files[UPDATE]).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name!='updating_file_with_tmpfile'}
    check=f'''import ast,importlib.util,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('upstream_update',{UPDATE!r})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for newline in [b'\\n',b'\\r\\n']:
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);src=root/'source.txt';work=root/'temporary';work.mkdir()
  src.write_bytes(b'old'+newline+b'keep'+newline)
  with m.updating_file_with_tmpfile(str(src),str(work)) as (inp,out):
   assert Path(out.name).name==src.name+'.tmp'
   assert Path(out.name).parent==work,'Temporary directory was ignored for absolute source path'
   out.write(inp.read().replace('old','new'))
  assert src.read_bytes()==b'new'+newline+b'keep'+newline
  assert list(work.iterdir())==[]
  with m.updating_file_with_tmpfile(str(src)) as (inp,out):out.write(inp.read())
  assert src.read_bytes()==b'new'+newline+b'keep'+newline
  assert not Path(str(src)+'.tmp').exists()
tree=ast.parse(Path({UPDATE!r}).read_text())
functions={{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name!='updating_file_with_tmpfile'}}
assert functions=={original_functions!r}
'''
    scenarios['cpython_update_tmpdir']={'files':files,'primary_file':UPDATE,'protected':[p for p in files if p!=UPDATE],
        'prompt':f'Fix updating_file_with_tmpfile in {UPDATE}: when tmpfile is a directory and filename is absolute, create the temporary file inside the supplied directory instead of beside the source file. Preserve the source basename with .tmp suffix, LF/CRLF handling, default temporary-file behavior and the separate update_file_with_tmpfile function. Modify only this script. Exercise the context manager with temporary files and verify the temporary location and final bytes, then summarize.',
        'check':check,'upstream_commit':COMMIT}
    return scenarios
