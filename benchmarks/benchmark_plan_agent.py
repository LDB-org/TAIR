"""Real Pi cold/warm/changed-contract loops using pinned upstream dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

from compare_pijit_presets import attempt, summarize

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT/'benchmarks/plan_project_validator.py'
CONTRACTS = {
    'rich': [
        'Create adapter.py exposing render_plain(markup: str)->str. Use the existing project rich.text.Text.from_markup to parse Rich markup and return its plain text with tags removed. Preserve Unicode and spaces. Empty input returns an empty string. No import-time I/O.',
        'Create adapter.py exposing render_plain(markup: str)->str. Use existing rich.text.Text(markup).plain, treating the input literally: preserve ALL markup tags as text, Unicode and spaces. Do NOT parse or strip markup. Empty input returns an empty string. No import-time I/O.'],
    'cpython': [
        'Create adapter.py exposing leaf_names(paths)->list[str]. Use existing upstream_pathlib.PurePosixPath to obtain each input path basename. Return sorted unique basenames (case-sensitive). Preserve Unicode. Do not mutate the input. Empty input returns []. No import-time I/O.',
        'Create adapter.py exposing leaf_names(paths)->list[str]. Use existing upstream_pathlib.PurePosixPath to obtain each basename. Preserve INPUT ORDER and ALL DUPLICATES; DO NOT sort or deduplicate. Preserve Unicode and do not mutate input. Empty input returns []. No import-time I/O.'],
    'tair': [
        'Create adapter.py exposing fingerprint(source: str). Delegate to existing upstream_codebook.syntax_digest(source), which hashes normalized Python AST and returns None for invalid Python. Formatting differences must yield identical hashes. No import-time I/O.',
        'Create adapter.py exposing fingerprint(source: str). Delegate to existing upstream_codebook.digest(source), computing SHA-256 over the EXACT UTF-8 source text. Preserve formatting sensitivity; DO NOT normalize AST or reject invalid Python. No import-time I/O.']}


def prepare(project, name, repositories):
    project.mkdir(parents=True)
    if name == 'rich':
        shutil.copytree(repositories[name]/'rich', project/'rich', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(repositories[name]/'LICENSE', project/'UPSTREAM_LICENSE')
    elif name == 'cpython':
        content = subprocess.check_output(['git','-C',str(repositories[name]),'show','HEAD:Lib/pathlib.py'])
        (project/'upstream_pathlib.py').write_bytes(content)
        shutil.copyfile(repositories[name]/'LICENSE', project/'UPSTREAM_LICENSE')
    else:
        shutil.copyfile(ROOT/'deploy/jit_codebook.py', project/'upstream_codebook.py')
        shutil.copyfile(ROOT/'LICENSE', project/'UPSTREAM_LICENSE')
    (project/'README.md').write_text(f'Adapter integration task for pinned {name}. Existing dependencies are read-only.\n')


def inventory(folder):
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


def run(args):
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    repositories = dict(rich=Path('/tmp/tair-rich-v13.7.1'), cpython=Path('/tmp/tair-cpython-v3.11.9'), tair=ROOT)
    revisions = {name:subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip() for name,path in repositories.items()}
    assert revisions['rich']=='7f580bdcf07a3b269a0e786b6a3aa9c804f393cf'
    assert revisions['cpython']=='de54cf5be371a6f5e2e9f208c38def5f81d3ef02'
    os.environ['PIJIT_URL'] = args.url
    for key in list(os.environ):
        if key.startswith(('PIJIT_', 'TAIR_')) and key not in ('PIJIT_URL','PIJIT_PYTHON'):
            del os.environ[key]
    (out/'manifest.json').write_text(json.dumps(dict(revisions=revisions, contracts=CONTRACTS,
        method='Real Pi 0.85.1, three pinned project dependency adapter tasks, cold/warm/new-contract, three arms interleaved. Both plan arms force the first outer tool call to plan; no-book forces inner generation and still validates/persists. This isolates reuse from the initial-tool policy. Same workspace reset each round, independent arm state, no retries. Native permits multiple tool calls; all outer planners use per-workspace prefix cache namespaces. Inner fused calls keep their own request KV. End-to-end includes outer reasoning/tools/final summary, inner model calls, trusted project validation and independent artifact oracle. Not complete upstream project tests or arbitrary repository maintenance.'),indent=2))
    for relative in ['deploy/adaptive_plan.py','integrations/pijit/bridge.py','integrations/pijit/extension.ts','deploy/native_planner.py',
                     'benchmarks/benchmark_plan_agent.py','benchmarks/plan_project_validator.py','benchmarks/compare_pijit_presets.py']:
        target=out/'sources'/relative; target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
    rows=[]
    with tempfile.TemporaryDirectory(prefix='tair-plan-agent-') as temp:
        for name in CONTRACTS:
            workspace=Path(temp)/name/'project'
            for round_ in range(3):
                arms=['native','plan_no_book','adaptive'];random.Random(20260923+round_).shuffle(arms)
                for arm in arms:
                    if workspace.exists():shutil.rmtree(workspace)
                    prepare(workspace,name,repositories)
                    before=inventory(workspace)
                    state=Path(temp)/name/'state'/arm
                    folder=out/f'{name}-{round_}-{arm}';folder.mkdir()
                    variant=int(round_==2)
                    argv=[sys.executable,'-B',str(VALIDATOR),name,str(variant)]
                    check=argv+['adapter.py','contract',str(workspace)]
                    scenario=dict(primary_file='README.md', prompt=CONTRACTS[name][variant]+
                        ' Modify/create only adapter.py. Do not install packages. Existing dependency files must remain unchanged. '
                        'Use the available tools, run this supplied project behavior check, then give a brief final summary: '+
                        __import__('shlex').join(check),
                        check='import subprocess\nsubprocess.run('+repr(check)+',check=True)\n')
                    env=dict(PIJIT_NATIVE_PLANNER='1',PIJIT_NATIVE_PREFIX_CACHE='1',TAIR_NATIVE_PREFIX_CACHE='1',TAIR_NATIVE_PARALLEL_TOOLS='1',PIJIT_PLANNER_MAX_TOKENS='4096',TAIR_NATIVE_MAX_TOKENS='4096',
                             PIJIT_ADAPTIVE_PLAN='0' if arm=='native' else '1',PIJIT_PLAN_DISABLE_REUSE='1' if arm=='plan_no_book' else '0',PIJIT_PLAN_VERIFY_ARGV=json.dumps(argv))
                    row=attempt(workspace,state,folder,'native' if arm=='native' else 'c4',0,args.timeout,
                                scenario=scenario,env_overrides=env)
                    after=inventory(workspace)
                    intact=all(after.get(path)==digest for path,digest in before.items())
                    only_output=set(after)-set(before)=={'adapter.py'}
                    row.update(arm=arm,case=name,round=round_,protected_intact=intact,only_requested_output=only_output)
                    row['passed'] &= intact and only_output
                    (folder/'inventory-before.json').write_text(json.dumps(before,indent=2))
                    (folder/'inventory-after.json').write_text(json.dumps(after,indent=2))
                    if (workspace/'adapter.py').exists():shutil.copyfile(workspace/'adapter.py',folder/'adapter.py')
                    for book in state.glob('workspaces/*/plan-codebook*'):
                        if book.suffix=='.json':shutil.copyfile(book,folder/book.name)
                    (folder/'final-result.json').write_text(json.dumps(row,indent=2));rows.append(row)
                    with (out/'rows.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
                    print(json.dumps(dict(case=name,round=round_,arm=arm,passed=row['passed'],seconds=row['validated_seconds'],
                                         usage_complete=row['usage_complete'],plans=sum(r['action']=='plan' for r in row['metrics']))),flush=True)
    summary=summarize(rows);summary['limitations']='Three small adapter tasks on real pinned project dependencies, not full upstream suite or production workload. Different tools and model trajectories; all inner and outer calls included.'
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
    return int(not all(r['passed'] and r['usage_complete'] for r in rows))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=120)
    raise SystemExit(run(p.parse_args()))
