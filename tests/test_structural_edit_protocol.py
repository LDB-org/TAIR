import importlib.util
import json
from pathlib import Path
import re
import pytest

spec=importlib.util.spec_from_file_location('structural',Path(__file__).parents[1]/'deploy/structural_edit_protocol.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def apply(source,edits):
 raw=json.dumps(edits,separators=(',',':'))
 assert re.fullmatch(m.grammar(source),raw)
 return m.decode(source,m.digest(source),raw,'stop')


def test_alias_inserts_without_reprinting_multiline_call():
 source='def f():\n    call(\n        "--port", # retain this\n        required=True,\n    )\n'
 assert apply(source,[['arg','C2_4','"-p"']])==source.replace('"--port"','\'-p\', "--port"')


@pytest.mark.parametrize('source',['x = call(1)\n','x = call(1,\n)\n','x = call(1, # trailing\n)\n','x = call(**options)\n','x = call()\n'])
def test_keyword_insert_handles_trailing_commas_comments_and_unpack(source):
 result=apply(source,[['kw','C1_4','enabled','True']])
 ns={'call':lambda *a,**kw:kw,'options':{}}
 exec(result,ns);assert ns['x']['enabled'] is True


def test_keyword_replacement_changes_only_expression_and_utf8_offsets():
 source='é = "保留"; x = call(enabled=False) # retain\n'
 key=next(k for k in m.catalogue(source) if k.startswith('C'))
 assert apply(source,[['kw',key,'enabled','True']])==source.replace('False','True')


@pytest.mark.parametrize('indent',['  ','    ','\t'])
def test_guard_preserves_docstring_and_source(indent):
 source='def f(x):\n'+indent+'"""doc\n  text unchanged\n"""\n'+indent+'return x + 1\n'
 result=apply(source,[['guard_return','F1_0','not x','0']])
 assert result==source.replace(indent+'return x + 1',indent+'if not x:\n'+indent*2+'return 0\n'+indent+'return x + 1')
 ns={};exec(result,ns);assert ns['f'](0)==0 and ns['f'](2)==3
 assert ns['f'].__doc__=='doc\n  text unchanged\n'


def test_catch_wraps_only_existing_statement_and_keeps_following_try():
 source='def f():\n    x = allocate() # keep\n    try:\n        return x\n    finally:\n        cleanup()\n'
 result=apply(source,[['catch_return','S2_4','OSError','False']])
 assert '    except OSError:\n        return False\n    try:' in result
 ns={'allocate':lambda:(_ for _ in ()).throw(OSError()),'cleanup':lambda:None};exec(result,ns)
 assert ns['f']() is False and '# keep' in result


def test_guard_raise():
 source='def f(x):\n    return x\n'
 result=apply(source,[['guard_raise','F1_0','x <= 0','ValueError("bad")']])
 ns={};exec(result,ns)
 with pytest.raises(ValueError,match='bad'):ns['f'](0)


@pytest.mark.parametrize('edit',[
 ['guard_return','F1_0','True','return 1'],['arg','F1_0','1'],
 ['kw','C2_11','bad-name','1'],['catch_return','S2_4','OSError','1\nraise Exception()'],
])
def test_rejects_bad_expression_or_target(edit):
 source='def f():\n    return call()\n'
 with pytest.raises((ValueError,SyntaxError)):
  m.decode(source,m.digest(source),json.dumps([edit]),'stop')


def test_snapshot_truncation_and_overlaps():
 source='def f():\n    return call()\n'
 raw=json.dumps([['arg','C2_11','1']])
 for version,finish in [('old','stop'),(m.digest(source),'length')]:
  with pytest.raises(ValueError):m.decode(source,version,raw,finish)
 with pytest.raises(ValueError,match='Overlapping'):
  m.decode(source,m.digest(source),json.dumps([['catch_return','S2_4','Exception','0'],['arg','C2_11','1']]),'stop')


def test_moving_multiline_string_is_rejected():
 source='def f():\n    x = """a\nb"""\n    return x\n'
 with pytest.raises(ValueError,match='multiline'):
  apply(source,[['catch_return','S2_4','Exception','0']])


def test_positional_insert_uses_source_order_before_keyword_and_starred_args():
 source='x = call(flag=True, *items)\n'
 result=apply(source,[['arg','C1_4','42']])
 assert result=='x = call(42, flag=True, *items)\n'
 ns={'call':lambda *a,**kw:a,'items':[7]};exec(result,ns)
 assert ns['x']==(42,7)
