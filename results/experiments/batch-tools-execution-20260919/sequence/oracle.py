import os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
assert Path('sequence.txt').read_text()=='first'