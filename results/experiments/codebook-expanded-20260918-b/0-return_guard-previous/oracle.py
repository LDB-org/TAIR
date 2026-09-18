import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import app
assert app.safe_divide(7,0)==0
assert app.safe_divide(9,3)==3
