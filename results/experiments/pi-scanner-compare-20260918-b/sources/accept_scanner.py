"""Independent scanner CLI acceptance, run INSIDE the private network namespace."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading


def cli(*args):
    return subprocess.run([sys.executable, 'port_scanner.py', *args], text=True, capture_output=True, timeout=10)


def main():
    listeners = [socket.socket() for _ in range(2)]
    reserved = socket.socket()
    reserved.bind(('127.0.0.1', 0))  # Reserved but NOT listening: cannot be stolen by another process.
    closed = reserved.getsockname()[1]
    for server in listeners:
        server.bind(('127.0.0.1', 0))
        server.listen()
        server.settimeout(0.1)
    stopping = threading.Event()

    def drain(server):
        while not stopping.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except socket.timeout:
                pass

    threads = [threading.Thread(target=drain, args=(s,)) for s in listeners]
    for thread in threads:
        thread.start()
    opened = sorted(s.getsockname()[1] for s in listeners)
    checks = []
    try:
        for workers in [1, 4, 16]:
            a, b = opened
            spec = f'{a},{closed},{b}-{b},{a}'
            result = cli('--host', '127.0.0.1', '--ports', spec, '--timeout', '0.2', '--workers', str(workers))
            assert result.returncode == 0, result.stderr
            value = json.loads(result.stdout)
            assert value == {'host': '127.0.0.1', 'open_ports': opened, 'closed_ports': [closed]}, value
            checks.append({'test': 'open_closed_range_duplicate', 'workers': workers, 'result': value})
        for spec in ['0', '65536', '20-10', 'abc', '1,,2', '1-2-3', '-1', '']:
            result = cli('--host', '127.0.0.1', '--ports', spec)
            assert result.returncode != 0, (spec, result.stdout)
            checks.append({'test': 'invalid_ports', 'value': spec, 'exit_code': result.returncode})
        for flag, value in [('--workers', '0'), ('--workers', '-1'), ('--timeout', '0'), ('--timeout', '-1')]:
            result = cli('--host', '127.0.0.1', '--ports', str(closed), flag, value)
            assert result.returncode != 0, (flag, value, result.stdout)
            checks.append({'test': 'invalid_option', 'flag': flag, 'value': value, 'exit_code': result.returncode})
        help_result = cli('--help')
        assert help_result.returncode == 0 and '--ports' in help_result.stdout
        checks.append({'test': 'help', 'exit_code': 0})
        assert Path('test_port_scanner.py').is_file()
        own = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_port_scanner'], capture_output=True, text=True, timeout=30)
        assert own.returncode == 0, own.stdout + own.stderr
        checks.append({'test': 'agent_written_unittest_rerun', 'stdout': own.stdout, 'stderr': own.stderr, 'exit_code': own.returncode})
        print(json.dumps({'status': 'passed', 'checks': checks, 'count': len(checks)}))
    finally:
        stopping.set()
        for thread in threads:
            thread.join()
        for server in listeners:
            server.close()
        reserved.close()


if __name__ == '__main__':
    main()
