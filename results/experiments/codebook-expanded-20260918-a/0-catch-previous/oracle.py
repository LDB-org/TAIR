import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import app
assert app.parse_count("bad")==-1
assert app.parse_count("19")==19
