import json,sys,subprocess
sys.path.insert(0,'.')
import port_scanner as m
case=sys.argv[1]
if case=='compact_record':
 for value in [{'b':[1,2],'a':'x'},{}]:assert m.encode_record(value)==json.dumps(value,sort_keys=True,separators=(',',':'))
elif case=='finite_record':
 for value in [float('nan'),float('inf'),-float('inf')]:
  try:m.encode_record({'value':value})
  except ValueError:pass
  else:raise AssertionError('nonstandard float accepted')
 assert json.loads(m.encode_record({'value':1.5}))=={'value':1.5}
elif case=='score_range':
 for value in [-1,101,-.01,100.01]:
  try:m.normalize_score(value)
  except ValueError:pass
  else:raise AssertionError(value)
 for value in [0,1,50,100]:assert m.normalize_score(value)==value/100
elif case=='empty_jobs':
 assert m.schedule_jobs([],4)==([],0)
 assert m.schedule_jobs((),2)==([],0)
 assert m.schedule_jobs([3,1],4)==([3,1],4)
elif case=='retry_alias':
 for flag in ['-r','--retries']:assert m.build_parser().parse_args([flag,'5']).retries==5
 assert m.build_parser().parse_args([]).retries==2
elif case=='missing_resource':
 def missing(key):raise LookupError(key)
 assert m.read_resource(missing,'absent') is None
 def other(key):raise RuntimeError(key)
 try:m.read_resource(other,'error')
 except RuntimeError:pass
 else:raise AssertionError('unrelated exception swallowed')
 assert m.read_resource(lambda key:key+'!', 'found')=='found!'
elif case=='new_divisor':
 for value in [-125,-1,0,1,13,50,99,100,2000]:assert m.normalize_score(value)==value/200,(value,m.normalize_score(value))
p=subprocess.run([sys.executable,'-m','unittest','-v','test_port_scanner'],capture_output=True,text=True,timeout=25)
assert p.returncode==0,p.stdout+p.stderr
print(json.dumps({'passed':True,'regression':p.stderr}))
