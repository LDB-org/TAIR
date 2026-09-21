"""Full Agent cold/warm pairs with restored source and retained learned codebooks."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import statistics
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('general', ROOT / 'benchmarks/benchmark_general_pijit.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
b = g.b
SCENARIOS = {
    'properties': {
        'files': {'app.py': '''import argparse

def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4, help='old', required=False)
    p.add_argument('--timeout', type=float, default=1.5)
    p.add_argument('--host', default='localhost')
    p.add_argument('--verbose', action='store_true', default=False)
    return p
''', 'test_app.py': '''import unittest
from app import build_parser
class TestConfig(unittest.TestCase):
    def test_defaults(self):
        p=build_parser()
        a=p.parse_args(['--workers','3'])
        self.assertEqual((a.workers,a.timeout,a.host,a.verbose),(3,2.5,'remote',True))
        self.assertIn('Worker count',p.format_help())
        with self.assertRaises(SystemExit): p.parse_args([])
    def test_overrides(self):
        a=build_parser().parse_args(['--workers','9','--timeout','0.25','--host','custom'])
        self.assertEqual((a.workers,a.timeout,a.host),(9,0.25,'custom'))
'''},
        'prompt': 'Inspect this Python project. Change --timeout default to 2.5. Change --host default to "remote". Change --verbose default to true. Change --workers help to "Worker count". Change --workers required to true. Preserve explicit overrides and unrelated code. Do not change tests. Run python -m unittest -v and summarize.',
        'check': '''from app import build_parser
p=build_parser();a=p.parse_args(['--workers','7'])
assert (a.workers,a.timeout,a.host,a.verbose)==(7,2.5,'remote',True)
assert 'Worker count' in p.format_help()
assert next(a for a in p._actions if a.dest=='workers').required
b=p.parse_args(['--workers','8','--timeout','0.5','--host','elsewhere'])
assert (b.workers,b.timeout,b.host)==(8,0.5,'elsewhere')
'''},
    'alias': {
        'files': {'app.py': "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n    p.add_argument('--workers', type=int, default=4)\n    return p\n",
                  'test_app.py': '''import unittest
from app import build_parser
class TestAlias(unittest.TestCase):
    def test_alias(self):
        p=build_parser()
        self.assertEqual(p.parse_args(['-w','9']).workers,9)
        self.assertEqual(p.parse_args(['--workers','7']).workers,7)
        self.assertEqual(p.parse_args([]).workers,4)
'''},
        'prompt': 'Inspect this Python project. Add alias -w to --workers. Preserve its default, type, long option and all unrelated behavior. Do not change tests. Run python -m unittest -v and summarize.',
        'check': '''from app import build_parser
p=build_parser()
assert p.parse_args(['-w','13']).workers==13
assert p.parse_args(['--workers','17']).workers==17
assert p.parse_args([]).workers==4
'''},
    'summary_bug': g.SCENARIOS['summary_bug'],
}


def main(args):
    comparison = getattr(args, 'outer_comparison', False)
    arm_names = ['native', 'accelerated', 'optimized'] if comparison else ['native', 'generation', 'accelerated']
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    snapshots = out / 'sources'; snapshots.mkdir()
    for src in ['benchmarks/benchmark_schema_jit_agent.py', 'benchmarks/benchmark_general_pijit.py',
                'benchmarks/compare_pijit_presets.py', 'benchmarks/native_pi_trace.ts',
                'integrations/pijit/bridge.py', 'integrations/pijit/extension.ts', 'integrations/pijit/launch.mjs',
                'deploy/schema_actions.py', 'deploy/preset_edits.py', 'deploy/jit_codebook.py',
                'deploy/direct_structural_protocol.py', 'deploy/compact_structural_protocol.py',
                'deploy/structural_edit_protocol.py']:
        shutil.copyfile(ROOT / src, snapshots / Path(src).name)
    (out / 'scenarios.json').write_text(json.dumps(SCENARIOS, indent=2))
    (out / 'manifest.json').write_text(json.dumps({
        'arms': arm_names, 'outer_comparison': comparison, 'rounds': 2, 'repeats': args.repeats,
        'seed': 20260921, 'tokenizer_revision': os.environ.get('PIJIT_TOKENIZER_REVISION'),
        'timing': 'Pi startup through exit plus external final oracle. In-loop tests and recovery included; fixture reset excluded.',
        'pairing': 'Same absolute project per arm/pair; identical initial files restored before both rounds. Fresh Agent session each time. Round two retains only runtime state (learned codebook and tokenizer cache); no conversation history. No preseeded correct edits.',
        'baseline': 'Native stock tools on same patched server; generation uses compact tools without schema/JIT. Accelerated uses expanded schema and exact-source learned replay. Tool catalogs and provider prompts differ; not a pure classifier-only comparison.',
        'admission': 'Generated typed edits admitted after existing local syntax/project checks. Full task oracle is run externally afterward; admission is not proof of semantic correctness.'}, indent=2))
    rows = []; rng = random.Random(20260921)
    with tempfile.TemporaryDirectory(prefix='tair-agent-jit-') as temp:
        for repeat in range(args.repeats):
            for name, scenario in SCENARIOS.items():
                for round_ in (1, 2):
                    arms = list(arm_names); rng.shuffle(arms)
                    for arm in arms:
                        root = Path(temp) / f'{repeat}-{name}-{arm}'
                        project = root / 'project'; state = root / 'state'
                        if project.exists(): shutil.rmtree(project)
                        project.mkdir(parents=True)
                        for filename, content in scenario['files'].items():
                            (project / filename).write_text(content)
                        folder = out / f'{repeat}-{name}-{arm}-round{round_}'; folder.mkdir()
                        enabled = str(int(arm in ('accelerated', 'optimized')))
                        os.environ.update(PIJIT_SCHEMA_ACTIONS=enabled, PIJIT_JIT_ACTIONS=enabled, PIJIT_LOCAL_ROUTING=enabled,
                                          PIJIT_CONTINUATION_CACHE=str(int(arm == 'optimized')),
                                          PIJIT_DIRECTORY_GUARD=str(int(arm == 'optimized')))
                        row = b.attempt(project, state, folder, 'c4' if arm in ('accelerated', 'optimized') else arm,
                                        0, 120, scenario=scenario)
                        row.update(arm=arm, case=name, repeat=repeat, round=round_, order=arms)
                        events = [json.loads(l) for l in (folder / 'events.jsonl').read_text().splitlines() if l.strip()]
                        row['tool_calls'] = [{'name': e.get('toolName'), 'error': e.get('isError', False)}
                                             for e in events if e.get('type') == 'tool_execution_end']
                        row['jit_entries'] = sum(len(json.loads(p.read_text())) for p in state.glob('workspaces/*/jit-actions.json'))
                        for p in state.glob('workspaces/*/jit-actions.json'):
                            shutil.copyfile(p, folder / 'learned-codebook.json')
                        shutil.copytree(project, folder / 'project-after', ignore=shutil.ignore_patterns('__pycache__'))
                        # Tests requested to remain unchanged are part of correctness, independently checked.
                        if name != 'summary_bug':
                            row['passed'] &= (project / 'test_app.py').read_text() == scenario['files']['test_app.py']
                        rows.append(row)
                        with (out / 'rows.jsonl').open('a') as stream: stream.write(json.dumps(row) + '\n')
                        print(json.dumps({'case': name, 'repeat': repeat, 'round': round_, 'arm': arm,
                            'passed': row['passed'], 'seconds': row['validated_seconds'], 'jit_entries': row['jit_entries'],
                            'jit_hits': sum(r.get('jit_hit', False) for r in row['metrics']),
                            'schema_hits': sum(r.get('schema_hit', False) for r in row['metrics']),
                            'tools': row['tool_calls']}), flush=True)
    summary = []
    for name in SCENARIOS:
        for arm in arm_names:
            for round_ in (1, 2):
                selected = [r for r in rows if (r['case'], r['arm'], r['round']) == (name, arm, round_)]
                records = [m for r in selected for m in r['metrics']]
                summary.append({'case': name, 'arm': arm, 'round': round_, 'n': len(selected),
                    'passed': sum(r['passed'] for r in selected),
                    'mean_seconds': statistics.mean(r['validated_seconds'] for r in selected),
                    'edit_calls': sum(m['action'] == 'edit' for m in records),
                    'schema_hits': sum(m.get('schema_hit', False) for m in records),
                    'jit_hits': sum(m.get('jit_hit', False) for m in records),
                    'local_routes': sum(m.get('local_route') == 'supported_user_clause' for m in records),
                    'jit_admitted': sum(m.get('jit_admitted', 0) for m in records),
                    'continuation_cache_hits': sum(m.get('continuation_cache_hit', False) for m in records),
                    'directory_redirects': sum(bool(m.get('directory_read_redirect')) for m in records),
                    'tokenize_requests': sum(h['route'] == '/tokenize' for m in records for h in m.get('http_requests', [])),
                    'preparation_seconds': sum(m.get('stage_seconds', {}).get('generation_preparation', 0) for m in records),
                    'skipped_classification': sum(m.get('schema_decision', {}).get('classification_skipped', False) for m in records),
                    **{k: sum(m['accounting'][k] for m in records) for k in
                       ('inference_requests', 'known_input_tokens', 'known_generated_argument_tokens', 'known_classification_control_records')}})
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--outer-comparison', action='store_true', help='Compare previous accelerated path with continuation cache and directory guard')
    main(parser.parse_args())
