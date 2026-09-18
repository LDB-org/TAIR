import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('summary',Path(__file__).parents[1]/'benchmarks/summarize_region_holdout.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def write_fixture(root):
 (root/'manifest.json').write_text(json.dumps({'cases':['a'],'repeats':1}))
 rows=[]
 for arm,seconds,attempts in [('native',10,[True]),('hybrid',15,[False,True])]:
  rows.append({'case':'a','repeat':0,'arm':arm,'passed':True,'seconds':seconds,'usage_complete':True,
   'usage':{'prompt_tokens':100*len(attempts),'completion_tokens':10*len(attempts),'total_tokens':110*len(attempts)},
   'attempts':[{'passed':v,'metrics':{'queue_time_ms':1,'generation_time_ms':2}} for v in attempts]})
 (root/'rows.jsonl').write_text('\n'.join(map(json.dumps,rows)))
 return rows


def test_costs_include_failed_attempt_and_fallback(tmp_path):
 write_fixture(tmp_path);m.summarize(tmp_path)
 s=json.loads((tmp_path/'summary.json').read_text())
 assert s['hybrid']['fallbacks']==1 and s['hybrid']['first_attempt_passed']==0
 assert s['hybrid']['usage']['total_tokens']==220
 assert s['reductions']['wall_seconds']==-.5
 assert not s['screen_gate']


def test_incomplete_usage_cannot_be_treated_as_free_failure(tmp_path):
 rows=write_fixture(tmp_path);rows[1]['usage_complete']=False
 (tmp_path/'rows.jsonl').write_text('\n'.join(map(json.dumps,rows)))
 with pytest.raises(AssertionError,match='Missing usage'):m.summarize(tmp_path)
 assert not (tmp_path/'summary.json').exists()
