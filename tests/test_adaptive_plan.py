from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from benchmark_adaptive_plan import build_book, check_module, materialize, SEED


def reuse(book, path='text_io.py'):
    entry = book['entries'][0]
    return dict(op='reuse', path=path, entry_id=entry['id'], source_sha256=entry['source_sha256'])


def test_mixed_plan_and_stale_entry(tmp_path):
    book = build_book()
    step = reuse(book)
    step['source_sha256'] = 'stale'
    with pytest.raises(ValueError, match='stale'):
        materialize(dict(steps=[step]), book, tmp_path, ['text_io.py'], 'adaptive')
    assert not list(tmp_path.iterdir())
    steps = [reuse(book), dict(op='write', path='other.py', content='value = 42\n')]
    materialize(dict(steps=steps), book, tmp_path, ['text_io.py', 'other.py'], 'adaptive')
    assert (tmp_path / 'text_io.py').read_text() == book['entries'][0]['source']
    assert (tmp_path / 'other.py').read_text() == 'value = 42\n'


def test_invalid_plan_never_partially_writes(tmp_path):
    book = build_book()
    for steps, allowed in [
        ([reuse(book), reuse(book)], ['text_io.py']),
        ([reuse(book, '../escape.py')], ['../escape.py']),
        ([reuse(book)], ['text_io.py', 'missing.py']),
        ([reuse(book), dict(op='write', path='bad.py', content='def (')], ['text_io.py', 'bad.py']),
    ]:
        with pytest.raises((ValueError, SyntaxError)):
            materialize(dict(steps=steps), book, tmp_path, allowed, 'adaptive')
        assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('kind', ['utf16', 'parents', 'exclusive', 'binary'])
def test_seed_is_incompatible_with_new_contracts(kind):
    with pytest.raises(ValueError):
        check_module(SEED, kind)


def test_binary_oracle_uses_invalid_utf8(tmp_path):
    path = tmp_path / 'bad_binary.py'
    path.write_text('from pathlib import Path\ndef read_bytes(p): return Path(p).read_bytes()\ndef write_bytes(p, data, *, append=False): Path(p).write_text(data.decode("utf-8"))\n')
    with pytest.raises(ValueError, match='UnicodeDecodeError'):
        check_module(path, 'binary')
