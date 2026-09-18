import importlib.util
import json
from pathlib import Path
import re
import pytest

spec=importlib.util.spec_from_file_location('compact',Path(__file__).parents[1]/'deploy/compact_structural_protocol.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def run(source,edits):
 raw=json.dumps(edits,separators=(',',':'))
 assert re.fullmatch(m.grammar(source),raw)
 return m.decode(source,m.base.digest(source),raw,'stop')


def test_keyword_slot_prevents_outer_print_and_wrong_alias_keyword():
 source='import json\ndef f(parser, data):\n    parser.add_argument("--host", required=True)\n    print(json.dumps(data))\n'
 for edit in [['kw','print','separators',"(',', ':')"],['kw','--host','option_strings',"['-H']"]]:
  raw=json.dumps([edit],separators=(',',':'))
  assert re.fullmatch(m.grammar(source),raw) is None
  with pytest.raises(ValueError,match='keyword'):m.decode(source,m.base.digest(source),raw,'stop')
 updated=run(source,[['arg','--host',"'-H'"],['kw','json.dumps','separators',"(',', ':')"]])
 assert "'-H', \"--host\"" in updated and "json.dumps(data, separators=(',', ':'))" in updated


def test_compact_guard_and_catch_keep_original_code():
 source='def f(x):\n    value = allocate(x)\n    return value\n'
 result=run(source,[['guard_return','f','not x','0']])
 assert 'if not x:\n        return 0\n    value = allocate(x)' in result
 result=run(source,[['catch_return','value','OSError','False']])
 assert 'except OSError:\n        return False\n    return value' in result


def test_duplicate_names_are_disambiguated():
 source='a = f()\nb = f()\n'
 assert set(m.selectors(source)['C'])=={'f','f@2_4'}
 assert run(source,[['arg','f@2_4','2']])=='a = f()\nb = f(2)\n'


def test_invalid_exception_and_stale_frames_rejected():
 source='def f():\n    return 1\n'
 raw=json.dumps([['guard_raise','f','True','False']])
 with pytest.raises(ValueError,match='exception'):m.decode(source,m.base.digest(source),raw,'stop')
 for version,finish in [('old','stop'),(m.base.digest(source),'length')]:
  with pytest.raises(ValueError):m.decode(source,version,raw,finish)


def test_existing_keyword_is_available_for_unknown_callee():
 source='x = custom(size=3)\n'
 assert run(source,[['kw','custom','size','5']])=='x = custom(size=5)\n'
 raw=json.dumps([['kw','custom','unknown','5']],separators=(',',':'))
 assert re.fullmatch(m.grammar(source),raw) is None


def test_no_duplicate_positional_keyword_for_known_signature():
 source='x = json.dumps(data)\n'
 raw=json.dumps([['kw','json.dumps','obj','data']],separators=(',',':'))
 assert re.fullmatch(m.grammar(source),raw) is None


def test_typed_values_generate_literal_arguments_and_keyword_values():
 source='import json\ndef f(parser, data):\n    parser.add_argument("--host", required=True)\n    print(json.dumps(data))\n'
 edits=[['arg','--host','-H'],['kw','json.dumps','separators',[',',':']]]
 raw=json.dumps(edits,separators=(',',':'))
 result=m.typed_decode(source,m.base.digest(source),raw,'stop')
 assert "'-H', \"--host\"" in result
 assert "separators=[',', ':']" in result


def test_typed_grammar_rejects_string_for_boolean_and_separator_expression():
 source='x=json.dumps(data, ensure_ascii=True)\n'
 for edit in [['kw','json.dumps','ensure_ascii','False'],['kw','json.dumps','separators',"(',', ':')"],['kw','json.dumps','separators',[',']]]:
  raw=json.dumps([edit],separators=(',',':'))
  assert re.fullmatch(m.typed_grammar(source),raw) is None
  with pytest.raises(ValueError):m.typed_decode(source,m.base.digest(source),raw,'stop')


def test_typed_catch_and_raise_construct_exceptions_and_return_literals():
 source='def f(x):\n    value = allocate(x)\n    return value\n'
 raw=json.dumps([['catch','value','OSError',False]],separators=(',',':'))
 result=m.typed_decode(source,m.base.digest(source),raw,'stop')
 assert 'except OSError:\n        return False' in result
 raw=json.dumps([['raise_if','f','x < 0','ValueError','bad input']],separators=(',',':'))
 result=m.typed_decode(source,m.base.digest(source),raw,'stop')
 ns={};exec(result,ns)
 with pytest.raises(ValueError,match='bad input'):ns['f'](-1)


def test_typed_guard_result_preserves_tuple_expression():
 source='def f(x):\n    return x\n'
 raw=json.dumps([['return_if','f','not x','([], [])']],separators=(',',':'))
 result=m.typed_decode(source,m.base.digest(source),raw,'stop')
 ns={};exec(result,ns);assert ns['f']([])==([],[])


def test_typed_nonfinite_numeric_overflow_rejected():
 source='x=call(timeout=1.0)\n'
 with pytest.raises(ValueError,match='Nonfinite'):
  m.typed_decode(source,m.base.digest(source),'[["kw","call","timeout",1e999]]','stop')


def test_scope_retrieves_callee_and_owner_without_irrelevant_print():
 source='import json\ndef main(data):\n    print(json.dumps(data))\ndef other():\n    print("x")\n'
 allowed=m.task_scope(source,'Make main JSON serialization compact.')
 aliases=m.scoped_selectors(source,allowed)
 assert set(aliases['C'])=={'json.dumps'} and set(aliases['F'])=={'main'}
 raw=json.dumps([['kw','print','end','']],separators=(',',':'))
 with pytest.raises(ValueError):m.typed_decode(source,m.base.digest(source),raw,'stop',allowed)


def test_scope_uses_generic_names_and_literal_arguments():
 source='def configure(builder):\n    builder.add("--alpha", default=1)\n    builder.add("--beta", default=2)\n'
 allowed=m.task_scope(source,'Set --beta default to 4.')
 assert set(m.scoped_selectors(source,allowed)['C'])=={'--beta'}
 source='def acquire():\n    resource = factory.make()\n    return resource\n'
 allowed=m.task_scope(source,'In acquire, catch failures from factory.make.')
 aliases=m.scoped_selectors(source,allowed)
 assert 'resource' in aliases['S'] and 'acquire' in aliases['F']


def test_scope_without_lexical_evidence_keeps_all_candidates():
 source='def f():\n    return call()\n'
 assert m.task_scope(source,'Improve things carefully')==set(m.base.catalogue(source))
