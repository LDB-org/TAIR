import os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
assert not Path('must-not-exist.txt').exists()
assert not Path('must-not-run.txt').exists()