import os, sys
sys.path.insert(0, os.getcwd())
from app import summarize
for xs in [[],[2,2,5],[-4,-2],[0.25,1.25,2.5],[9]]:
 before=list(xs)
 expected={'count':len(xs),'total':sum(xs),'mean':sum(xs)/len(xs) if xs else None,'min':min(xs) if xs else None,'max':max(xs) if xs else None}
 assert summarize(xs)==expected
 assert xs==before
from pathlib import Path
assert 'unittest' in Path('test_app.py').read_text()

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
