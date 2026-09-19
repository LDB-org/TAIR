"""Run independent scanner acceptance in a private network/filesystem namespace."""
import argparse
import json
from pathlib import Path
import subprocess


def accept(run):
    run = Path(run).resolve()
    check = Path(__file__).resolve().parents[1] / 'integrations/pi/accept_scanner.py'
    args = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
            '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
            '--ro-bind', str(run / 'workspace'), '/work', '--ro-bind', str(check), '/accept_scanner.py',
            '--chdir', '/work', '/usr/bin/python3', '/accept_scanner.py']
    with (run / 'acceptance.json').open('x') as out:
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=60)
            data = json.loads(result.stdout) if result.returncode == 0 else {
                'status': 'failed', 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        except subprocess.TimeoutExpired:
            data = {'status': 'failed', 'error': 'Acceptance timed out'}
        json.dump(data, out, ensure_ascii=False, indent=2)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    data = accept(parser.parse_args().run)
    print(json.dumps(data, ensure_ascii=False))
    raise SystemExit(0 if data['status'] == 'passed' else 1)
