import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from app import build_parser
p=build_parser()
assert p.parse_args([]).workers == 4
assert p.parse_args(["--workers", "7"]).workers == 7
assert len(p._actions) == 2
assert p.parse_args(["-w", "9"]).workers == 9
