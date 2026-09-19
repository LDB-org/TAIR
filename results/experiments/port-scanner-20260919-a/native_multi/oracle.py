import os, sys
sys.path.insert(0, os.getcwd())
import json, math, socket, subprocess, sys
from pathlib import Path
from contextlib import ExitStack
assert Path('scanner.py').stat().st_size > 0
assert Path('README.md').is_file()
assert list(Path('.').rglob('test*.py')), 'No delivered tests'
def run(*args):
 return subprocess.run([sys.executable,'-B','scanner.py',*args],capture_output=True,text=True,timeout=5)
base=['--host','127.0.0.1']
for spec in ['', '0', '65536', '5-3', '1,,2', 'abc', '1-', '-1', '1-2-3']:
 p=run(*base,'--ports',spec);assert p.returncode==2,(spec,p.returncode,p.stderr)
for option,values in [('--timeout',['0','-1','nan','inf']),('--workers',['0','257','x'])]:
 for value in values:
  p=run(*base,'--ports','12345',option,value);assert p.returncode==2,(option,value,p.returncode)
for host in ['999.0.0.1','localhost','::1','127.0.0.0/8']:
 p=run('--host',host,'--ports','12345');assert p.returncode==2,(host,p.returncode)
p=run('--help');assert p.returncode==0 and '--ports' in p.stdout
p=subprocess.run([sys.executable,'-B','-c','import scanner; print("import-ok")'],capture_output=True,text=True,timeout=3)
assert p.returncode==0 and p.stdout.strip()=='import-ok',(p.stdout,p.stderr)
with ExitStack() as stack:
 opened=[]
 for _ in range(2):
  sock=stack.enter_context(socket.socket());sock.bind(('127.0.0.1',0));sock.listen(32);opened.append(sock.getsockname()[1])
 closed=stack.enter_context(socket.socket());closed.bind(('127.0.0.1',0));closed_port=closed.getsockname()[1]
 for workers in ['1','4']:
  spec=f' {opened[1]}, {closed_port},{opened[0]},{opened[1]} '
  p=run(*base,'--ports',spec,'--timeout','.15','--workers',workers,'--json')
  assert p.returncode==0,(p.stdout,p.stderr)
  assert json.loads(p.stdout)==dict(host='127.0.0.1',open_ports=sorted(opened)),p.stdout
 p=run(*base,'--ports',str(closed_port),'--json');assert p.returncode==0 and json.loads(p.stdout)['open_ports']==[]
 p=run(*base,'--ports',str(opened[0]));assert p.returncode==0 and str(opened[0]) in p.stdout
 # Reserve an adjacent loopback pair: listener followed by bound but non-listening port.
 for _ in range(50):
  left=socket.socket();left.bind(('127.0.0.1',0));port=left.getsockname()[1]
  right=socket.socket()
  try:right.bind(('127.0.0.1',port+1))
  except (OSError,OverflowError):left.close();right.close();continue
  stack.enter_context(left);stack.enter_context(right);left.listen(8);break
 else:raise AssertionError('Cannot reserve adjacent test ports')
 p=run(*base,'--ports',f'{port}-{port+1},{port}','--json')
 assert p.returncode==0 and json.loads(p.stdout)==dict(host='127.0.0.1',open_ports=[port]),(p.stdout,p.stderr)
print('Independent loopback CLI checks passed')
