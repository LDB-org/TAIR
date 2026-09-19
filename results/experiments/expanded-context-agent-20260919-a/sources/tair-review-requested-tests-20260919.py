import json,subprocess,sys
from pathlib import Path
out=Path(sys.argv[1]).resolve()
code='''import importlib.util,io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
spec=importlib.util.spec_from_file_location('review_test_app',Path('test_app.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
real=m.summarize
results={}
for mode in ['original','negative_total','input_mutation']:
 def altered(values):
  if mode=='input_mutation':values.sort()
  result=real(values)
  if mode=='negative_total' and any(v<0 for v in values):result={**result,'total':1234567}
  return result
 m.summarize=altered
 result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(m))
 results[mode]={'passed':result.wasSuccessful(),'failing_tests':[str(t) for t,_ in result.failures+result.errors]}
print(json.dumps(results))
'''
rows=[]
for project in sorted(out.glob('*summary_bug*/project-after')):
 result=json.loads(subprocess.check_output([sys.executable,'-B','-c',code],cwd=project,text=True))
 rows.append({'case':project.parent.name,'results':result,'requested_tests_effective':result['original']['passed'] and not result['negative_total']['passed'] and not result['input_mutation']['passed']})
(out/'requested-test-review.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'cases':len(rows),'all_effective':all(r['requested_tests_effective'] for r in rows),'failed':[r['case'] for r in rows if not r['requested_tests_effective']]}))
