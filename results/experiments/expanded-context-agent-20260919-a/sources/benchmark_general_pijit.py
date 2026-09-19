"""Real Pi loops on three small coding tasks; presets plus normal tool fallback."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('comparison', ROOT/'benchmarks/compare_pijit_presets.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
SCENARIOS = {
 'mixed_config': {
  'files': {'app.py': '''import argparse

def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--timeout', type=float, default=1.5)
    p.add_argument('--host', default='localhost')
    return p
''', 'test_app.py': '''import unittest
from app import build_parser
class TestConfig(unittest.TestCase):
    def test_defaults(self):
        p=build_parser().parse_args([])
        self.assertEqual((p.workers,p.timeout,p.host),(6,2.5,'localhost'))
    def test_overrides(self):
        p=build_parser().parse_args(['--workers','3','--timeout','0.25','--host','remote'])
        self.assertEqual((p.workers,p.timeout,p.host),(3,0.25,'remote'))
'''},
  'prompt': 'Inspect the Python project. Change the workers default to 6 and timeout default to 2.5. Preserve explicit overrides and the host setting. Run python -m unittest -v, fix any failures, and summarize what changed. Do not change the tests.',
  'check': '''import app
p=app.build_parser()
a=p.parse_args([])
assert (a.workers,a.timeout,a.host)==(6,2.5,'localhost')
a=p.parse_args(['--workers','17','--timeout','0.75','--host','example'])
assert (a.workers,a.timeout,a.host)==(17,0.75,'example')
'''},
 'summary_bug': {
  'files': {'app.py': '''def summarize(values):
    return {'count': len(set(values)), 'total': sum(values), 'mean': sum(values)/len(values), 'min': min(values), 'max': max(values)}
''', 'test_app.py': '''import unittest
from app import summarize
class TestSummary(unittest.TestCase):
    def test_duplicates(self):
        self.assertEqual(summarize([2,2,5])['count'],3)
    def test_empty(self):
        self.assertEqual(summarize([]),{'count':0,'total':0,'mean':None,'min':None,'max':None})
'''},
  'prompt': 'Inspect this project and fix summarize: count must include duplicates; empty input must return count=0,total=0,mean=None,min=None,max=None. Preserve input order and contents and handle negative/floating-point values. Add unittest coverage for negative values and input immutability, keeping existing tests. Run python -m unittest -v and summarize the result.',
  'check': '''from app import summarize
for xs in [[],[2,2,5],[-4,-2],[0.25,1.25,2.5],[9]]:
 before=list(xs)
 expected={'count':len(xs),'total':sum(xs),'mean':sum(xs)/len(xs) if xs else None,'min':min(xs) if xs else None,'max':max(xs) if xs else None}
 assert summarize(xs)==expected
 assert xs==before
from pathlib import Path
assert 'unittest' in Path('test_app.py').read_text()
'''},
 'multifile_feature': {
  'files': {'app.py': '''import argparse

def main():
    p=argparse.ArgumentParser()
    p.add_argument('text')
    args=p.parse_args()
    print(args.text)

if __name__=='__main__':
    main()
''', 'README.md': '# Text CLI\n\nRun python app.py "Hello World" to echo text.\n'},
  'prompt': 'Add an opt-in --slug flag to this CLI. Implement slugify(text) in a new textutil.py module: lowercase text, split on whitespace, join words with hyphens; whitespace-only input returns an empty string. Without --slug preserve the original echo behavior. Update README with an example and add test_app.py unittest coverage for the utility and both CLI modes. Run python -m unittest -v and summarize.',
  'check': '''import subprocess,sys
from pathlib import Path
from textutil import slugify
for text,expected in [('  Hello   WORLD ','hello-world'),('A\\tB\\nC','a-b-c'),('   ',''),('Keep_This','keep_this')]:
 assert slugify(text)==expected
for flags,expected in [([], '  Hello World  \\n'),(['--slug'],'hello-world\\n')]:
 r=subprocess.run([sys.executable,'app.py',*flags,'  Hello World  '],capture_output=True,text=True,timeout=10)
 assert r.returncode==0 and r.stdout==expected,(r.stdout,r.stderr)
assert '--slug' in Path('README.md').read_text()
assert 'unittest' in Path('test_app.py').read_text()
'''},
}


def main(args):
 out=args.out.resolve();out.mkdir(parents=True,exist_ok=False);(out/'sources').mkdir()
 for relative in ['benchmarks/benchmark_general_pijit.py','benchmarks/compare_pijit_presets.py','benchmarks/native_pi_trace.ts','integrations/pijit/bridge.py','integrations/pijit/extension.ts','integrations/pijit/launch.mjs','deploy/preset_edits.py','deploy/jit_codebook.py','deploy/direct_structural_protocol.py','deploy/compact_structural_protocol.py','deploy/structural_edit_protocol.py']:
  shutil.copyfile(ROOT/relative,out/'sources'/Path(relative).name)
 (out/'scenarios.json').write_text(json.dumps(SCENARIOS,indent=2))
 (out/'manifest.json').write_text(json.dumps({'repeats':args.repeats,'seed':20260920,'arms':['native','preset'],'timeout_seconds':120,'tokenizer_revision':os.environ.get('PIJIT_TOKENIZER_REVISION'),'scope':'Three small coding tasks; full Pi read/edit/write/bash/test/reply loops. Native uses stock tools; preset uses same tools plus compact_edit and set_cli_default. Not whole-action classification and not a broad coding benchmark. No prebound correct actions. Cold project/codebook/label cache for each attempt. Normal edit/write fallback and Agent recovery remain allowed and counted.','timing':'Pi process startup through exit plus independent behavior oracle. Fixture creation excluded. In-tool compact/preset validation keeps normal syntax guards without a final-task oracle on intermediate edits. Both arms run the identical independent final behavior oracle; Agent-invoked project tests remain inside Pi wall time.','isolation':'Proxy and CyberEdge frozen; single client, sequential randomized pairs; no service change.'},indent=2))
 rng=random.Random(20260920);rows=[]
 with tempfile.TemporaryDirectory(prefix='pijit-general-state-') as temp:
  for repeat in range(args.repeats):
   for name,scenario in SCENARIOS.items():
    arms=['native','preset'];rng.shuffle(arms)
    for arm in arms:
     folder=out/f'{repeat}-{name}-{arm}';folder.mkdir();project=folder/'project';project.mkdir()
     for filename,content in scenario['files'].items():(project/filename).write_text(content)
     state=Path(temp)/folder.name
     row=b.attempt(project,state,folder,arm,0,120,scenario=scenario)
     row.update(repeat=repeat,case=name,order=arms)
     events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines() if l.strip()]
     row['tool_calls']=[{'name':e.get('toolName'),'error':e.get('isError',False)} for e in events if e.get('type')=='tool_execution_end']
     rows.append(row)
     with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
     print(json.dumps({'repeat':repeat,'case':name,'arm':arm,'passed':row['passed'],'seconds':row['validated_seconds'],'tools':row['tool_calls']}),flush=True)
 summary=b.summarize(rows)
 summary['limitations']='Three small coding tasks, two repeats per task by default; full Pi loops under exclusive load, different tool catalogs/prompts, recovery included. Not a general coding or stable speed claim.'
 (out/'summary.json').write_text(json.dumps(summary,indent=2))


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--repeats',type=int,default=2)
 main(parser.parse_args())
