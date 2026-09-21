"""Compare fixed old/new plan requests; no inference or tool execution."""
import hashlib,json,os,sys,tempfile
from pathlib import Path
from probe_candidate_binding import load
ROOT=Path(__file__).resolve().parents[1]


def main(tokenizer,output):
    for key in list(os.environ):
        if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
    os.environ.update(PIJIT_URL='http://unused',PIJIT_LOCAL_TOKENIZER=str(tokenizer),
                      PIJIT_TOKENIZER_REVISION=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest())
    old_path=ROOT/'results/experiments/tool-description-dedup-20260921-b/sources/integrations/pijit/bridge.py'
    modules=[load('old_empty_prompt',old_path),load('new_empty_prompt',ROOT/'integrations/pijit/bridge.py')]
    catalog=json.loads((ROOT/'results/experiments/plan-client-profile-20260920-a/catalog.json').read_text())
    rows=[]
    with tempfile.TemporaryDirectory(prefix='tair-empty-prompt-') as temp:
        for scenario in ('empty','warm','disabled','recovery'):
            calls=[]
            for index,b in enumerate(modules):
                b.STATE=Path(temp)/str(index)/scenario
                b.server_plan_budget=lambda:True
                workspace=Path(temp)/'workspace';workspace.mkdir(exist_ok=True)
                task='Create a JSONL parser and check malformed input.'
                os.environ['PIJIT_PLAN_DISABLE_REUSE']='1' if scenario=='disabled' else '0'
                if scenario in ('warm','disabled'):
                    book=b.tool_plan.ToolContentBook(b.paths(str(workspace))/'tool-plan-codebook.sqlite3')
                    book.admit([(task,'def parse(text):\n    return []\n','execution only')])
                def infer(messages,options,**kwargs):
                    tails=[[dict(role='assistant',content=b.LABELS[i]),dict(role='user',content=kwargs['branch_instruction'](i,o))] for i,o in enumerate(options)]
                    prefix,suffixes=b.prepare_continuations(messages+[dict(role='user',content=kwargs['classification_prompt'])],tails)
                    calls.append(dict(messages=messages,options=options,tails=tails,prompt=kwargs['classification_prompt'],prefix=len(prefix),suffixes=[len(s) for s in suffixes]))
                    return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',classification_control_records=1,call=dict(name='plan',arguments=dict(content='fixture')))
                b.infer=infer
                history=[dict(role='user',content=task)]
                if scenario=='recovery':history.append(dict(role='toolResult',isError=True,content='failed'))
                b.generic_plan_chat(dict(cwd=str(workspace),inner_tools=catalog,context=dict(messages=history)))
            old,new=calls
            for key in ('messages','options','tails','suffixes'):assert old[key]==new[key],(scenario,key)
            if scenario in ('warm','recovery'):assert old==new
            else:assert new['prefix']<old['prefix'] and 'For pending writes' not in new['prompt']
            rows.append(dict(scenario=scenario,old_prefix_tokens=old['prefix'],new_prefix_tokens=new['prefix'],saved=old['prefix']-new['prefix'],branches=len(new['options']),schemas_and_continuations_identical=True))
    report=dict(method='Exact local tokenizer, fixed Pi catalog and contexts; no inference, latency or semantic-quality claim.',rows=rows,
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),old_path,ROOT/'integrations/pijit/bridge.py')})
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
