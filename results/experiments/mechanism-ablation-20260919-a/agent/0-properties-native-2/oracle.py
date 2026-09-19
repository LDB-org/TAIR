import os, sys
sys.path.insert(0, os.getcwd())
from app import build_parser
p=build_parser();a=p.parse_args(['--workers','7'])
assert (a.workers,a.timeout,a.host,a.verbose)==(7,2.5,'remote',True)
assert 'Worker count' in p.format_help()
assert next(a for a in p._actions if a.dest=='workers').required
b=p.parse_args(['--workers','8','--timeout','0.5','--host','elsewhere'])
assert (b.workers,b.timeout,b.host)==(8,0.5,'elsewhere')

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
