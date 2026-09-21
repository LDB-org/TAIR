import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
from plan_book import PlanBook, digest


def legacy(path, corrupt=False):
    source = 'value = 1'
    entry = dict(id=digest('constant\0' + source), contract='constant', source=source,
                 source_sha256='bad' if corrupt else digest(source), verification='trusted')
    path.write_text(json.dumps(dict(version=1, entries=[entry])))
    return entry


def test_legacy_import_once_preserves_original_and_rejections(tmp_path):
    path = tmp_path/'book.json'
    entry = legacy(path)
    raw = path.read_bytes()
    path.with_suffix('.rejected.json').write_text(json.dumps([[entry['id'], digest('constant')]]))
    book = PlanBook(path)
    assert book.candidates('', {'a.py': 'constant'}) == []
    assert book.candidates('', {'a.py': 'constant again'})[0]['id'] == entry['id']
    assert path.read_bytes() == raw and book.path.suffix == '.sqlite3'
    book.prune(0)
    assert PlanBook(path).load() == []  # Never reimport evicted legacy entries.


def test_failed_import_rolls_back_then_can_retry(tmp_path):
    path = tmp_path/'book.json'
    legacy(path, corrupt=True)
    with pytest.raises(ValueError, match='Corrupt'):
        PlanBook(path).load()
    legacy(path)
    assert len(PlanBook(path).load()) == 1


def test_failed_admission_is_transactional(tmp_path):
    book = PlanBook(tmp_path/'book.sqlite3')
    with pytest.raises(SyntaxError):
        book.admit([('valid', 'x=1', 'check'), ('invalid', 'def', 'check')])
    assert book.load() == []
    assert book.candidates('valid', {}) == []


def test_index_query_does_not_load_entire_book_and_handles_chinese(tmp_path, monkeypatch):
    book = PlanBook(tmp_path/'book.sqlite3')
    book.admit([(f'noise {i}', f'x={i}', 'check') for i in range(1000)])
    identity, = book.admit([('读取本地文件并返回内容', 'x=0', 'check')])
    monkeypatch.setattr(book, 'load', lambda: pytest.fail('full scan'))
    assert book.candidates('读取文件', {})[0]['id'] == identity
    assert book.candidates('totallyunrelated', {}) == []
    assert book.candidates('" OR * - ()', {}) == []
    with pytest.raises(ValueError):
        book.candidates('noise', {}, 16)


def test_retention_uses_verified_reuse_and_version(tmp_path):
    book = PlanBook(tmp_path/'book.sqlite3')
    hot, = book.admit([('old hot', 'x=0', 'check')])
    stale, = book.admit([('old format', 'x=1', 'check')])
    book.record_reuse([hot, hot, stale, stale, stale])
    book.admit([(f'new {i}', f'x={i}', 'check') for i in range(4)])
    with sqlite3.connect(book.path) as db:
        db.execute('UPDATE entries SET entry_version=2 WHERE id=?', (stale,))
    assert book.candidates('old format', {})[0]['id'] == hot
    assert book.prune(2) == 4
    entries = book.load()
    assert hot in {e['id'] for e in entries} and stale not in {e['id'] for e in entries}
    assert next(e for e in entries if e['id'] == hot)['reuse_count'] == 2
    assert len(book.candidates('new', {})) == 1  # Deleted FTS rows are removed too.


def test_rejection_survives_more_than_256_other_rejections(tmp_path):
    book = PlanBook(tmp_path/'book.sqlite3')
    identity, = book.admit([('constant', 'x=1', 'check')])
    for i in range(260):
        book.reject(identity, f'constant {i}')
    assert book.candidates('', {'a': 'constant 0'}) == []
    assert len(book.candidates('', {'a': 'constant 999'})) == 1


def test_concurrent_process_first_use_migrates_once_and_merges(tmp_path):
    from concurrent.futures import ProcessPoolExecutor
    path = tmp_path/'book.json'
    legacy(path)
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(admit_process, [(str(path), i) for i in range(12)]))
    assert len(PlanBook(path).load()) == 13


def admit_process(args):
    path, i = args
    PlanBook(path).admit([(f'process {i}', f'x={i}', 'check')])


def test_lazy_source_read_survives_concurrent_prune(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import sqlite3
    book=PlanBook(tmp_path/'snapshot.sqlite3')
    identity=book.admit([('read file','value=1','verified')])[0]
    with book.connection() as db:
        db.execute('PRAGMA journal_mode=WAL')
    original=book.connection
    pruned=[]
    def prune_between_queries(sql):
        if not pruned and sql.startswith('SELECT * FROM entries WHERE seq IN'):
            with sqlite3.connect(book.path) as writer:
                writer.execute('DELETE FROM entries')
            pruned.append(True)
    @contextmanager
    def connection():
        with original() as db:
            db.set_trace_callback(prune_between_queries)
            yield db
    monkeypatch.setattr(book,'connection',connection)
    result=book.candidates('read file',{},limit=1)
    assert pruned and [entry['id'] for entry in result]==[identity]
    assert result[0]['source']=='value=1' and book.count()==0
