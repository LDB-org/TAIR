import importlib.util
import json
from pathlib import Path
import re
import pytest

spec=importlib.util.spec_from_file_location('applicable',Path(__file__).parents[1]/'deploy/applicable_structural_protocol.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def raw(edit):return json.dumps([edit],separators=(',',':'))


def test_uninitialized_local_and_comprehension_cannot_be_generated():
 source='def render(record):\n    later = list(record)\n    return later\n'
 for condition in ['not later','any(x for x in later)','record.value','record = 1']:
  text=raw(['return_if','render',condition,'None'])
  assert re.fullmatch(m.grammar(source),text) is None
  with pytest.raises(ValueError):m.decode(source,m.m.base.digest(source),text,'stop')


def test_valid_parameter_conditions_and_tuple_return():
 source='def work(items, workers):\n    return list(items), workers\n'
 for condition in ['not items','workers <= 0','not 1 <= workers <= 16','workers < 1 or workers > 16']:
  text=raw(['return_if','work',condition,'([], 0)'])
  assert re.fullmatch(m.grammar(source),text)
  compile(m.decode(source,m.m.base.digest(source),text,'stop'),'<test>','exec')


def test_json_separator_domain_enforced_before_decode():
 source='def render(data):\n    return json.dumps(data)\n'
 for separators in [[',',':'],[', ',': ']]:
  text=raw(['kw','json.dumps','separators',separators])
  assert re.fullmatch(m.grammar(source),text)
 for separators in [['',': '],[';',':'],[',','=']]:
  text=raw(['kw','json.dumps','separators',separators])
  assert re.fullmatch(m.grammar(source),text) is None


def test_unsupported_anchors_and_top_level_catch_removed():
 source='resource = allocate()\ndef f():\n    "doc only"\n'
 pattern=m.grammar(source)
 assert re.fullmatch(pattern,raw(['catch','resource','OSError',None])) is None
 assert re.fullmatch(pattern,raw(['return_if','f','True','None'])) is None
 assert re.fullmatch(pattern,'["native"]')


def test_results_cannot_reference_later_bindings_or_execute_calls():
 source='def f(x):\n    later = 2\n    return x\n'
 for result in ['later','len(x)','x + 1','(y for y in x)']:
  assert re.fullmatch(m.grammar(source),raw(['return_if','f','not x',result])) is None


def test_valid_string_literal_and_keyword_only_parameters():
 source='def f(*, label):\n    return label\n'
 text=raw(['raise_if','f',"label == ''",'ValueError','empty'])
 updated=m.decode(source,m.m.base.digest(source),text,'stop')
 ns={};exec(updated,ns)
 with pytest.raises(ValueError):ns['f'](label='')


def test_version_and_incomplete_output_still_rejected():
 source='def f(x):\n    return x\n';text=raw(['return_if','f','not x','None'])
 for version,finish in [('old','stop'),(m.m.base.digest(source),'length')]:
  with pytest.raises(ValueError):m.decode(source,version,text,finish)
