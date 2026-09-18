import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import app
p=app.build_parser()
a=next(a for a in p._actions if '--workers' in a.option_strings)
assert a.default == 11 and type(a.default) is int
assert len(p._actions)==6
assert app.checksum([65536,3])==3
parsed=p.parse_args(["--workers","9","--timeout","0.5","--host","explicit","--token","provided"])
assert (parsed.workers,parsed.timeout,parsed.host,parsed.token)==(9,0.5,"explicit","provided")
p=app.build_parser()
a=next(a for a in p._actions if '--timeout' in a.option_strings)
assert a.default == 3.125 and type(a.default) is float
assert len(p._actions)==6
assert app.checksum([65536,3])==3
parsed=p.parse_args(["--workers","9","--timeout","0.5","--host","explicit","--token","provided"])
assert (parsed.workers,parsed.timeout,parsed.host,parsed.token)==(9,0.5,"explicit","provided")
