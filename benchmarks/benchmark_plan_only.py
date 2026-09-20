"""Real local Pi + fused engine smoke: only plan, cold admission and warm reuse."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'deploy'))
from plan_book import PlanBook
from benchmark_adaptive_plan import check_module
from benchmark_engine_adaptive import CONTRACTS


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for relative in ['integrations/pijit/launch.mjs', 'integrations/pijit/extension.ts',
                     'integrations/pijit/bridge.py', 'integrations/pijit/validate_utf8_demo.py',
                     'deploy/adaptive_plan.py', 'deploy/plan_book.py', 'deploy/tool_plan.py', 'deploy/native_planner.py',
                     'integrations/pijit/plan_executor.mjs',
                     'benchmarks/benchmark_plan_only.py', 'benchmarks/benchmark_adaptive_plan.py']:
        path = out/'sources'/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, path)
    with tempfile.TemporaryDirectory(prefix='tair-plan-only-') as temp:
        root = Path(temp); workspace = root/'workspace'; workspace.mkdir()
        env = {k:v for k,v in os.environ.items() if not k.startswith(('PIJIT_', 'TAIR_'))}
        env.update(PIJIT_SSH_HOST='rs-yuesheng-gpu-public', PIJIT_PYTHON=sys.executable,
                   PIJIT_STATE_DIR=str(root/'state'),
                   PIJIT_PLAN_VERIFY_ARGV=json.dumps([sys.executable, str(ROOT/'integrations/pijit/validate_utf8_demo.py')]))
        for i, name in enumerate(['cold_io.py', 'warm_io.py']):
            prompt = 'Create ONLY '+name+'. '+CONTRACTS['utf8']+' No other files. Use plan; the trusted validator runs the checks.'
            start = time.perf_counter()
            completed = subprocess.run(['node', str(ROOT/'integrations/pijit/launch.mjs'), '--plan-only', '--verified-modules', '-p', prompt],
                                       cwd=workspace, env=env, capture_output=True, text=True, timeout=100)
            elapsed = time.perf_counter()-start
            (out/f'{i}-stdout.txt').write_text(completed.stdout)
            (out/f'{i}-stderr.txt').write_text(completed.stderr)
            metrics_path = next((root/'state').glob('workspaces/*/metrics.jsonl'))
            raw = metrics_path.read_text(); (out/f'{i}-metrics.jsonl').write_text(raw)
            all_records = [json.loads(line) for line in raw.splitlines()]
            records = all_records[sum(len(row['records']) for row in rows):]
            row = dict(round=i, returncode=completed.returncode, seconds=elapsed, records=records)
            rows.append(row); (out/'report.json').write_text(json.dumps(rows, indent=2))
            assert completed.returncode == 0, completed.stderr
            assert all(r['status']=='ok' for r in records)
            assert all(r['available_tools']==['plan'] and r['plan_only'] for r in records if r['action']=='chat')
            plans = [r for r in records if r['action']=='plan']
            assert len(plans)==1 and plans[0]['adaptive_plan']
            assert plans[0]['cache_hit'] == bool(i)
            assert len(plans[0]['admitted']) == (0 if i else 1)
            assert all(r['action'] in ('chat','plan') for r in records)
            check_module(workspace/name, 'utf8')
            shutil.copyfile(workspace/name, out/name)
            assert {p.name for p in workspace.iterdir()} == set(['cold_io.py','warm_io.py'][:i+1])
            print(json.dumps(dict(round=i,seconds=elapsed,hit=plans[0]['cache_hit'],passed=True)), flush=True)
        assert (workspace/'cold_io.py').read_bytes() == (workspace/'warm_io.py').read_bytes()
        book = PlanBook(metrics_path.parent/'plan-codebook.sqlite3')
        entries = book.load()
        assert len(entries)==1 and entries[0]['reuse_count']==1
        (out/'book.json').write_text(json.dumps(entries, indent=2))
        for path in (root/'state/agent/sessions').rglob('*.jsonl'):
            shutil.copyfile(path, out/('session-'+path.name))
    files=sorted(p for p in out.rglob('*') if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
