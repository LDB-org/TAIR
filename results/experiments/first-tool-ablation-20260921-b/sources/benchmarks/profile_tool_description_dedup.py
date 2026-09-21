"""Count exact token IDs before/after removing duplicate tool descriptions; no inference."""
import hashlib,json,os,sys,tempfile
from pathlib import Path
from probe_candidate_binding import load
ROOT=Path(__file__).resolve().parents[1]


def main(tokenizer,output):
    for key in list(os.environ):
        if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
    os.environ.update(PIJIT_URL='http://unused',PIJIT_LOCAL_TOKENIZER=str(tokenizer),PIJIT_PLAN_DISABLE_REUSE='1',
                      PIJIT_TOKENIZER_REVISION=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest())
    b=load('description_bridge',ROOT/'integrations/pijit/bridge.py');b.server_plan_budget=lambda:True
    catalog=json.loads((ROOT/'results/experiments/plan-client-profile-20260920-a/catalog.json').read_text())
    calls=[]
    def infer(messages,options,**kwargs):
        messages=messages+[dict(role='user',content=kwargs['classification_prompt'])]
        tails=[[dict(role='assistant',content=b.LABELS[i]),dict(role='user',content=kwargs['branch_instruction'](i,o))] for i,o in enumerate(options)]
        prefix,suffixes=b.prepare_continuations(messages,tails)
        calls.append(dict(prefix_tokens=len(prefix),suffix_tokens=[len(s) for s in suffixes],messages=messages,options=options,tails=tails))
        return dict(decision=dict(index=len(options)-1),same_engine_session=True,finish_reason='stop',classification_control_records=1,call=dict(name='plan',arguments=dict(content='fixture')))
    b.infer=infer
    with tempfile.TemporaryDirectory(prefix='tair-description-profile-') as temp:
        b.STATE=Path(temp)/'state';workspace=Path(temp)/'workspace';workspace.mkdir()
        for enabled in ['0','1']:
            os.environ['PIJIT_DEDUP_TOOL_DESCRIPTIONS']=enabled
            b.generic_plan_chat(dict(cwd=str(workspace),inner_tools=catalog,context=dict(messages=[dict(role='user',content='Create a JSONL parser and check malformed input.')])) )
    assert calls[0]['options']==calls[1]['options'] and calls[0]['tails']==calls[1]['tails']
    assert calls[0]['suffix_tokens']==calls[1]['suffix_tokens']
    report=dict(method='Identical fixed context and real pinned Pi catalog; exact local tokenizer IDs; no inference or latency claim.',
        original_prefix_tokens=calls[0]['prefix_tokens'],deduplicated_prefix_tokens=calls[1]['prefix_tokens'],
        saved_prefix_tokens=calls[0]['prefix_tokens']-calls[1]['prefix_tokens'],suffix_tokens=calls[0]['suffix_tokens'],
        schemas_and_continuations_identical=True,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'integrations/pijit/bridge.py']})
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
