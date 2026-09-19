import sys
sys.path.insert(0,'.')
import app
p=app.build_parser()
n=p.parse_args([])
assert n.workers==8 and n.timeout==5
n=p.parse_args(['--workers','23','--timeout','29'])
assert n.workers==23 and n.timeout==29
opt=next(a for a in p._actions if '--timeout' in a.option_strings)
assert opt.help=='timeout'
