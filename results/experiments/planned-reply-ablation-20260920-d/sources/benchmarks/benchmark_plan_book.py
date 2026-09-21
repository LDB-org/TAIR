"""C1 local synthetic retrieval scaling; no LLM/GPU or semantic-hit claims."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'deploy'))
from plan_book import PlanBook


def measure(book, task, contract, expected):
    samples = []
    for _ in range(31):
        start = time.perf_counter()
        candidates = book.candidates(task, {'module.py': contract})
        samples.append((time.perf_counter() - start) * 1000)
        assert expected in {e['id'] for e in candidates}
        assert len(candidates) <= 15
    return dict(first_ms=samples[0], median_ms=statistics.median(samples[1:]),
                p95_ms=sorted(samples[1:])[28], max_ms=max(samples), samples_ms=samples,
                candidate_count=len(candidates), target_retrieved=True)


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    for path in [Path(__file__), ROOT/'deploy/plan_book.py']:
        shutil.copyfile(path, out/path.name)
    report = dict(python=sys.version, platform=platform.platform(), sqlite=sqlite3.sqlite_version,
                  concurrency=1, inference_requests=0, generated_tokens=0, classification_controls=0,
                  method='Synthetic compiled constant modules; lexical recall only, no semantic classifier. '
                  '31 queries per case, first separate and 30 warm samples. New connection per call, OS cache not flushed. '
                  'Database construction and query timing separate. No old/new or end-to-end speed claim.', rows=[])
    with tempfile.TemporaryDirectory(prefix='tair-book-scale-') as folder:
        for size in [256, 10000, 100000]:
            book = PlanBook(Path(folder)/f'{size}.sqlite3')
            start = time.perf_counter()
            identity, = book.admit([('Read UTF16 files preserving Unicode', 'value=0', 'synthetic compile only')])
            for offset in range(1, size, 1000):
                book.admit([(f'Read counter item{i} files', f'value={i}', 'synthetic compile only')
                            for i in range(offset, min(offset+1000, size))])
            build = time.perf_counter() - start
            assert book.count() == size
            row = dict(entries=size, build_seconds=build, database_bytes=book.path.stat().st_size,
                       selective=measure(book, 'UTF16', 'UTF16', identity),
                       common=measure(book, 'Read files', 'Read UTF16 files preserving Unicode', identity))
            report['rows'].append(row)
            (out/'report.json').write_text(json.dumps(report, indent=2))
            print(json.dumps({k:v for k,v in row.items() if k not in ('selective','common')} |
                             {k:row[k]['median_ms'] for k in ['selective','common']}), flush=True)
    files = sorted(p for p in out.iterdir() if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args().out)
