import json,shutil,subprocess,sys,tempfile
from pathlib import Path
out=Path(sys.argv[1]).resolve()
rows=[json.loads(x) for x in (out/'rows.jsonl').read_text().splitlines()]
results=[]
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
  original=subprocess.run(command,cwd=project,capture_output=True,text=True,timeout=20)
  checked={'case':case,'base_passed':True,'original_suite_passed':original.returncode==0}
  stdout=subprocess.check_output([sys.executable,'-B','-c',utility],cwd=project,text=True,timeout=20)
  checked['utility']=json.loads(next(line.split('=',1)[1] for line in reversed(stdout.splitlines()) if line.startswith('TAIR_TEST_REVIEW=')))
  source=(project/'app.py').read_text();(project/'_probe_original_app.py').write_text(source)
  for mode,slug in [('echo',False),('slug',True)]:
   (project/'app.py').write_text("import runpy,sys\nif __name__=='__main__':\n    if ('--slug' in sys.argv)=="+str(slug)+":\n        print('__BROKEN_CLI__')\n    else:\n        runpy.run_path('_probe_original_app.py',run_name='__main__')\nelse:\n    from _probe_original_app import *\n")
   result=subprocess.run(command,cwd=project,capture_output=True,text=True,timeout=20)
   checked[mode]={'caught':result.returncode!=0,'stderr':result.stderr}
  checked['requested_tests_effective']=checked['original_suite_passed'] and all(checked[k]['caught'] for k in ['utility','echo','slug'])
  results.append(checked)
(out/'cli-test-review.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'reviewed':len(results),'all_effective':all(r['requested_tests_effective'] for r in results),'failed':[r['case'] for r in results if not r['requested_tests_effective']]}))
