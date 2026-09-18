import ast,json,subprocess,sys,socket,unittest
from unittest.mock import patch,MagicMock
import port_scanner as m
case=sys.argv[1]
if case=='finite_timeout':
 for value in ['nan','inf','-inf','0','-0.1']:
  p=subprocess.run([sys.executable,'port_scanner.py','--host','127.0.0.1','--ports','1','--timeout='+value],capture_output=True,text=True,timeout=5)
  assert p.returncode==2,(value,p.returncode,p.stdout,p.stderr)
elif case=='range_step':
 for text,expected in [('20-26/2,80,20',[20,22,24,26,80]),('1-7/3',[1,4,7]),('80-80/2',[80]),('10-13/2,12-14',[10,12,13,14])]:
  assert m.parse_port_spec(text)==expected,(text,m.parse_port_spec(text))
 for text in ['1-5/0','1-5/-1','1-5/x','80/2','5-1/2','1-65536/2','1-5/2/3']:
  try:m.parse_port_spec(text)
  except ValueError:pass
  else:raise AssertionError(text)
elif case=='socket_context':
 tree=ast.parse(open('port_scanner.py').read()); fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='scan_port')
 assert any(isinstance(n,ast.With) for n in ast.walk(fn)),'Context manager missing'
 assert not any(isinstance(n,ast.Try) and n.finalbody for n in ast.walk(fn)),'Explicit finally remains'
 for outcome,expected in [(0,True),(111,False),(OSError('test'),False)]:
  sock=MagicMock();sock.__enter__.return_value=sock
  if isinstance(outcome,Exception):sock.connect_ex.side_effect=outcome
  else:sock.connect_ex.return_value=outcome
  with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',12345,.1) is expected
  sock.__exit__.assert_called_once();sock.settimeout.assert_called_once_with(.1)
p=subprocess.run([sys.executable,'-m','unittest','-v','test_port_scanner'],capture_output=True,text=True,timeout=25)
assert p.returncode==0,p.stdout+p.stderr
print(json.dumps({'status':'passed','case':case,'regression_output':p.stderr}))
