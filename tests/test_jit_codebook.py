import importlib.util
from pathlib import Path

s=importlib.util.spec_from_file_location('jit',Path(__file__).parents[1]/'deploy/jit_codebook.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def test_only_validated_supported_edits_enter_codebook():
    b=m.Codebook()
    assert not b.admit('source','Set value to 6.',[['kw','f','default',6]],False)
    assert not b.admit('source','Return early.',[['return_if','f','True','0']],True)
    assert b.entries==[]


def test_integer_template_rebinds_and_rejects_stale_or_ambiguous_input():
    b=m.Codebook()
    assert b.admit('source','Set default to 6.',[['kw','f','default',6]],True)
    assert b.retrieve('source','Set default to 8.',{'f'})[0]['edits']==[['kw','f','default',8]]
    assert not b.retrieve('changed','Set default to 8.',{'f'})
    assert not b.retrieve('source','Set 8 or 9.',{'f'})
    assert not b.retrieve('source','Set value to 8.5.',{'f'})
    assert not b.retrieve('source','Set default to 8.',{'other'})
    assert not b.admit('source','Set default to 8.',[['kw','f','default',8]],True)
    assert b.entries[0]['template'][3]=={'bind':'task_integer'}


def test_boolean_templates_do_not_become_integer_bindings():
    b=m.Codebook();assert b.admit('source','Disable flag.',[['kw','f','flag',False]],True)
    assert b.retrieve('source','Disable flag.',{'f'})[0]['edits'][0][3] is False
