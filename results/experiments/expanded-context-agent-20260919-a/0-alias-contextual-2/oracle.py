import os, sys
sys.path.insert(0, os.getcwd())
from app import build_parser
p=build_parser()
assert p.parse_args(['-w','13']).workers==13
assert p.parse_args(['--workers','17']).workers==17
assert p.parse_args([]).workers==4

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
