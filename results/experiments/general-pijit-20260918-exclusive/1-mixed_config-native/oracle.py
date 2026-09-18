import os, sys
sys.path.insert(0, os.getcwd())
import app
p=app.build_parser()
a=p.parse_args([])
assert (a.workers,a.timeout,a.host)==(6,2.5,'localhost')
a=p.parse_args(['--workers','17','--timeout','0.75','--host','example'])
assert (a.workers,a.timeout,a.host)==(17,0.75,'example')
