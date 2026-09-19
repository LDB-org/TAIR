import json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
out=Path(sys.argv[1]).resolve()
rows=[json.loads(x) for x in (out/'rows.jsonl').read_text().splitlines()]
results=[]
audit_env=dict(os.environ,PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH',''))
utility='''import io,json,unittest,test_app,textutil
real=textutil.slugify
bad=lambda text:'__BROKEN_UTILITY__'
for k,v in list(vars(test_app).items()):
 if v is real:setattr(test_app,k,bad)
textutil.slugify=bad
result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(test_app))
print('TAIR_TEST_REVIEW='+json.dumps({'caught':not result.wasSuccessful(),'failed_tests':[str(t) for t,_ in result.failures+result.errors]}))
'''
for row in rows:
 if row['case']!='multifile_feature' or not row['passed']:continue
 case=f"{row['repeat']}-{row['case']}-{row['arm']}-{row['round']}"
 with tempfile.TemporaryDirectory(prefix='tair-cli-test-audit-') as temp:
  project=Path(temp)/'project';shutil.copytree(out/case/'project-after',project)
  command=[sys.executable,'-B','-m','unittest','-v']
  original=subprocess.run(command,cwd=project,env=audit_env,capture_output=True,text=True,timeout=20)
  checked={'case':case,'base_passed':True,'original_suite_passed':original.returncode==0,'original_stderr':original.stderr}
  stdout=subprocess.check_output([sys.executable,'-B','-c',utility],cwd=project,env=audit_env,text=True,timeout=20)
  checked['utility']=json.loads(next(line.split('=',1)[1] for line in reversed(stdout.splitlines()) if line.startswith('TAIR_TEST_REVIEW=')))
  source=(project/'app.py').read_text();(project/'_probe_original_app.py').write_text(source)
  for mode,slug in [('echo',False),('slug',True)]:
   (project/'app.py').write_text("import sys\nfrom _probe_original_app import *\nimport _probe_original_app as original\ndef main(*args,**kwargs):\n    argv=args[0] if args else kwargs.get('argv')\n    if argv is None:argv=sys.argv[1:]\n    if ('--slug' in argv)=="+str(slug)+":\n        print('__BROKEN_CLI__')\n        return None\n    return original.main(*args,**kwargs)\nif __name__=='__main__':main()\n")
   result=subprocess.run(command,cwd=project,env=audit_env,capture_output=True,text=True,timeout=20)
   checked[mode]={'caught':result.returncode!=0,'stderr':result.stderr}
  checked['requested_tests_effective']=checked['original_suite_passed'] and all(checked[k]['caught'] for k in ['utility','echo','slug'])
  results.append(checked)
(out/'cli-test-review.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'reviewed':len(results),'all_effective':all(r['requested_tests_effective'] for r in results),'failed':[r['case'] for r in results if not r['requested_tests_effective']]}))
