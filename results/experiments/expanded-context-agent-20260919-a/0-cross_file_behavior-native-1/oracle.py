import os, sys
sys.path.insert(0, os.getcwd())
import copy
from app import render_users
from formatter import display_name
for u,expected in [({},'Unknown'),({'name':None},'Unknown'),({'name':'  '},'Unknown'),({'name':' 雪 '},'雪')]:
 before=copy.deepcopy(u);assert display_name(u)==expected;assert u==before
users=[{'name':'b'},{'name':'A'},{'name':'a'},{'name':' B '},{'other':3}]
before=copy.deepcopy(users)
assert render_users(users)=='A\na\nb\nB\nUnknown'
assert users==before
assert render_users([])==''

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
