import json,sys,hashlib
from pathlib import Path
from collections import defaultdict
out=Path(sys.argv[1]); rows=[json.loads(l) for l in (out/'rows.jsonl').read_text().splitlines()]
manifest=json.loads((out/'manifest.json').read_text())
expected={(a,c,k,r) for a in manifest['arms'] for c in manifest['cases'] for k in range(manifest['repeats']) for r in range(1,manifest['rounds']+1)}
assert {(r['arm'],r['case'],r['repeat'],r['round']) for r in rows}==expected
assert len(rows)==len(expected)
for path,digest in manifest['source_sha256'].items():
 assert hashlib.sha256((out/'sources'/path).read_bytes()).hexdigest()==digest,path
reviewpath=out/'requested-test-review.json'
reviews={r['case']:r for r in json.loads(reviewpath.read_text())} if reviewpath.exists() else {}
for row in rows:
 row['raw_passed']=row['passed']
 if row['case']=='summary_bug':
  review=reviews[f"{row['repeat']}-{row['case']}-{row['arm']}-{row['round']}"]
  row['passed'] &= review['requested_tests_effective'] is True

def summarize(group):
 records=[m for r in group for m in r['metrics']]
 return {'tasks':len(group),'passed':sum(r['passed'] for r in group),'raw_passed':sum(r['raw_passed'] for r in group),'seconds':sum(r['validated_seconds'] for r in group),
 'timeouts':sum(r['timed_out'] for r in group),'usage_complete':all(r['usage_complete'] for r in group),
 'multi_tool_responses':sum(r['multi_tool_responses'] for r in group),'cache_hits':sum(m.get('cache_hit',False) for m in records),
 'bound_reuse_hits':sum(m.get('bound_reuse_hit',False) for m in records),'local_routes':sum(bool(m.get('local_route')) for m in records),
 **{k:sum(m['accounting'].get(k,0) for m in records) for k in ('inference_requests','known_input_tokens','known_generated_argument_tokens','known_classification_control_records','unknown_usage_requests')}}
summary={a:summarize([r for r in rows if r['arm']==a]) for a in manifest['arms']}
pairs={}
for before,after in [('native_single','native_multi'),('native_multi','tair'),('tair_no_book','tair'),('native_multi','hybrid'),('tair','hybrid'),('hybrid_no_book','hybrid')]:
 if before not in summary or after not in summary:continue
 index={(r['case'],r['repeat'],r['round']):r for r in rows if r['arm']==before}
 matched=[(index[r['case'],r['repeat'],r['round']],r) for r in rows if r['arm']==after]
 groups={'all':matched,'both_passed':[(x,y) for x,y in matched if x['passed'] and y['passed']],
 'warm_both_passed':[(x,y) for x,y in matched if x['passed'] and y['passed'] and y['round']>1]}
 pair={}
 for label,items in groups.items():
  a=sum(x['validated_seconds'] for x,y in items);b=sum(y['validated_seconds'] for x,y in items)
  pair[label]={'pairs':len(items),'before_seconds':a,'after_seconds':b,'saved_seconds':a-b,'saved_percent':100*(a-b)/a if a else None}
 pairs[before+' -> '+after]=pair
native=[]
for folder in out.glob('*/native-inference.jsonl'):
 arm=next(a for a in ('native_single','native_multi') if a in folder.parent.name)
 events=[json.loads(l) for l in folder.read_text().splitlines()]
 requests=[e for e in events if e['event']=='request']
 assert all(e['payload'].get('parallel_tool_calls')==(arm=='native_multi') for e in requests)
 native.append({'task':folder.parent.name,'requests':len(requests),'parallel_tool_calls':arm=='native_multi'})
result={'arms':summary,'comparisons':pairs,'by_case':{c:{a:summarize([r for r in rows if r['case']==c and r['arm']==a]) for a in manifest['arms']} for c in manifest['cases']},'failures':[{k:r[k] for k in ('arm','case','repeat','round','raw_passed','passed','timed_out','validation')} for r in rows if not r['passed']], 'native_payload_checks':native,
 'limitations':'Development tasks, one trajectory per cell; same shared server and different planner protocols. Known usage is a lower bound for interrupted requests. Pairwise successful subsets do not replace all-attempt correctness. Repository tasks are modifications to pinned CPython Tools/scripts, not a full upstream test run. Third round uses new parameter bindings only for variant tasks; other tasks repeat. All timing includes Agent tools, recovery, final response and external oracle.'}
(out/'analysis.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'arms':summary,'comparisons':pairs},indent=2))
