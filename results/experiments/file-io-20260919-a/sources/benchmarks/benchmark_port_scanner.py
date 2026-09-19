"""One cold real coding task per arm, verified only against owned loopback sockets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from benchmark_three_goals import configuration
from compare_pijit_presets import attempt
from report_safe_codebook_agent import aggregate

ROOT = Path(__file__).resolve().parents[1]
PROMPT = '''Build a usable Python 3 TCP connect port scanner in this project. scanner.py is initially empty.
Use only the standard library. Deliver scanner.py, README.md, and unittest tests.
CLI: python scanner.py --host IPV4 --ports SPEC [--timeout SECONDS] [--workers N] [--json].
Accept one IPv4 literal (no hostname, CIDR, or IPv6). SPEC is a comma-separated mix of individual ports and inclusive ranges, e.g. 22,80,8000-8002. Trim whitespace, deduplicate, and sort ports; valid ports are 1..65535. Reject empty/malformed entries, reversed ranges and invalid ports with argparse exit code 2. Timeout must be finite and greater than zero; workers must be an integer from 1 through 256. Defaults: timeout 0.5 seconds and workers 32.
Use bounded concurrent TCP connection attempts, close every socket, and do not spawn one thread per port. Report reachable TCP ports only. Closed/unreachable ports are normal results, not fatal errors. Exit 0 after a completed scan even if nothing is open. In --json mode, stdout must be one JSON object exactly shaped as {"host": "127.0.0.1", "open_ports": [12345]} using the actual target and sorted unique open ports, with no progress text on stdout. Without --json, print a readable report. Importing scanner must not start a scan or parse CLI arguments. Include useful --help and Ctrl-C handling without a traceback.
Write and run unittest tests covering parser errors, duplicates/ranges, and actual open/closed port detection. Test network operations ONLY against temporary sockets you create on 127.0.0.1; do not scan external hosts, existing services, or broad port ranges. In README document usage, limits (TCP only, single IPv4 host), and use only on authorized systems. Finish with a concise summary of files and tests run. Do not install packages.'''
ORACLE = r'''import json, math, socket, subprocess, sys
from pathlib import Path
from contextlib import ExitStack
assert Path('scanner.py').stat().st_size > 0
assert Path('README.md').is_file()
assert list(Path('.').rglob('test*.py')), 'No delivered tests'
def run(*args):
 return subprocess.run([sys.executable,'-B','scanner.py',*args],capture_output=True,text=True,timeout=5)
base=['--host','127.0.0.1']
for spec in ['', '0', '65536', '5-3', '1,,2', 'abc', '1-', '-1', '1-2-3']:
 p=run(*base,'--ports',spec);assert p.returncode==2,(spec,p.returncode,p.stderr)
for option,values in [('--timeout',['0','-1','nan','inf']),('--workers',['0','257','x'])]:
 for value in values:
  p=run(*base,'--ports','12345',option,value);assert p.returncode==2,(option,value,p.returncode)
for host in ['999.0.0.1','localhost','::1','127.0.0.0/8']:
 p=run('--host',host,'--ports','12345');assert p.returncode==2,(host,p.returncode)
p=run('--help');assert p.returncode==0 and '--ports' in p.stdout
p=subprocess.run([sys.executable,'-B','-c','import scanner; print("import-ok")'],capture_output=True,text=True,timeout=3)
assert p.returncode==0 and p.stdout.strip()=='import-ok',(p.stdout,p.stderr)
with ExitStack() as stack:
 opened=[]
 for _ in range(2):
  sock=stack.enter_context(socket.socket());sock.bind(('127.0.0.1',0));sock.listen(32);opened.append(sock.getsockname()[1])
 closed=stack.enter_context(socket.socket());closed.bind(('127.0.0.1',0));closed_port=closed.getsockname()[1]
 for workers in ['1','4']:
  spec=f' {opened[1]}, {closed_port},{opened[0]},{opened[1]} '
  p=run(*base,'--ports',spec,'--timeout','.15','--workers',workers,'--json')
  assert p.returncode==0,(p.stdout,p.stderr)
  assert json.loads(p.stdout)==dict(host='127.0.0.1',open_ports=sorted(opened)),p.stdout
 p=run(*base,'--ports',str(closed_port),'--json');assert p.returncode==0 and json.loads(p.stdout)['open_ports']==[]
 p=run(*base,'--ports',str(opened[0]));assert p.returncode==0 and str(opened[0]) in p.stdout
 # Reserve an adjacent loopback pair: listener followed by bound but non-listening port.
 for _ in range(50):
  left=socket.socket();left.bind(('127.0.0.1',0));port=left.getsockname()[1]
  right=socket.socket()
  try:right.bind(('127.0.0.1',port+1))
  except (OSError,OverflowError):left.close();right.close();continue
  stack.enter_context(left);stack.enter_context(right);left.listen(8);break
 else:raise AssertionError('Cannot reserve adjacent test ports')
 p=run(*base,'--ports',f'{port}-{port+1},{port}','--json')
 assert p.returncode==0 and json.loads(p.stdout)==dict(host='127.0.0.1',open_ports=[port]),(p.stdout,p.stderr)
print('Independent loopback CLI checks passed')
'''


def main(args, scenario=None):
    scenario = scenario or dict(primary_file='scanner.py', files={'scanner.py': ''}, prompt=PROMPT, check=ORACLE)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    os.environ['PIJIT_URL'] = args.url
    arms = ['native_multi', 'hybrid']
    sources = [p for directory in ['benchmarks', 'deploy', 'integrations/pijit']
               for p in (ROOT / directory).glob('*') if p.suffix in ('.py', '.ts', '.mjs', '.txt')]
    hashes = {}
    for path in sources:
        relative = path.relative_to(ROOT); target = out / 'sources' / relative
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    configs = {arm: configuration(arm, args.tokenizer_revision, True, True) for arm in arms}
    for config in configs.values():
        config.update(PIJIT_PLANNER_MAX_TOKENS='8192', TAIR_NATIVE_MAX_TOKENS='8192')
    (out / 'manifest.json').write_text(json.dumps(dict(prompt=scenario['prompt'], arms=arms, configurations=configs,
        source_sha256=hashes, task_timeout=args.timeout, max_tokens_per_response=8192, repetitions=1, empty_codebooks=True,
        method='Native first, TAIR second, one attempt each. Same absolute workspace reset to the same input files, separate fresh state. Same backend and generation cap. Hidden independent oracle; no runtime verification command. No retries. Timing includes Agent and separately recorded oracle; excludes fixture/tunnel setup.'), indent=2))
    rows = []
    with tempfile.TemporaryDirectory(prefix='tair-port-scanner-') as tmp:
        project = Path(tmp) / 'project'
        for arm in arms:
            if project.exists():shutil.rmtree(project)
            project.mkdir()
            for name, content in scenario['files'].items():
                (project / name).write_text(content)
            folder = out / arm; folder.mkdir()
            state = Path(tmp) / 'states' / arm
            row = attempt(project, state, folder, 'native' if arm == 'native_multi' else 'c4', 0,
                          args.timeout, scenario=scenario, env_overrides=configs[arm])
            events = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines() if line.strip().startswith('{')]
            row.update(arm=arm, tool_errors=sum(e.get('type') == 'tool_execution_end' and e.get('isError', False) for e in events))
            shutil.copytree(project, folder / 'project-after', ignore=shutil.ignore_patterns('__pycache__'))
            for book in state.glob('workspaces/*/codebook.json'):shutil.copyfile(book, folder / 'codebook.json')
            (folder / 'final-result.json').write_text(json.dumps(row, indent=2))
            rows.append(row)
            with (out / 'rows.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
            print(json.dumps(dict(arm=arm, passed=row['passed'], seconds=row['seconds'],
                                 usage_complete=row['usage_complete'])),flush=True)
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    summary={arm:aggregate([r for r in rows if r['arm']==arm]) for arm in arms}
    for arm, result in summary.items():
        row=next(r for r in rows if r['arm']==arm)
        result['agent_seconds']=row['seconds']
        result['oracle_seconds']=row['validation']['seconds']
        result['output_tokens_total']=result['known_generated_argument_tokens']+result['known_classification_control_records']
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2),flush=True)
    return int(not all(r['passed'] and r['usage_complete'] for r in rows))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--tokenizer-revision',required=True);p.add_argument('--timeout',type=float,default=600)
    raise SystemExit(main(p.parse_args()))
