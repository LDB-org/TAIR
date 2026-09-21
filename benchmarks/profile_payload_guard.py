"""Measure preparing a literal-payload guard once rather than per candidate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
from tool_plan import payload_guard


def main(output):
    old_path=ROOT/'results/experiments/single-branch-split-restore-20260921-a/sources/deploy/tool_plan.py'
    spec=importlib.util.spec_from_file_location('old_payload_guard',old_path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rows=[]
    for size in (100,20000):
        for count in (24,2000):
            task='Requirements '+('a'*size)+'\n```python\nvalue=1\n```\n'
            entries=[dict(source=f'value={i%5}\n') for i in range(count)]
            expected=None;times={'per_entry':[],'prepared':[]}
            for repeat in range(12):
                for arm in (['per_entry','prepared'] if repeat%2==0 else ['prepared','per_entry']):
                    begin=time.perf_counter()
                    if arm=='prepared':
                        guard=payload_guard(task);result=[guard(entry) for entry in entries]
                    else:result=[old.compatible_payload(entry,task) for entry in entries]
                    elapsed=time.perf_counter()-begin
                    if expected is None:expected=result
                    assert result==expected
                    if repeat>=2:times[arm].append(elapsed)
            rows.append(dict(task_characters=len(task),candidates_inspected=count,accepted=sum(expected),
                             median_seconds={arm:statistics.median(v) for arm,v in times.items()}))
    paths=[Path(__file__),old_path,ROOT/'deploy/tool_plan.py',ROOT/'integrations/pijit/bridge.py']
    report=dict(method='Synthetic task and candidates; guard construction included, alternating order, two warmups and ten measured repetitions; no SQLite, model or full-Agent timing.',rows=rows,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(rows,indent=2))


if __name__=='__main__':main(Path(sys.argv[1]))
