import json,sys,subprocess,unittest,socket,io,contextlib
from unittest.mock import patch,MagicMock
sys.path.insert(0,'.')
import port_scanner as m
case=sys.argv[1]
if case=='json_no_nan':
 stream=io.StringIO()
 with patch.object(m,'scan_ports',return_value=([float('nan')],[])),contextlib.redirect_stdout(stream):
  try:m.main(['--host','127.0.0.1','--ports','80'])
  except ValueError:pass
  else:raise AssertionError('nonstandard NaN JSON accepted')
 assert stream.getvalue()==''
elif case=='guard_port_bounds':
 for port in [0,-1,65536]:
  with patch.object(m.socket,'socket') as create:
   try:m.scan_port('127.0.0.1',port,.1)
   except ValueError:pass
   else:raise AssertionError(port)
   create.assert_not_called()
 for port in [1,65535]:
  sock=MagicMock();sock.connect_ex.return_value=0
  with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',port,.1) is True
  sock.close.assert_called_once()
elif case=='guard_empty_host':
 with patch.object(m.socket,'socket') as create:
  try:m.scan_port('',80,.1)
  except ValueError:pass
  else:raise AssertionError('empty host accepted')
  create.assert_not_called()
 sock=MagicMock();sock.connect_ex.return_value=0
 with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',80,.1) is True
 sock.close.assert_called_once()
elif case=='json_unicode':
 stream=io.StringIO()
 with patch.object(m,'scan_ports',return_value=([80],[])),contextlib.redirect_stdout(stream):
  assert m.main(['--host','测试.example','--ports','80'])==0
 expected={'host':'测试.example','open_ports':[80],'closed_ports':[]}
 assert stream.getvalue()==json.dumps(expected,sort_keys=True,ensure_ascii=False)+'\n',repr(stream.getvalue())
elif case=='default_workers_six':
 parser=m.build_parser()
 assert parser.parse_args(['--host','127.0.0.1','--ports','80']).workers==14
 assert parser.parse_args(['--host','127.0.0.1','--ports','80','--workers','3']).workers==3
elif case=='timeout_upper_guard':
 for timeout in [60.01,100]:
  with patch.object(m.socket,'socket') as create:
   try:m.scan_port('127.0.0.1',80,timeout)
   except ValueError:pass
   else:raise AssertionError(timeout)
   create.assert_not_called()
 for timeout in [.1,60]:
  sock=MagicMock();sock.connect_ex.return_value=0
  with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',80,timeout) is True
  sock.close.assert_called_once()
elif case=='pool_cap':
 original=m.ThreadPoolExecutor
 for workers,expected in [(100,2),(1,1)]:
  with patch.object(m,'ThreadPoolExecutor',wraps=original) as pool,patch.object(m,'scan_port',return_value=False):
   assert m.scan_ports('127.0.0.1',[80,81],.1,workers)==([],[80,81])
   pool.assert_called_once_with(max_workers=expected)
elif case=='socket_timeout_guard':
 for timeout in [0,-.1,-100]:
  with patch.object(m.socket,'socket') as create:
   try:m.scan_port('127.0.0.1',80,timeout)
   except ValueError:pass
   else:raise AssertionError(timeout)
   create.assert_not_called()
 sock=MagicMock();sock.connect_ex.return_value=0
 with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',80,.1) is True
 sock.close.assert_called_once()
elif case=='short_flags':
 p=m.build_parser()
 for flags in [['-H','127.0.0.1','-p','80','-t','.2','-w','3'],['--host','127.0.0.1','--ports','80','--timeout','.2','--workers','3']]:
  a=p.parse_args(flags);assert (a.host,a.ports,a.timeout,a.workers)==('127.0.0.1','80',.2,3)
elif case=='compact_json':
 stream=io.StringIO()
 with patch.object(m,'scan_ports',return_value=([80],[81])),contextlib.redirect_stdout(stream):
  assert m.main(['--host','127.0.0.1','--ports','80,81'])==0
 value={'host':'127.0.0.1','open_ports':[80],'closed_ports':[81]}
 assert stream.getvalue()==json.dumps(value,sort_keys=True,separators=(',',':'))+'\n',repr(stream.getvalue())
elif case=='empty_scan':
 with patch.object(m.socket,'getaddrinfo',side_effect=AssertionError('DNS must not run')),patch.object(m,'ThreadPoolExecutor',side_effect=AssertionError('pool must not run')):
  assert m.scan_ports('invalid',[],.1,1)==([],[])
  assert m.scan_ports('invalid',(),.1,1)==([],[])
elif case=='unique_scan':
 with patch.object(m,'scan_port',side_effect=lambda host,port,timeout:port==80) as scan:
  assert m.scan_ports('127.0.0.1',[81,80,81,80],.1,2)==([80],[81])
  assert scan.call_count==2,scan.call_count
elif case=='socket_creation':
 with patch.object(m.socket,'socket',side_effect=OSError('allocation failed')):
  assert m.scan_port('127.0.0.1',80,.1) is False
 for result in [0,111]:
  sock=MagicMock();sock.connect_ex.return_value=result
  with patch.object(m.socket,'socket',return_value=sock):assert m.scan_port('127.0.0.1',80,.1) is (result==0)
  sock.close.assert_called_once()
elif case=='exact_flags':
 for flag,value in [('--hos','127.0.0.1'),('--por','1'),('--time','.1'),('--work','1')]:
  with contextlib.redirect_stderr(io.StringIO()):
   try:m.build_parser().parse_args(['--host','127.0.0.1','--ports','1',flag,value])
   except SystemExit as e:assert e.code==2
   else:raise AssertionError(flag)
p=subprocess.run([sys.executable,'-m','unittest','-v','test_port_scanner'],capture_output=True,text=True,timeout=25)
assert p.returncode==0,p.stdout+p.stderr
print(json.dumps({'passed':True,'regression':p.stderr}))
