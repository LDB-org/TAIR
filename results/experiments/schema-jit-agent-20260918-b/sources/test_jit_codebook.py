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


def test_exact_codebook_is_task_path_source_and_result_bound():
    book = m.ExactCodebook()
    edits = [['arg', '--workers', '-w'], ['kw', '--timeout', 'default', 2.5]]
    assert book.admit('before', 'Add alias and change timeout.', '/p/app.py', edits, 'after', 'project checks')
    edits[0][2] = '-x'
    entry = book.retrieve('before', 'Add alias and change timeout.', '/p/app.py')
    assert entry['edits'][0][2] == '-w'
    assert entry['updated_sha256'] == m.digest('after')
    assert not book.retrieve('after', 'Add alias and change timeout.', '/p/app.py')
    assert not book.retrieve('before', 'Other task.', '/p/app.py')
    assert not book.retrieve('before', 'Add alias and change timeout.', '/other/app.py')
    assert not book.admit('before', 'Add alias and change timeout.', '/p/app.py', edits, 'after', 'checks')
    assert not book.admit('same', 'No change.', '/p/app.py', edits, 'same', 'checks')
    assert not book.admit('before', 'Unvalidated.', '/p/app.py', edits, 'after', '')


def test_exact_codebook_refuses_ambiguous_duplicate_entries():
    book = m.ExactCodebook()
    book.admit('before', 'task', 'path', [['kw', 'f', 'default', 3]], 'after', 'checks')
    book.entries.append(dict(book.entries[0]))
    assert book.retrieve('before', 'task', 'path') is None
