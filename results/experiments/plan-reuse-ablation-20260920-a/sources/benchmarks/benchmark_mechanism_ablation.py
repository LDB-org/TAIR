"""Single-factor comparisons on fresh full Pi loops; dependent factors use explicit parents."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import tempfile

from benchmark_codebook_agent import b, test_integrity
from expanded_agent_scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
CASES = ('properties', 'alias', 'summary_bug', 'json_config', 'quoted_csv', 'wide_project')
FLAGS = ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_LOCAL_ROUTING',
         'PIJIT_PRESET_EDITS', 'PIJIT_SERIAL_PREPARATION', 'PIJIT_DISABLE_CODEBOOK',
         'PIJIT_CONTINUATION_CACHE', 'PIJIT_DIRECTORY_GUARD', 'PIJIT_BATCH_TOOLS',
         'PIJIT_PLAN_CONTEXT', 'PIJIT_TOKENIZER_REVISION')
# Each treatment changes exactly one flag relative to its named parent.
EDGES = {
    'serial': ('base', 'PIJIT_SERIAL_PREPARATION'),
    'labels': ('base', 'PIJIT_TOKENIZER_REVISION'),
    'continuation': ('labels', 'PIJIT_CONTINUATION_CACHE'),
    'codebook': ('base', 'PIJIT_DISABLE_CODEBOOK'),
    'routing': ('codebook', 'PIJIT_LOCAL_ROUTING'),
    'directory': ('base', 'PIJIT_DIRECTORY_GUARD'),
    'batch': ('base', 'PIJIT_BATCH_TOOLS'),
    'context': ('batch', 'PIJIT_PLAN_CONTEXT'),
}
SOURCES = ['benchmarks/benchmark_mechanism_ablation.py', 'benchmarks/benchmark_codebook_agent.py',
           'benchmarks/compare_pijit_presets.py', 'benchmarks/benchmark_schema_jit_agent.py',
           'benchmarks/benchmark_general_pijit.py', 'benchmarks/expanded_agent_scenarios.py',
           'benchmarks/native_pi_trace.ts', 'integrations/pijit/bridge.py',
           'integrations/pijit/extension.ts', 'integrations/pijit/launch.mjs',
           'deploy/jit_codebook.py', 'deploy/schema_actions.py', 'deploy/preset_edits.py',
           'deploy/direct_structural_protocol.py', 'deploy/compact_structural_protocol.py',
           'deploy/structural_edit_protocol.py']


def configurations(revision):
    base = dict.fromkeys(FLAGS, '0')
    base.update(PIJIT_TOKENIZER_REVISION='', PIJIT_DISABLE_CODEBOOK='1')
    configs = {'base': base}
    for arm, (parent, flag) in EDGES.items():
        value = revision if flag == 'PIJIT_TOKENIZER_REVISION' else '0' if flag == 'PIJIT_DISABLE_CODEBOOK' else '1'
        configs[arm] = {**configs[parent], flag: value}
    return {'native': base.copy(), **configs}


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    configs = configurations(args.tokenizer_revision)
    os.environ['PIJIT_URL'] = args.url
    sources = out / 'sources'
    sources.mkdir()
    hashes = {}
    for source in SOURCES:
        shutil.copyfile(ROOT / source, sources / Path(source).name)
        hashes[source] = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    manifest = {'arms': list(configs), 'configurations': configs, 'comparisons': EDGES,
                'cases': CASES, 'repeats': args.repeats, 'rounds': 2, 'seed': 922,
                'source_sha256': hashes, 'tokenizer_revision': args.tokenizer_revision,
                'timing': 'Pi startup through exit plus independent final oracle; in-loop failures, recovery and tests included. Fixture reset, post-run audits excluded.',
                'pairing': 'Fresh arm/case/repeat state; restore identical files at same absolute path for warm round, retaining runtime state only. Fresh Agent sessions. No retries or discarded formal attempts.',
                'limitations': 'Six synthetic development task families, shared backend. Native is an ordinary tools API reference on the patched server, not a single-factor edge. The base is compact-tool Agent with codebook and optional optimizations disabled, but parallel preparation enabled. Serial edge measures removal of parallel preparation. Schema/JIT and direct classification are tested separately at edit/service boundaries. Single-factor effects are conditional on the specified parent; they are not additive.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    (out / 'scenarios.json').write_text(json.dumps({c: SCENARIOS[c] for c in CASES}, indent=2))
    rng, rows = random.Random(922), []
    with tempfile.TemporaryDirectory(prefix='tair-ablation-') as temp:
        for repeat in range(args.repeats):
            for name in CASES:
                scenario = SCENARIOS[name]
                for round_ in (1, 2):
                    order = list(configs)
                    rng.shuffle(order)
                    for arm in order:
                        root = Path(temp) / f'{repeat}-{name}-{arm}'
                        project, state = root / 'project', root / 'state'
                        if project.exists():
                            shutil.rmtree(project)
                        project.mkdir(parents=True)
                        for path, content in scenario['files'].items():
                            target = project / path
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(content)
                        folder = out / f'{repeat}-{name}-{arm}-{round_}'
                        folder.mkdir()
                        (folder / 'configuration.json').write_text(json.dumps(configs[arm], indent=2))
                        row = b.attempt(project, state, folder, 'native' if arm == 'native' else 'generation',
                                        0, args.timeout, scenario=scenario, env_overrides=configs[arm])
                        row.update(arm=arm, case=name, repeat=repeat, round=round_, order=order)
                        try:
                            row['test_integrity'] = test_integrity(project, name, scenario)
                        except (OSError, SyntaxError):
                            row['test_integrity'] = False
                        row['passed'] &= row['test_integrity']
                        (folder / 'final-result.json').write_text(json.dumps(row, indent=2))
                        for filename in ('codebook.json', 'jit-actions.json'):
                            for book in state.glob('workspaces/*/' + filename):
                                shutil.copyfile(book, folder / filename)
                        shutil.copytree(project, folder / 'project-after', ignore=shutil.ignore_patterns('__pycache__'))
                        rows.append(row)
                        with (out / 'rows.jsonl').open('a') as stream:
                            stream.write(json.dumps(row) + '\n')
                        print(json.dumps({'case': name, 'arm': arm, 'round': round_, 'passed': row['passed'],
                                          'seconds': row['validated_seconds'], 'complete_usage': row['usage_complete']}), flush=True)
    assert all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest for path, digest in hashes.items()), 'Sources changed during experiment'
    summary = b.summarize(rows)
    summary['limitations'] = manifest['limitations']
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    return int(not all(row['passed'] and row['usage_complete'] for row in rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--tokenizer-revision', required=True)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=120)
    raise SystemExit(main(parser.parse_args()))
