"""Infer missing branch indices from uniquely matching pinned continuation lengths."""
from collections import Counter
import hashlib,importlib.util,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main(experiment,tokenizer,output):
    root=ROOT/'results/experiments'/experiment
    path=root/'sources/integrations/pijit/bridge.py'
    for key in list(os.environ):
        if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
    os.environ.update(PIJIT_URL='http://unused',PIJIT_LOCAL_TOKENIZER=str(tokenizer),
                      PIJIT_TOKENIZER_REVISION=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest())
    spec=importlib.util.spec_from_file_location('length_audit_bridge',path);b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
    tools=json.loads((ROOT/'results/experiments/plan-client-profile-20260920-a/catalog.json').read_text())
    results=[]
    for row in json.loads((root/'report.json').read_text()):
        if row['arm']!='tair' or not row.get('timed_out'):continue
        metric=next(m for m in row['metrics'] if m.get('action')=='chat')
        assert metric['first_tool_classification_enabled'] and not metric['recovery_planning']
        for flag in ('reuse_routing','reply_branch_enabled','plan_success_reply_enabled','bash_argv_enabled','write_references_enabled'):
            assert not metric.get(flag),flag
        candidates=[dict(id=str(i),source='',contract='') for i in range(metric['candidate_count'])]
        options=b.tool_plan.branches(tools,candidates)
        # Candidate bytes affect their own continuations; native/general continuations do not use them.
        indices=[*range(len(tools)),len(options)-1]
        tails=[[dict(role='assistant',content=b.LABELS[i]),dict(role='user',content='\n'+b.tool_plan.continuation(i,tools,candidates,options[i]))] for i in indices]
        calibrations=[]
        for context in ([dict(role='user',content='Short calibration')],
                        [dict(role='system',content='Long calibration 雪 '+('words '*100)),dict(role='user',content='Read files then write code.')]):
            _,suffixes=b.continuation_tokens(context,tails)
            calibrations.append(suffixes)
        assert calibrations[0]==calibrations[1]
        counts=Counter(x['token_count'] for x in metric['local_tokenization'] if x['token_count']>1)
        assert sum(counts.values())==len(options)+1
        prefix=min(counts);counts.subtract([prefix]);counts=+counts
        known={i:prefix+len(tail) for i,tail in zip(indices,calibrations[0])}
        known_counts=Counter(known.values())
        assert all(counts[n]>=v for n,v in known_counts.items())
        candidate_counts=counts-known_counts
        http=next(h for h in metric['http_requests'] if h['route']=='/v1/openjev/toolcall')
        selected=http['input_tokens'];matches=[i for i,n in known.items() if n==selected]
        assert len(matches)==1 and candidate_counts[selected]==0
        index=matches[0]
        results.append(dict(task=row['task'],arm=row['arm'],prefix_tokens=prefix,selected_input_tokens=selected,
            inferred_wire_index=index,inferred_branch='general' if index==len(options)-1 else 'tool:'+tools[index]['name'],
            known_branch_input_tokens={str(i):n for i,n in known.items()},unassigned_candidate_input_tokens=list(candidate_counts.elements()),
            inference_caveat='Index inferred from a unique token-length match with calibrated suffix invariance; original decision index was not recorded.',
            request_started_at=http['started_at'],generated_tokens=http['generated_argument_tokens']))
    report=dict(experiment=experiment,results=results,method='Offline only: frozen source, pinned tokenizer, two calibration contexts, recorded full-input length multiset. No model calls or elapsed-time claims.',
                frozen_bridge_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),tokenizer_revision=os.environ['PIJIT_TOKENIZER_REVISION'])
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]))
