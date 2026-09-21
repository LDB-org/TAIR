"""Additional pinned CPython tasks; checks and references are not supplied to the Agent."""
import ast

UNTABIFY = 'Tools/scripts/untabify.py'
MD5SUM = 'Tools/scripts/md5sum.py'


def extra_scenarios(files):
    untabify_check = f'''import ast,subprocess,sys,tempfile
from pathlib import Path
script=Path({UNTABIFY!r}).resolve()
with tempfile.TemporaryDirectory() as temp:
 for flags,width in [([],4),(['-t','2'],2),(['-t','8'],8)]:
  p=Path(temp)/'sample.py'
  original=b"# coding: latin-1\\n# caf\\xe9\\n\\tvalue = 1\\n"
  p.write_bytes(original)
  run=subprocess.run([sys.executable,str(script),*flags,str(p)],capture_output=True,timeout=10)
  assert run.returncode==0,run.stderr
  assert p.read_bytes()==original.expandtabs(width)
  assert Path(str(p)+'~').read_bytes()==original
  unchanged=Path(temp)/'unchanged.py';unchanged.write_bytes(b'value = 1\\n')
  run=subprocess.run([sys.executable,str(script),str(unchanged)],capture_output=True,timeout=10)
  assert run.returncode==0 and run.stdout==b''
  assert unchanged.read_bytes()==b'value = 1\\n' and not Path(str(unchanged)+'~').exists()
assert ast.dump(ast.parse(script.read_text()))=={ast.dump(ast.parse(files[UNTABIFY].replace('tabsize = 8', 'tabsize = 4', 1)))!r}
'''
    untouched = {n.name: ast.dump(n) for n in ast.parse(files[MD5SUM]).body
                 if isinstance(n, ast.FunctionDef) and n.name != 'main'}
    md5_check = f'''import ast,hashlib,subprocess,sys,tempfile
from pathlib import Path
script=Path({MD5SUM!r}).resolve()
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp)/'data.bin';data=bytes(range(256))*39;p.write_bytes(data)
 for invalid in ['0','-1','-8192']:
  run=subprocess.run([sys.executable,str(script),'-s',invalid,str(p)],capture_output=True,timeout=10)
  assert run.returncode==2,(invalid,run.returncode,run.stdout,run.stderr)
  assert run.stdout==b'' and b'positive' in run.stderr.lower()
 for flags in [[],['-s','1'],['-s','7'],['-s','8192'],['-l']]:
  run=subprocess.run([sys.executable,str(script),*flags,str(p)],capture_output=True,timeout=10)
  assert run.returncode==0,run.stderr
  name=p.name if '-l' in flags else str(p)
  assert run.stdout.decode()==hashlib.md5(data).hexdigest()+' '+name+'\\n'
 run=subprocess.run([sys.executable,str(script),'-s','0',str(Path(temp)/'missing')],capture_output=True,timeout=10)
 assert run.returncode==2 and run.stdout==b'' and b'positive' in run.stderr.lower()
 assert p.read_bytes()==data
tree=ast.parse(script.read_text())
untouched={{n.name:ast.dump(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name!='main'}}
assert untouched=={untouched!r}
'''
    result = {}
    for name, path, prompt, check in [
        ('cpython_untabify_default', UNTABIFY,
         f'Change the default tab width in {UNTABIFY} from 8 to 4. Preserve -t overrides, source encoding, backup behavior, and unchanged-file behavior. Modify only this script and keep all other code unchanged. Verify the real CLI using temporary files, then summarize.', untabify_check),
        ('cpython_md5_positive_buffer', MD5SUM,
         f'In {MD5SUM}, make main reject a nonpositive -s buffer size before processing any input files. Return exit status 2, print a diagnostic containing "positive" to stderr, and emit no checksum. Preserve valid positive sizes, default behavior, and -l. Modify only main in this script. Verify the CLI with temporary files, including zero, negative and positive sizes, then summarize.', md5_check),
    ]:
        result[name] = dict(files=files, primary_file=path, prompt=prompt, check=check,
                            protected=[p for p in files if p != path])
    return result


def reference_source(name, source):
    if name == 'cpython_untabify_default':
        return source.replace('tabsize = 8', 'tabsize = 4', 1)
    if name == 'cpython_md5_positive_buffer':
        return source.replace('    if not args:\n',
                              '    if bufsize <= 0:\n'
                              '        sys.stderr.write("buffer size must be positive\\n")\n'
                              '        return 2\n'
                              '    if not args:\n', 1)
    raise ValueError(name)
