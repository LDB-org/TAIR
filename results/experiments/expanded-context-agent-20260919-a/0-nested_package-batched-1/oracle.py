import os, sys
sys.path.insert(0, os.getcwd())
from app import moving_average
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

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
