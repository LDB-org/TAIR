import os, sys
sys.path.insert(0, os.getcwd())
from app import settings
assert settings()=={'server': {'port': 9090, 'host': '127.0.0.1'}, 'retry': {'count': 4, 'backoff': 0.5}, 'features': ['metrics', 'tracing'], 'metadata': {'owner': 'example', 'revision': 7}}

from pathlib import Path
import hashlib
assert hashlib.sha256(Path('app.py').read_bytes()).hexdigest()=='4d3801816dd6d7ac204afdc2d190528aabbc45725cf16143cfd3555b801fcd7c'
import hashlib
assert hashlib.sha256(Path('docs/notes.md').read_bytes()).hexdigest()=='5f7ad52293a1e566fc21bf3f68b194854fd98a1e6d35d52d6fa4ec65d21b0f5d'

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
