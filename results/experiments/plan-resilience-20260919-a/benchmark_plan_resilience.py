"""256-entry shortlist, bounded rejection recovery and C2 concurrent admission."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
import adaptive_plan as runtime
from benchmark_engine_adaptive import CONTRACTS, verify


def run(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for source in [Path(__file__),ROOT/'deploy/adaptive_plan.py']:
        shutil.copyfile(source,out/source.name)
    raw=out/'requests';raw.mkdir()
    def transport(url,route,body):
        record=raw/(uuid.uuid4().hex+'.json')
        if route!='/tokenize':record.write_text(json.dumps(dict(route=route,request=body),indent=2))
        response=runtime.post(url,route,body)
        if route!='/tokenize':record.write_text(json.dumps(dict(route=route,request=body,response=response),indent=2))
        return response
    seed=json.loads((ROOT/'results/experiments/engine-adaptive-20260919-b/books/0-engine.json').read_text())['entries']
    book=runtime.PlanBook(out/'large-book.json')
    modules=[]
    for entry in seed:
        path=out/'seed-check.py';path.write_text(entry['source']);verify(path,entry['contract'])
        modules.append((entry['contract'],entry['source'],'Rechecked earlier generated artifact against behavior suite'))
    for i in range(251):
        source=f'def constant_{i}():\n    return {i}\n'
        import ast
        tree=ast.parse(source);assert tree.body[0].body[0].value.value==i
        modules.append((f'Expose constant_{i}(), returning integer {i}. No file I/O.',source,'AST constant-return audit for synthetic distractor'))
    book.admit(modules);assert len(book.load())==256
    rows=[]
    for kind in ('utf8','utf16','binary','exclusive','parents'):
        contracts={'module.py':CONTRACTS[kind]};directory=out/'large'/kind
        start=time.perf_counter()
        result=runtime.run_plan(args.url,'Implement the requested module.',contracts,directory,book,verify,transport)
        assert result['reuse_steps']==1 and not result['recovered']
        assert len(result['attempts'][0]['candidate_ids'])==15
        rows.append(dict(case='large_'+kind,seconds=time.perf_counter()-start,passed=True,result=result))
    # Explicit fault injection: source was valid for an older contract, catalog
    # metadata now falsely advertises the new contract. This is NOT normal admission.
    faulty=runtime.PlanBook(out/'faulty-book.json')
    source=next(e['source'] for e in seed if e['contract']==CONTRACTS['utf8'])
    identity,=faulty.admit([(CONTRACTS['parents'],source,'INJECTED incorrect metadata for rejection test')])
    contracts={'module.py':CONTRACTS['parents']};start=time.perf_counter()
    result=runtime.run_plan(args.url,'Implement automatic parent directory creation.',contracts,out/'recovery',faulty,verify,transport)
    # Either model detects mismatch before execution, or validator forces one recovery.
    assert len(result['attempts'])<=2
    verify(out/'recovery/module.py',CONTRACTS['parents'])
    rows.append(dict(case='fault_injection',seconds=time.perf_counter()-start,passed=True,result=result))
    if result['recovered']:
        assert identity not in {e['id'] for e in faulty.candidates('',contracts)}
    # A deterministic validator fault proves the retry path even when the model
    # catches the corrupted metadata above before it reaches execution.
    retry_book=runtime.PlanBook(out/'retry-book.json')
    correct=next(e for e in seed if e['contract']==CONTRACTS['parents'])
    retry_book.admit([(correct['contract'],correct['source'],'Earlier artifact reverified')])
    verifications=[]
    def reject_once(path,contract):
        verifications.append(str(path))
        if len(verifications)==1:
            raise ValueError('INJECTED one-time validator rejection')
        return verify(path,contract)
    start=time.perf_counter()
    retry=runtime.run_plan(args.url,'Implement automatic parent directory creation.',contracts,out/'forced-recovery',retry_book,reject_once,transport)
    assert retry['recovered'] and len(retry['attempts'])==2 and len(verifications)==2
    assert retry['attempts'][1]['candidate_ids']==[]
    rows.append(dict(case='forced_validator_recovery',seconds=time.perf_counter()-start,passed=True,result=retry))
    concurrent=runtime.PlanBook(out/'concurrent-book.json')
    def job(kind):
        start=time.perf_counter()
        result=runtime.run_plan(args.url,'Create this module.',{'module.py':CONTRACTS[kind]},out/'concurrent'/kind,concurrent,verify,transport)
        return dict(case='concurrent_'+kind,seconds=time.perf_counter()-start,passed=True,result=result)
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=list(pool.map(job,['utf16','binary']))
    concurrent_seconds=time.perf_counter()-start
    assert {e['contract'] for e in concurrent.load()}=={CONTRACTS['utf16'],CONTRACTS['binary']}
    rows.extend(jobs)
    (out/'results.json').write_text(json.dumps(dict(rows=rows,concurrent_wall_seconds=concurrent_seconds,
        method='Large catalog contains five earlier generated, reverified entries plus 251 synthetic constant-function distractors. Explicit metadata corruption checks rejection; C2 shares an initially empty book. These are focused integration checks, not a production load benchmark.'),indent=2))
    print(json.dumps(dict(passed=len(rows),cases=len(rows),concurrent_wall_seconds=concurrent_seconds,
                         recovery_requests=len(result['attempts']),recovered=result['recovered'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True)
    run(p.parse_args())
