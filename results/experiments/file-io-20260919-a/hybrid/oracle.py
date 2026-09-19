import os, sys
sys.path.insert(0, os.getcwd())
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
assert Path('test_file_io.py').is_file(), 'Missing delivered tests'
from file_io import read_text, write_text
with tempfile.TemporaryDirectory() as folder:
 root=Path(folder);p=root/'文本.txt'
 assert write_text(p,'你好 café 🌍\nsecond line\n') is None
 assert p.read_bytes()=='你好 café 🌍\nsecond line\n'.encode('utf-8')
 assert read_text(str(p))=='你好 café 🌍\nsecond line\n'
 assert write_text(str(p),'replacement') is None
 assert read_text(p)=='replacement'
 assert write_text(p,'\n追加',append=True) is None
 assert read_text(p)=='replacement\n追加'
 assert write_text(p,'') is None and read_text(p)==''
 assert write_text(p,'',append=True) is None and read_text(p)==''
 q=root/'new.txt';assert write_text(q,'new',append=True) is None and read_text(q)=='new'
 try:read_text(root/'missing.txt')
 except FileNotFoundError:pass
 else:raise AssertionError('Missing read must raise FileNotFoundError')
 try:write_text(root/'missing-parent'/'new.txt','x')
 except FileNotFoundError:pass
 else:raise AssertionError('Must not create parent directories')
 assert not (root/'missing-parent').exists()
 # Run the delivered tests independently, outside the Agent timing.
 result=subprocess.run([sys.executable,'-B','-m','unittest','-v','test_file_io'],capture_output=True,text=True,timeout=8)
 assert result.returncode==0,result.stdout+result.stderr
 print(result.stderr)
print('Independent file I/O checks passed')
