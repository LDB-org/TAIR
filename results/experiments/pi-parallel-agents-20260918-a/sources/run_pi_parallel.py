"""Run a bounded pair of independent real Pi loops in separate workspaces."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main(args):
    args.out.mkdir()
    def run(index):
        root = args.out / f'agent-{index}'
        command = ['node', str(ROOT / 'integrations/pi/run_scanner.mjs'),
                   '--out', str(root), '--pi-root', args.pi_root,
                   '--host', args.host, '--worker', args.worker,
                   '--mode', 'engine_raw', '--all-tools', 'true', '--max-turns', '20',
                   '--fixture', str(ROOT / 'benchmarks/data/pi-all-tools-fixture'),
                   '--prompt', str(ROOT / 'benchmarks/data/pi-all-tools-task.txt')]
        with (args.out / f'agent-{index}.log').open('x') as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=660)
        return {'agent': index, 'returncode': result.returncode, 'command': command}
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    summary = {'seconds': time.perf_counter() - started, 'concurrency': 2, 'agents': results}
    with (args.out / 'batch.json').open('x') as output:
        json.dump(summary, output, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=lambda p: Path(p).resolve())
    parser.add_argument('--pi-root', required=True)
    parser.add_argument('--host', default='rs-yuesheng-gpu-vps')
    parser.add_argument('--worker', required=True)
    main(parser.parse_args())
