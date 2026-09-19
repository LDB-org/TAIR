from pathlib import Path
import sys
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
    book.path.write_text(book.path.read_text().replace('value = 1', 'value = 2'))
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
    assert len(entries) == 15
    assert entries[-1]['source'] == 'value = 16\n'
