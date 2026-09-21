"""Interleaved local pijit edits: C1-C3 generation versus C4, including cold starts."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import signal
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pijit_bridge', ROOT / 'integrations/pijit/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
SOURCE = ('import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n'
          '    p.add_argument("--workers", type=int, default=4)\n    return p\n')


def source_for(value):
    return SOURCE.replace('default=4', f'default={value}')


def summarize(rows):
    arms = {}
    for arm in ('generation', 'c4'):
        items = [row for row in rows if row['arm'] == arm]
        results = [row['result'] for row in items]
        accounting = [result['accounting'] for result in results]
        arms[arm] = {
            'attempts': len(items), 'passed': sum(row['passed'] for row in items),
            'cache_hits': sum(row['passed'] and result.get('cache_hit', False)
                              for row, result in zip(items, results)),
            'wall_seconds': sum(row['seconds'] for row in items),
            'median_seconds': statistics.median(row['seconds'] for row in items) if items else None,
            'stage_seconds': {key: sum(r['stage_seconds'].get(key, 0) for r in results)
                              for key in sorted({key for r in results for key in r['stage_seconds']})},
            'fallback_reasons': dict(Counter(r.get('fallback_reason') for r in results)),
            'usage_complete': all(a['usage_complete'] for a in accounting),
            **{key: sum(a[key] for a in accounting) for key in (
                'inference_requests', 'unknown_usage_requests', 'known_input_tokens',
                'known_generated_argument_tokens', 'known_classification_control_records')},
        }
    matched = (arms['generation']['attempts'] > 0 and
               arms['generation']['attempts'] == arms['c4']['attempts'] and
               all(a['passed'] == a['attempts'] and a['usage_complete'] for a in arms.values()))
    return {'arms': arms, 'all_pairs_passed_with_complete_usage': matched,
            'observed_generation_over_c4_wall_ratio': (
                arms['generation']['wall_seconds'] / arms['c4']['wall_seconds']
                if matched and arms['c4']['wall_seconds'] else None),
            'limitations': 'Small synthetic fixture; shared service; no stable speed claim. '
                           'Direct nested edit calls, not a complete Pi loop. Client wall includes '
                           'preparation, network, queueing, verification, writes and admission. '
                           'HTTP timings overlap concurrent tokenizer requests; do not sum them as wall time. '
                           'Failed inference with missing usage is unknown, not zero. No automatic retries.'}


def run(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    bridge.STATE = out / 'state'
    manifest = {'seed': args.seed, 'repeats': args.repeats, 'values': args.values,
                'baseline': 'C1-C3 with codebook lookup and admission disabled',
                'c4': 'Unmodified 0.95 probability / 3 margin gate; empty table per repeat',
                'pairing': 'Both arms receive identical intended source snapshots; independent '
                           'projects and tables. A failed edit cannot contaminate later inputs.',
                'verification': 'Exact expected AST, then default and explicit override behavior. '
                                'Same task oracle in both arms, included in timing, before admission.',
                'model': bridge.MODEL, 'sources': {}}
    sources = out / 'sources'
    sources.mkdir()
    for relative in ('benchmarks/compare_pijit_c4.py', 'integrations/pijit/bridge.py',
                     'deploy/jit_codebook.py', 'deploy/preset_edits.py', 'deploy/direct_structural_protocol.py',
                     'deploy/compact_structural_protocol.py', 'deploy/structural_edit_protocol.py'):
        source = ROOT / relative
        shutil.copyfile(source, sources / source.name)
        manifest['sources'][relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    rows = []
    rng = random.Random(args.seed)
    for repeat in range(args.repeats):
        projects = {arm: out / f'repeat-{repeat}' / arm for arm in ('generation', 'c4')}
        for project in projects.values():
            project.mkdir(parents=True)
        previous = 4
        for index, value in enumerate(args.values):
            arms = list(projects)
            rng.shuffle(arms)
            for arm in arms:
                project = projects[arm]
                source = source_for(previous)
                (project / 'app.py').write_text(source)
                # Reject unanticipated code before executing anything generated by the model.
                expected_ast = ast.dump(ast.parse(source_for(value)))
                check = ('import ast\nfrom pathlib import Path\n'
                         f'assert ast.dump(ast.parse(Path("app.py").read_text())) == {expected_ast!r}\n'
                         'import app\np = app.build_parser()\n'
                         f'assert p.parse_args([]).workers == {value}\n'
                         'assert p.parse_args(["--workers", "23"]).workers == 23\n')
                (project / 'verify.py').write_text(check)
                os.environ['PIJIT_DISABLE_CODEBOOK'] = '1' if arm == 'generation' else '0'
                os.environ['PIJIT_VERIFY_CMD'] = shlex.join([sys.executable, '-B', 'verify.py'])
                payload = {'action': 'edit', 'cwd': str(project), 'path': 'app.py',
                           'task': f'Change the --workers default to {value}.',
                           'session_id': f'c4-comparison-{repeat}-{arm}'}
                started = time.perf_counter()
                result = bridge.run(payload)
                try:
                    correct = ast.dump(ast.parse((project / 'app.py').read_text())) == expected_ast
                except SyntaxError:
                    correct = False
                row = {'repeat': repeat, 'index': index, 'arm': arm, 'order': arms,
                       'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                       'value': value, 'passed': result['status'] == 'ok' and correct,
                       'result': result, 'seconds': time.perf_counter() - started}
                rows.append(row)
                with (out / 'rows.jsonl').open('a') as stream:
                    stream.write(json.dumps(row) + '\n')
                print(json.dumps({'repeat': repeat, 'value': value, 'arm': arm,
                                  'passed': row['passed'], 'hit': result.get('cache_hit', False),
                                  'seconds': row['seconds']}), flush=True)
                if result['status'] == 'cancelled':
                    summary = summarize(rows)
                    summary.update(interrupted=True, all_pairs_passed_with_complete_usage=False,
                                   observed_generation_over_c4_wall_ratio=None)
                    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
                    return summary
            previous = value
    summary = summarize(rows)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--url', default=os.environ.get('PIJIT_URL'))
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--values', type=int, nargs='+', default=[6, 8, 10, 12])
    parser.add_argument('--seed', type=int, default=20260918)
    args = parser.parse_args()
    if not args.url or args.repeats < 1:
        parser.error('Provide --url (or PIJIT_URL) and a positive --repeats')
    os.environ['PIJIT_URL'] = args.url
    signal.signal(signal.SIGTERM, bridge.cancelled)
    signal.signal(signal.SIGINT, bridge.cancelled)
    summary = run(args)
    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary['all_pairs_passed_with_complete_usage'] else 1)
