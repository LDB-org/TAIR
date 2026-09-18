"""Private-host maintenance controller. Never emits container environment/config."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

os.umask(0o077)
BASE = Path('/opt/openjev-toolcall/maintenance/scheduler-20260918T033422Z')
NAME = 'vllm-deepseek-v4-sm120-situ'
PREPARED = NAME + '-seq8-prepared-20260918'
ROLLBACK = NAME + '-seq4-rollback-20260918'
FAILED = NAME + '-seq8-stopped-20260918'
ROOT = '/usr/local/lib/python3.12/dist-packages/vllm/'
TIMER = 'vllm-deepseek-health-watchdog.timer'
SERVICE = 'vllm-deepseek-health-watchdog.service'


def call(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def inspect(identifier):
    return json.loads(call('docker', 'inspect', identifier))[0]


def save(state):
    tmp = BASE / 'state.tmp'
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(BASE / 'state.json')


def load():
    return json.loads((BASE / 'state.json').read_text())


class DockerHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(60)
        self.sock.connect('/var/run/docker.sock')


def api(method, path, body=None):
    client = DockerHTTP('localhost', timeout=60)
    client.request(method, path, body=json.dumps(body) if body else None,
                   headers={'Content-Type': 'application/json'})
    response = client.getresponse()
    data = json.loads(response.read() or '{}')
    client.close()
    if response.status >= 300:
        (BASE / 'docker-api-error.json').write_text(json.dumps(data))
        raise RuntimeError('Docker API failed; private error saved')
    return data


def prepare():
    assert not (BASE / 'state.json').exists(), 'Already prepared; inspect state before continuing'
    original = json.loads((BASE / 'original-inspect.json').read_text())
    proposal = json.loads((BASE / 'proposal-summary.json').read_text())
    live = inspect(NAME)
    assert live['Id'] == original['Id'] and live['Image'] == original['Image']
    assert live['Config'] == original['Config'] and live['HostConfig'] == original['HostConfig']
    expected = proposal['source_hashes']
    actual = call('docker', 'exec', NAME, 'sha256sum', *[ROOT + p for p in expected])
    assert {line.split()[1][len(ROOT):]: line.split()[0] for line in actual.splitlines()} == expected
    assert set(live['NetworkSettings']['Networks']) == {'bridge'}
    body = copy.deepcopy(original['Config'])
    body['Image'] = original['Image']
    body['Cmd'] = json.loads((BASE / 'proposed-command.json').read_text())
    body['HostConfig'] = copy.deepcopy(original['HostConfig'])
    body['HostConfig']['RestartPolicy'] = {'Name': 'no', 'MaximumRetryCount': 0}
    assert not body['HostConfig']['AutoRemove']
    (BASE / 'candidate-create.json').write_text(json.dumps(body, indent=2))
    version = api('GET', '/version')['ApiVersion']
    created = api('POST', '/v' + version + '/containers/create?name=' + PREPARED, body)
    state = {'phase': 'created', 'original_id': original['Id'], 'candidate_id': created['Id'],
             'original_restart_policy': original['HostConfig']['RestartPolicy'],
             'watchdog_was_active': subprocess.run(['systemctl', 'is-active', '--quiet', TIMER]).returncode == 0,
             'created_at': time.time()}
    save(state)
    copied = {}
    for rel in expected:
        source = BASE / ('proposed-helper.py' if rel == 'openjev_direct_tools.py' else 'original-source/' + rel)
        call('docker', 'cp', str(source), state['candidate_id'] + ':' + ROOT + rel)
        check = BASE / 'candidate-source-check' / rel
        check.parent.mkdir(parents=True, exist_ok=True)
        call('docker', 'cp', state['candidate_id'] + ':' + ROOT + rel, str(check))
        assert source.read_bytes() == check.read_bytes(), rel
        copied[rel] = hashlib.sha256(check.read_bytes()).hexdigest()
    state.update(phase='prepared', candidate_source_hashes=copied)
    save(state)
    return {'phase': state['phase'], 'candidate_id': state['candidate_id'], 'source_files_verified': len(copied)}


def switch():
    state = load()
    assert state['phase'] == 'prepared'
    assert inspect(NAME)['Id'] == state['original_id']
    assert inspect(PREPARED)['Id'] == state['candidate_id']
    call('systemctl', 'stop', TIMER, SERVICE)
    state.update(phase='stopping_original', switch_started_at=time.time())
    save(state)
    call('docker', 'stop', '--time', '90', state['original_id'])
    call('docker', 'update', '--restart=no', state['original_id'])
    call('docker', 'rename', state['original_id'], ROLLBACK)
    call('docker', 'rename', state['candidate_id'], NAME)
    state.update(phase='starting_candidate')
    save(state)
    call('docker', 'start', state['candidate_id'])
    state.update(phase='candidate_started', candidate_started_at=time.time())
    save(state)
    return {'phase': state['phase'], 'rollback_container': ROLLBACK}


def rollback():
    state = load()
    assert state['phase'] in ('candidate_started', 'starting_candidate', 'stopping_original', 'accepted')
    call('systemctl', 'stop', TIMER, SERVICE)
    candidate = inspect(state['candidate_id'])
    call('docker', 'update', '--restart=no', state['candidate_id'])
    if candidate['State']['Running']:
        call('docker', 'stop', '--time', '60', state['candidate_id'])
    call('docker', 'rename', state['candidate_id'], FAILED)
    original = inspect(state['original_id'])
    if original['Name'] != '/' + NAME:
        call('docker', 'rename', state['original_id'], NAME)
    call('docker', 'start', state['original_id'])
    state.update(phase='rollback_started', rollback_started_at=time.time())
    save(state)
    return {'phase': state['phase'], 'failed_candidate_retained': FAILED}


def finish():
    # Caller must first verify health, native generation and direct tool calling.
    state = load()
    assert state['phase'] in ('candidate_started', 'rollback_started')
    identifier = state['candidate_id'] if state['phase'] == 'candidate_started' else state['original_id']
    assert inspect(NAME)['Id'] == identifier and inspect(identifier)['State']['Running']
    policy = state['original_restart_policy']
    restart = policy['Name']
    if restart == 'on-failure' and policy['MaximumRetryCount']:
        restart += ':' + str(policy['MaximumRetryCount'])
    call('docker', 'update', '--restart=' + restart, identifier)
    if state['watchdog_was_active']:
        call('systemctl', 'start', TIMER)
    state.update(phase='accepted' if identifier == state['candidate_id'] else 'rolled_back', finished_at=time.time())
    save(state)
    return {'phase': state['phase'], 'watchdog_restored': state['watchdog_was_active']}


if __name__ == '__main__':
    try:
        print(json.dumps({'prepare': prepare, 'switch': switch, 'rollback': rollback, 'finish': finish}[sys.argv[1]]()))
    except Exception as error:
        (BASE / 'control-error.txt').write_text(repr(error))
        print(json.dumps({'error_type': type(error).__name__, 'details': 'Saved privately; inspect state before retrying'}))
        raise SystemExit(1)
