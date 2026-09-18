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
