import os, sys
sys.path.insert(0, os.getcwd())
import json,tempfile
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

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
