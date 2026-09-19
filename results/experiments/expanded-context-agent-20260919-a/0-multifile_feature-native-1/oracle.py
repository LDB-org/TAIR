import os, sys
sys.path.insert(0, os.getcwd())
import subprocess,sys
from pathlib import Path
from textutil import slugify
for text,expected in [('  Hello   WORLD ','hello-world'),('A\tB\nC','a-b-c'),('   ',''),('Keep_This','keep_this')]:
 assert slugify(text)==expected
for flags,expected in [([], '  Hello World  \n'),(['--slug'],'hello-world\n')]:
 r=subprocess.run([sys.executable,'app.py',*flags,'  Hello World  '],capture_output=True,text=True,timeout=10)
 assert r.returncode==0 and r.stdout==expected,(r.stdout,r.stderr)
assert '--slug' in Path('README.md').read_text()
assert 'unittest' in Path('test_app.py').read_text()

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
