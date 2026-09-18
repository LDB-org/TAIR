import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import app
assert app.connect(2)==4
try:
 app.connect(0)
except ValueError as e:
 assert str(e)=="too small"
else:
 raise AssertionError("missing exception")
