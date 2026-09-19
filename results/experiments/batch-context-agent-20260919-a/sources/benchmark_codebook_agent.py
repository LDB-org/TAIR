"""Full Pi loops with default learned codebook, without preset/schema/exact replay flags."""
import argparse
import ast
import json
import os
from pathlib import Path
import random
import shutil
import tempfile

from benchmark_schema_jit_agent import SCENARIOS, ROOT, b


def test_integrity(project, name, scenario):
    files = {path: text for path, text in scenario['files'].items() if path.startswith('test')}
    if name != 'summary_bug':
        return all((project/path).read_text() == text for path, text in files.items())
    # This task explicitly requests new tests while retaining the original cases.
    def methods(text):
        return {(c.name, f.name): ast.dump(f, include_attributes=False)
                for c in ast.walk(ast.parse(text)) if isinstance(c, ast.ClassDef)
                for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test')}
    for path, text in files.items():
        original, current = methods(text), methods((project/path).read_text())
        if any(current.get(key) != value for key, value in original.items()) or len(current) <= len(original):
            return False
    return True


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['PIJIT_URL'] = args.url
    for key in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_LOCAL_ROUTING',
                'PIJIT_CONTINUATION_CACHE', 'PIJIT_DIRECTORY_GUARD', 'PIJIT_TOKENIZER_REVISION', 'PIJIT_BATCH_TOOLS', 'PIJIT_PLAN_CONTEXT'):
        os.environ.pop(key, None)
    arms = ['native', 'c4', 'optimized'] if args.outer_optimized else ['native', 'generation', 'c4']
    if args.batch_comparison:
        arms = ['native', 'optimized', 'batched']
    if args.plan_context_comparison:
        arms = ['native', 'batched', 'contextual']
    (out/'manifest.json').write_text(json.dumps({'arms': arms, 'rounds': 2, 'repeats': args.repeats,
        'scenarios': SCENARIOS, 'seed': 921, 'outer_optimized': args.outer_optimized,
        'tokenizer_revision': args.tokenizer_revision,
        'batch_comparison': args.batch_comparison,
        'plan_context_comparison': args.plan_context_comparison,
        'contextual_arm': 'Batched with bounded root filename inventory, observed-file edit grammar, nonempty edits, and deferred writes to unread existing files; context gathering and deferred generations included.',
        'batched_arm': 'Same tokenizer caches and directory guard as optimized, but replace single-tool outer choices with a 1..8-operation plan and final reply; bypass local single-clause dispatcher; sequential Pi execution, stop remaining steps on error. Plan generation is included in time and tokens; plans themselves are not learned.',
        'method': 'real Pi 0.85.1; fresh sessions; restore original project before warm round; persist runtime state; no schema/preset/exact replay; optimized arm enables batched explicit-clause routing, revision-pinned tokenizer caches and directory guard; end-to-end includes planning, tools, tests, recovery and final answer; shared remote backend over SSH'}, indent=2))
    sources = out/'sources'
    sources.mkdir()
    for path in ['benchmarks/benchmark_codebook_agent.py', 'benchmarks/compare_pijit_presets.py',
                 'benchmarks/benchmark_schema_jit_agent.py', 'benchmarks/benchmark_general_pijit.py',
                 'benchmarks/native_pi_trace.ts', 'integrations/pijit/bridge.py',
                 'integrations/pijit/extension.ts', 'integrations/pijit/launch.mjs',
                 'deploy/jit_codebook.py', 'deploy/schema_actions.py',
                 'deploy/direct_structural_protocol.py', 'deploy/compact_structural_protocol.py',
                 'deploy/structural_edit_protocol.py']:
        shutil.copyfile(ROOT/path, sources/Path(path).name)
    rng = random.Random(921)
    rows = []
    with tempfile.TemporaryDirectory(prefix='tair-expanded-agent-') as temp:
        for repeat in range(args.repeats):
            for name, scenario in SCENARIOS.items():
                for round_ in (1, 2):
                    order = list(arms)
                    rng.shuffle(order)
                    for arm in order:
                        root = Path(temp)/f'{repeat}-{name}-{arm}'
                        project, state = root/'project', root/'state'
                        if project.exists():
                            shutil.rmtree(project)
                        project.mkdir(parents=True)
                        for path, text in scenario['files'].items():
                            (project/path).write_text(text)
                        folder = out/f'{repeat}-{name}-{arm}-{round_}'
                        folder.mkdir()
                        for key in ('PIJIT_LOCAL_ROUTING', 'PIJIT_CONTINUATION_CACHE', 'PIJIT_DIRECTORY_GUARD'):
                            os.environ[key] = str(int(arm in ('optimized', 'batched', 'contextual')))
                        os.environ['PIJIT_BATCH_TOOLS'] = str(int(arm in ('batched', 'contextual')))
                        os.environ['PIJIT_PLAN_CONTEXT'] = str(int(arm == 'contextual'))
                        if arm in ('optimized', 'batched', 'contextual'):
                            os.environ['PIJIT_TOKENIZER_REVISION'] = args.tokenizer_revision
                        else:
                            os.environ.pop('PIJIT_TOKENIZER_REVISION', None)
                        row = b.attempt(project, state, folder, arm, 0, args.timeout, scenario=scenario)
                        row.update(case=name, repeat=repeat, round=round_, order=order)
                        row['tests_unchanged'] = all((project/path).read_text()==text for path,text in scenario['files'].items() if path.startswith('test'))
                        row['test_integrity'] = test_integrity(project, name, scenario)
                        row['passed'] &= row['test_integrity']
                        (folder/'final-result.json').write_text(json.dumps(row, indent=2))
                        for book in state.glob('workspaces/*/codebook.json'):
                            shutil.copyfile(book, folder/'codebook.json')
                        shutil.copytree(project, folder/'project-after', ignore=shutil.ignore_patterns('__pycache__'))
                        rows.append(row)
                        with (out/'rows.jsonl').open('a') as stream:
                            stream.write(json.dumps(row)+'\n')
                        print(json.dumps({'case':name,'arm':arm,'round':round_,'passed':row['passed'],
                            'seconds':row['validated_seconds'],'hits':sum(bool(m.get('cache_hit')) for m in row['metrics']),
                            'complete_usage':row['usage_complete']}), flush=True)
    summary = b.summarize(rows)
    summary['limitations'] = 'Three small coding tasks, cold/warm pairs, real Pi loop. Different tool catalogs; no general throughput claim. Admission is compile-only; independent final behavioral oracle and original-test integrity determine success. Failed attempts and agent recovery are included. Optimized arm combines routing and transport optimizations; this is not a classifier-only ablation.'
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)
    return 0 if all(row['passed'] and row['usage_complete'] for row in rows) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--url',required=True)
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--timeout',type=float,default=120)
    parser.add_argument('--outer-optimized', action='store_true')
    parser.add_argument('--batch-comparison', action='store_true')
    parser.add_argument('--plan-context-comparison', action='store_true')
    parser.add_argument('--tokenizer-revision')
    args = parser.parse_args()
    if (args.outer_optimized or args.batch_comparison or args.plan_context_comparison) and not args.tokenizer_revision:
        parser.error('--outer-optimized requires --tokenizer-revision')
    raise SystemExit(main(args))
