import importlib.util
from pathlib import Path
import pytest
import json
import re

spec = importlib.util.spec_from_file_location('region', Path(__file__).parents[1] / 'deploy/region_edit_protocol.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_version_and_frame_rejection():
    source = 'def f():\n    return 1\n'
    regions = m.catalogue(source)
    key = next(k for k, r in regions.items() if r['start'] == r['end'] == 2)
    frame = key + '\n    return 2'
    assert m.decode(source, m.digest(source), regions, frame, 'stop') == 'def f():\n    return 2\n'
    for text, version, raw, finish in [(source+'\n', m.digest(source), frame, 'stop'),
                                       (source, m.digest(source), 'INVALID\nx', 'stop'),
                                       (source, m.digest(source), frame, 'length')]:
        with pytest.raises(ValueError):
            m.decode(text, version, regions, raw, finish)


def test_embedded_protocol_text_remains_content():
    source = 'value = 1\n'
    regions = m.catalogue(source)
    raw = 'R0\nvalue = """R1\nhello"""\n'
    assert m.decode(source, m.digest(source), regions, raw, 'stop') == raw.partition('\n')[2]


def test_readable_regions_and_runtime_indentation():
    source = 'def f(x):\n    if x:\n        return 1\n    return 0\n'
    regions = m.catalogue(source, readable=True)
    output = m.decode(source,m.digest(source),regions,'B2_3\nif not x:\n    return 2','stop',relative_indent=True)
    assert output == 'def f(x):\n    if not x:\n        return 2\n    return 0\n'
    assert m.decode(source,m.digest(source),regions,'L4\nreturn 3','stop',relative_indent=True).endswith('    return 3\n')
    with pytest.raises(ValueError):
        m.decode(source,m.digest(source),regions,'L4\n    return 3','stop',relative_indent=True)


def test_batch_uses_original_offsets_and_restores_indentation():
    source = 'def f():\n    x = 1\n    y = 2\n    return x+y\n'
    regions = m.catalogue(source, readable=True)
    raw = json.dumps([['L3','y = 4'], ['L2','x = 3\nz = "[L4]"']], separators=(',', ':'))
    assert re.fullmatch(m.multi_regex(regions),raw)
    assert m.decode_multi(source,m.digest(source),regions,raw,'stop') == 'def f():\n    x = 3\n    z = "[L4]"\n    y = 4\n    return x+y\n'


@pytest.mark.parametrize('edits', [[], [['L2','x = 2'],['L2','x = 3']],
    [['B1_3','def f():\n    return 2'],['L2','x = 3']], [['L2','x = 3'],['L99','oops']],
    [['L2',3]], [['L2','x = (']]])
def test_invalid_batch_never_returns_partial_result(edits):
    source='def f():\n    x = 1\n    return x\n'
    with pytest.raises((ValueError,SyntaxError)):
        m.decode_multi(source,m.digest(source),m.catalogue(source,True),json.dumps(edits),'stop')
    assert source=='def f():\n    x = 1\n    return x\n'


def test_batch_rejects_stale_version_and_truncation():
    source='a = 1\nb = 2\n';regions=m.catalogue(source,True)
    raw='[["L1","a = 3"],["L2","b = 4"]]'
    for text, finish in [(source+'\n','stop'),(source,'length')]:
        with pytest.raises(ValueError):
            m.decode_multi(text,m.digest(source),regions,raw,finish)


def test_batch_deletion_and_limit():
    source='def f():\n    unused = 1\n    return 0\n';regions=m.catalogue(source,True)
    raw='[["L2",""],["L3","return 42"]]'
    assert m.decode_multi(source,m.digest(source),regions,raw,'stop')=='def f():\n    return 42\n'
    assert re.fullmatch(m.multi_regex(regions,False),raw)
    assert re.fullmatch(m.multi_regex(regions,False),'L3\nreturn 42') is None
    source='x = 0\n'*10;regions=m.catalogue(source,True)
    raw=json.dumps([[f'L{i}','x = 1'] for i in range(1,10)],separators=(',',':'))
    assert re.fullmatch(m.multi_regex(regions,False),raw) is None
    with pytest.raises(ValueError):
        m.decode_multi(source,m.digest(source),regions,raw,'stop')


def test_grammar_rejects_base_indentation_before_generation():
    regions=m.catalogue('x = 1\n',True)
    pattern=m.multi_regex(regions,False)
    for value in [' x = 2','\tx = 2','\nx = 2']:
        assert re.fullmatch(pattern,json.dumps([['L1',value]],separators=(',',':'))) is None
    for value in ['', 'x = 2', 'x = "quoted"', '# comment\nx = 2']:
        assert re.fullmatch(pattern,json.dumps([['L1',value]],separators=(',',':')))
    assert re.fullmatch(pattern,'[["L1","\x00invalid"]]') is None


def apply_lines(source, edits):
    regions=m.statement_catalogue(source)
    raw=json.dumps(edits,ensure_ascii=False,separators=(',',':'))
    assert re.fullmatch(m.line_regex(regions),raw)
    return m.decode_lines(source,m.digest(source),regions,raw,'stop')


def test_explicit_depth_wraps_statement_without_duplicating_next_try():
    source='def f():\n    sock = create()\n    try:\n        return sock\n    finally:\n        close(sock)\n'
    result=apply_lines(source,[['L2',[[0,'try:'],[1,'sock = create()'],[0,'except OSError:'],[1,'return False']]]])
    assert result=='def f():\n    try:\n        sock = create()\n    except OSError:\n        return False\n    try:\n        return sock\n    finally:\n        close(sock)\n'


def test_statement_boundaries_cover_full_call_and_decorators():
    source='@decorate\ndef f():\n    call(\n        "old",\n    )\n'
    regions=m.statement_catalogue(source)
    assert 'L3' not in regions and 'L4' not in regions and 'B1_5' in regions
    assert apply_lines(source,[['B3_5',[[0,'call("new")']]]])=='@decorate\ndef f():\n    call("new")\n'


@pytest.mark.parametrize('unit',['  ','    ','\t'])
def test_source_indentation_units_and_nested_suites(unit):
    source='def f():\n'+unit+'return 1\n'
    result=apply_lines(source,[['L2',[[0,'if True:'],[1,'return 2'],[0,'return 3']]]])
    assert result=='def f():\n'+unit+'if True:\n'+unit*2+'return 2\n'+unit+'return 3\n'


def test_literal_escaped_newline_and_spaces_are_preserved():
    source='def f():\n    return "old"\n'
    result=apply_lines(source,[['L2',[[0,r'return "  a\n  b"']]]])
    namespace={};exec(result,namespace)
    assert namespace['f']()=='  a\n  b'


@pytest.mark.parametrize('body',[
    [[True,'return 1']], [[17,'return 1']], [[-1,'return 1']],
    [[1,'return 1']], [[0,' return 1']], [[0,'return\n1']],
    [[0,'return\t1']], [[0,'return """a'],[0,'b"""']],
    [[0,'if True:'],[0,'return 1']], [[0,'if True:'],[1,'return 1'],[2,'return 2']],
])
def test_line_protocol_rejects_ambiguous_or_invalid_content(body):
    source='def f():\n    return 0\n';regions=m.statement_catalogue(source)
    with pytest.raises((ValueError,SyntaxError,m.tokenize.TokenError)):
        m.decode_lines(source,m.digest(source),regions,json.dumps([['L2',body]]),'stop')


def test_line_protocol_snapshot_overlap_and_deletion():
    source='def f():\n    x = 1\n    return 0\n';regions=m.statement_catalogue(source)
    assert apply_lines(source,[['L2',[]]])=='def f():\n    return 0\n'
    raw=json.dumps([['L2',[[0,'x = 3']]]])
    for version,finish,catalog in [('stale','stop',regions),(m.digest(source),'length',regions),(m.digest(source),'stop',{})]:
        with pytest.raises(ValueError):m.decode_lines(source,version,catalog,raw,finish)
    with pytest.raises(ValueError,match='overlapping'):
        m.decode_lines(source,m.digest(source),regions,json.dumps([['L2',[]],['B1_3',[[0,'def f():'],[1,'return 1']]]]),'stop')


def test_line_grammar_cannot_smuggle_whitespace_through_json_escapes():
    pattern=m.line_regex(m.statement_catalogue('x = 1\n'))
    for raw in [r'[["L1",[[0,"\u0020x=2"]]]]',r'[["L1",[[0,"x=2\n"]]]]',r'[["L1",[[0,"x=2\t"]]]]']:
        assert re.fullmatch(pattern,raw) is None


def test_mixed_indentation_is_rejected_instead_of_guessed():
    with pytest.raises(ValueError,match='Mixed'):
        m.indentation_unit('def f():\n  if True:\n      return 1\n')


def test_line_protocol_limits_are_enforced_by_grammar_and_runtime():
    source='x = 1\n';regions=m.statement_catalogue(source)
    for edits in [[['L1',[[0,'x = 2']]*257]], [['L1',[[0,'x = 2']]]]*9]:
        raw=json.dumps(edits,separators=(',',':'))
        assert re.fullmatch(m.line_regex(regions),raw) is None
        with pytest.raises(ValueError):m.decode_lines(source,m.digest(source),regions,raw,'stop')


def test_multiple_explicit_line_edits_keep_original_offsets():
    source='def f():\n    x = 1\n    return x\n'
    edits=[['L3',[[0,'return x + 1']]],['L2',[[0,'if True:'],[1,'x = 3'],[0,'else:'],[1,'x = 0']]]]
    result=apply_lines(source,edits)
    namespace={};exec(result,namespace)
    assert namespace['f']()==4
