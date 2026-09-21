"""Compare lazy source loading with the frozen eager query on synthetic books."""
import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def main(output):
    old_path=ROOT/'results/experiments/single-branch-split-restore-20260921-a/sources/deploy/plan_book.py'
    new_path=ROOT/'deploy/plan_book.py'
    old,new=load('eager_book',old_path),load('lazy_book',new_path)
    rows=[]
    with tempfile.TemporaryDirectory(prefix='tair-book-source-profile-') as directory:
        for count,source_padding in product((100,2000),(64,8192)):
            path=Path(directory)/f'{count}-{source_padding}.sqlite3'
            book=new.PlanBook(path)
            book.admit([(f'read write file task {i}',f'value={i%100}\n#'+('x'*source_padding),'synthetic compile only') for i in range(count)])
            for scenario,kwargs in [('plain',{}),('unique',dict(unique_sources=True)),
                    ('eligible',dict(unique_sources=True,eligible=lambda e:int(e['source'].splitlines()[0].split('=')[1])%5==0)),
                    ('sparse',dict(unique_sources=True,eligible=lambda e:e['source'].startswith('value=0\n'))),
                    ('reject_all',dict(unique_sources=True,eligible=lambda e:False))]:
                expected=None;times={'eager':[],'lazy':[]}
                for repeat in range(12):
                    for arm,module in ([('eager',old),('lazy',new)] if repeat%2==0 else [('lazy',new),('eager',old)]):
                        start=time.perf_counter()
                        result=module.PlanBook(path).candidates('read write file',{},limit=7,**kwargs)
                        elapsed=time.perf_counter()-start
                        if expected is None:expected=result
                        assert result==expected,(count,scenario,arm)
                        if repeat>=2:times[arm].append(elapsed)
                rows.append(dict(entries=count,source_padding_bytes=source_padding,scenario=scenario,matched_entries=len(expected),
                    medians_seconds={arm:statistics.median(v) for arm,v in times.items()},
                    samples_seconds=times,candidate_ids=[e['id'] for e in expected]))
    report=dict(method='Synthetic SQLite books, 64 B and 8 KiB source padding, all contracts match; same database per pair, reversed order, two warmup rounds then ten measured rounds. Retrieval only, no model calls or Agent speed claim.',
        rows=rows,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),old_path,new_path)})
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in row.items() if k not in ('samples_seconds','candidate_ids')} for row in rows],indent=2))


if __name__=='__main__':main(Path(sys.argv[1]))
