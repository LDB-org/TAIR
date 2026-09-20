from pathlib import Path
import sys
import sqlite3
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
from adaptive_plan import PlanBook, execute_and_learn, infer, digest


def result(steps):
    return dict(plan=dict(name='plan', arguments=dict(steps=steps)))


def test_verified_generation_is_persistent_and_deduplicated(tmp_path):
    book = PlanBook(tmp_path / 'book.json')
    steps = [dict(op='write', path='a.py', content='value = 1\n')]
    for n in range(2):
        admitted = execute_and_learn(result(steps), {'a.py': 'value is 1'}, tmp_path / str(n), book,
                                     lambda p, c: 'external check passed')
        assert len(admitted) == (1 if n == 0 else 0)
    loaded = PlanBook(book.path).load()
    assert len(loaded) == 1 and loaded[0]['source'] == steps[0]['content']
    with sqlite3.connect(book.path) as db:
        db.execute("UPDATE entries SET source='value = 2'")
    with pytest.raises(ValueError, match='Corrupt'):
        book.load()


def test_failed_plan_admits_nothing_and_publishes_nothing(tmp_path):
    book = PlanBook(tmp_path / 'book.json')
    steps = [dict(op='write', path=p, content='x = 1') for p in ['a.py', 'b.py']]
    def verifier(path, contract):
        if path.name == 'b.py':
            raise ValueError('behavior failed')
        return 'passed'
    with pytest.raises(ValueError, match='behavior failed'):
        execute_and_learn(result(steps), dict.fromkeys(['a.py', 'b.py'], 'contract'), tmp_path / 'output', book, verifier)
    assert not book.path.exists() and not (tmp_path / 'output').exists()


@pytest.mark.parametrize('name', ['../escape.py', '/tmp/tair-absolute.py'])
def test_escape_rejected_before_verifier(tmp_path, name):
    def unreachable(*args):
        pytest.fail('verifier reached')
    with pytest.raises(ValueError, match='escapes'):
        execute_and_learn(result([dict(op='write', path=name, content='x=1')]), {name: 'contract'},
                          tmp_path, PlanBook(tmp_path / 'book.json'), unreachable)


@pytest.mark.parametrize('abandon', [False, True])
def test_engine_selects_entry_then_continues_in_one_inference(tmp_path, abandon):
    book = PlanBook(tmp_path / 'book.json')
    book.admit([('value is 1', 'value = 1\n', 'external test')])
    routes = []
    def transport(url, route, body):
        routes.append(route)
        if route == '/tokenize':
            if 'prompt' in body:
                return {'tokens': [ord(body['prompt'])]}
            return {'tokens': [1, 2] if len(body['messages']) == 3 else [1, 2, 3, 4]}
        assert route == '/v1/openjev/toolcall'
        assert all(t['name'] == 'plan' for t in body['tools'])
        step = dict(op='write', path='a.py', content='value = 2\n') if abandon else dict(op='reuse', path='a.py')
        return dict(decision=dict(index=0), same_engine_session=True, finish_reason='stop',
                    classification_control_records=1, generated_argument_tokens=10,
                    call=dict(name='plan', arguments=dict(steps=[step])))
    actual = infer('unused', 'make module', {'a.py': 'value is 1'}, book, transport)
    assert routes.count('/v1/openjev/toolcall') == 1
    assert actual['controls'] == 1 and actual['inference_requests'] == 1
    assert actual['plan']['arguments']['steps'][0]['content'] == ('value = 2\n' if abandon else 'value = 1\n')
    assert actual['classification_abandoned'] == abandon


def test_reuse_must_pass_current_contract_verifier(tmp_path):
    source = 'value = 1\n'
    book = PlanBook(tmp_path / 'book.json')
    step = dict(op='reuse', path='a.py', content=source, source_sha256=digest(source))
    with pytest.raises(ValueError, match='evidence'):
        execute_and_learn(result([step]), {'a.py': 'value is 2'}, tmp_path / 'out', book, lambda p,c: '')
    assert not book.path.exists() and not (tmp_path / 'out').exists()


def test_concurrent_admission_merges_and_bounds_catalog(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / 'book.json'
    def add(index):
        return PlanBook(path).admit([(f'value is {index}', f'value = {index}\n', 'external test')])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(add, range(4)))
    assert len(PlanBook(path).load()) == 4
    for index in range(4, 17):
        add(index)
    entries = PlanBook(path).load()
    assert len(entries) == 17
    assert entries[-1]['source'] == 'value = 16\n'


def test_shortlist_does_not_truncate_storage_and_rejects_scoped_pair(tmp_path):
    book = PlanBook(tmp_path/'book.json')
    book.admit([(f'Unrelated counter contract {i}', f'value = {i}', 'check') for i in range(40)])
    identity, = book.admit([('Parse UTF-16 binary records', 'value = 99', 'check')])
    candidates = book.candidates('parse records', {'a.py':'Parse UTF-16 binary records'})
    assert len(book.load()) == 41 and 1 <= len(candidates) <= 15
    assert candidates[0]['id'] == identity
    book.reject(identity, 'Parse UTF-16 binary records')
    assert identity not in {e['id'] for e in book.candidates('parse records', {'a.py':'Parse UTF-16 binary records'})}
    assert identity in {e['id'] for e in book.candidates('parse records', {'a.py':'Parse UTF-16 binary records again'})}


def test_storage_has_no_256_entry_cutoff(tmp_path):
    book = PlanBook(tmp_path/'book.json')
    book.admit([(f'constant {i}',f'value = {i}','constant check') for i in range(260)])
    entries = book.load()
    assert len(entries)==260
    assert entries[0]['source']=='value = 0' and entries[-1]['source']=='value = 259'


def test_rejected_reuse_recovers_once_and_preserves_both_attempts(tmp_path, monkeypatch):
    import adaptive_plan as module
    book = PlanBook(tmp_path/'book.json')
    identity, = book.admit([('value is 2', 'value = 1', 'old check')])
    calls = []
    def fake(*args, force_generate=False, **kwargs):
        calls.append(force_generate)
        step = dict(op='write', path='a.py', content='value = 2') if force_generate else dict(
            op='reuse', path='a.py', content='value = 1', source_sha256=digest('value = 1'), entry_id=identity)
        return result([step])
    monkeypatch.setattr(module, 'infer', fake)
    def verify(path, contract):
        if path.read_text() != 'value = 2':raise ValueError('Wrong value')
        return 'Independent expected value 2'
    actual = module.run_plan('', '', {'a.py':'value is 2'}, tmp_path/'output', book, verify)
    assert calls == [False, True] and actual['recovered']
    assert len(actual['attempts']) == 2 and 'verification_error' in actual['attempts'][0]
    assert (tmp_path/'output/a.py').read_text() == 'value = 2'
    assert identity not in {e['id'] for e in book.candidates('', {'a.py':'value is 2'})}


def test_recovery_failure_stops_after_two_and_never_publishes(tmp_path, monkeypatch):
    import adaptive_plan as module
    calls = []
    def fake(*args, **kwargs):
        calls.append(kwargs['force_generate'])
        return result([dict(op='write', path='a.py', content='value = 1')])
    monkeypatch.setattr(module, 'infer', fake)
    def reject(*args):raise ValueError('Wrong value')
    book = PlanBook(tmp_path/'book.json')
    with pytest.raises(module.VerificationError):
        module.run_plan('', '', {'a.py':'value is 2'}, tmp_path/'output', book, reject)
    assert calls == [False, True] and not (tmp_path/'output').exists() and book.load()==[]


def test_only_successfully_published_reuse_updates_frequency(tmp_path):
    book = PlanBook(tmp_path/'book.sqlite3')
    identity, = book.admit([('value is 1', 'value=1', 'check')])
    step = dict(op='reuse', path='a.py', content='value=1', entry_id=identity,
                source_sha256=digest('value=1'))
    with pytest.raises(ValueError, match='evidence'):
        execute_and_learn(result([step]), {'a.py':'value is 1'}, tmp_path/'bad', book, lambda p,c:'')
    assert book.load()[0]['reuse_count'] == 0
    execute_and_learn(result([step]), {'a.py':'value is 1'}, tmp_path/'good', book, lambda p,c:'check')
    assert book.load()[0]['reuse_count'] == 1
    assert book.load()[0]['successes'] == 2
