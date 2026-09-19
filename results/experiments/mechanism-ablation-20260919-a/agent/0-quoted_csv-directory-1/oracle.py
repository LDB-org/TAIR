import os, sys
sys.path.insert(0, os.getcwd())
import csv,io
from app import parse_people
rows=[['Doe, Jane','31','yes'],['He said "Hi"','-2','no'],['Multi'+chr(10)+'line','7','YES'],['  spaced  ','0','yes']]
s=io.StringIO(); writer=csv.writer(s);writer.writerow(['name','age','active']);writer.writerows(rows)
assert parse_people(s.getvalue())==[{'name':r[0],'age':int(r[1]),'active':r[2]=='yes'} for r in rows]
assert parse_people('name,age,active\n\n')==[]
try: parse_people('name,age,active\nAlice,invalid,yes\n')
except ValueError: pass
else: raise AssertionError('invalid age swallowed')

from pathlib import Path

import subprocess,sys
r=subprocess.run([sys.executable,'-B','-m','unittest','-v'],capture_output=True,text=True,timeout=10)
assert r.returncode==0,(r.stdout,r.stderr)
