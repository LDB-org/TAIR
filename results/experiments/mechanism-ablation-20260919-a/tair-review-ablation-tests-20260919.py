import json,subprocess,sys
from pathlib import Path
out=Path(sys.argv[1]).resolve()
code='''import importlib.util,io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import app
spec=importlib.util.spec_from_file_location('review_test_app',Path('test_app.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
real=app.summarize
aliases=[k for k,v in vars(m).items() if v is real]
results={}
for mode in ['original','negative_total','input_mutation']:
 def altered(values):
  if mode=='input_mutation':values.sort()
  result=real(values)
  if mode=='negative_total' and any(v<0 for v in values):result={**result,'total':1234567}
  return result
 app.summarize=altered
 for k in aliases:setattr(m,k,altered)
 result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(m))
 results[mode]={'passed':result.wasSuccessful(),'failing_tests':[str(t) for t,_ in result.failures+result.errors]}
print('TAIR_TEST_REVIEW='+json.dumps(results))
'''
rows=[]
for project in sorted(out.glob('*summary_bug*/project-after')):
 p=subprocess.run([sys.executable,'-B','-c',code],cwd=project,capture_output=True,text=True,timeout=20)
 result=None
 for line in p.stdout.splitlines():
  if line.startswith('TAIR_TEST_REVIEW='):result=json.loads(line.split('=',1)[1])
 effective=(result['original']['passed'] and not result['negative_total']['passed'] and not result['input_mutation']['passed']) if result else None
 rows.append({'case':project.parent.name,'results':result,'requested_tests_effective':effective,'stdout':p.stdout,'stderr':p.stderr,'returncode':p.returncode})
(out/'requested-test-review.json').write_text(json.dumps(rows,indent=2))
print(json.dumps({'cases':len(rows),'all_effective':all(r['requested_tests_effective'] is True for r in rows),'failed':[r['case'] for r in rows if r['requested_tests_effective'] is not True]}))
