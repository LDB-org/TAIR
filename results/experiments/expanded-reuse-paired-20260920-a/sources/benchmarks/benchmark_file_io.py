"""Two cold Agent attempts to write a small local UTF-8 file utility."""
import argparse
from pathlib import Path
from benchmark_port_scanner import main

PROMPT = '''Write a small Python standard-library-only file_io.py module (the current file is empty).
Provide read_text(path) -> str and write_text(path, text, *, append=False) -> None.
Both accept str or pathlib.Path paths and use UTF-8. read_text reads the full file. write_text creates a missing file, overwrites by default, or appends when append=True. Preserve Unicode and LF newlines. Reading a missing file must raise FileNotFoundError. Do not create missing parent directories; let normal filesystem errors propagate. No CLI, framework, network access, or extra features. Importing the module must perform no I/O.
Write test_file_io.py using unittest and TemporaryDirectory, covering Unicode round-trip, overwrite, append, empty content, and missing-file errors. Keep the implementation and tests small. Run the tests, then briefly summarize. Perform file operations only in this workspace or your own temporary test directories; do not inspect or modify unrelated files. Do not install packages.'''
CHECK = '''import importlib.util, subprocess, sys, tempfile
from pathlib import Path
assert Path('test_file_io.py').is_file(), 'Missing delivered tests'
from file_io import read_text, write_text
with tempfile.TemporaryDirectory() as folder:
 root=Path(folder);p=root/'文本.txt'
 assert write_text(p,'你好 café 🌍\\nsecond line\\n') is None
 assert p.read_bytes()=='你好 café 🌍\\nsecond line\\n'.encode('utf-8')
 assert read_text(str(p))=='你好 café 🌍\\nsecond line\\n'
 assert write_text(str(p),'replacement') is None
 assert read_text(p)=='replacement'
 assert write_text(p,'\\n追加',append=True) is None
 assert read_text(p)=='replacement\\n追加'
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
'''

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--tokenizer-revision',required=True);p.add_argument('--timeout',type=float,default=180)
 raise SystemExit(main(p.parse_args(),dict(primary_file='file_io.py',files={'file_io.py':''},prompt=PROMPT,check=CHECK)))
