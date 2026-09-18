from pathlib import Path
import json,statistics
p=Path('results/experiments/bound-action-task-20260918-c')
rows=[json.loads(l) for l in (p/'rows.jsonl').read_text().splitlines()]
assert len(rows)==12
summary={}
for arm in ['native','generate','classify']:
 rr=[r for r in rows if r['arm']==arm]
 s={'n':len(rr),'passed':sum(r['passed'] for r in rr),'mean_validated_seconds':statistics.mean(r['validated_seconds'] for r in rr),'median_validated_seconds':statistics.median(r['validated_seconds'] for r in rr)}
 if arm=='native':
  acc=[m['accounting'] for r in rr for m in r['metrics']]
  s.update(inference_requests=sum(a['inference_requests'] for a in acc),input_tokens=sum(a['known_input_tokens'] for a in acc),generated_tokens=sum(a['known_generated_argument_tokens'] for a in acc),controls=0,unknown_usage=sum(a['unknown_usage_requests'] for a in acc))
 else:
  s.update(inference_requests=len(rr),input_tokens=sum(r['response']['usage']['prompt_tokens'] for r in rr),generated_tokens=sum(r['generated_tokens'] for r in rr),controls=sum(r['control_records'] for r in rr),unknown_usage=0,
   mean_preparation_seconds=statistics.mean(r['preparation_seconds'] for r in rr),mean_service_seconds=statistics.mean((r['response']['metrics']['time_to_first_token_ms']+r['response']['metrics']['generation_time_ms'])/1000 for r in rr),mean_initial_queue_seconds=statistics.mean(r['response']['metrics']['queue_time_ms']/1000 for r in rr),mean_wall_less_initial_queue_seconds=statistics.mean(r['validated_seconds']-r['response']['metrics']['queue_time_ms']/1000 for r in rr))
 summary[arm]=s
(p/'summary.json').write_text(json.dumps(summary,indent=2))
lines=['# Complete bound-action tasks after mixed-batch dtype repair','',
 'Follow-up C: two repeats each of workers default 6 and 8, all starting from 4. Four matched task triples. Independent AST equality and argparse behavior checks preserve explicit overrides. Source read, finite action binding, cold tokenization, inference, application and validation are included in specialized task times. Candidates include fixed values 2/4/6/8/10 and NONE; none is selected locally from the expected answer. Both bound arms share candidate order per pair.', '',
 'The runner explicitly owns reading, validation and DONE. Only edit selection is delegated to the model. This prompt clarification follows pilot B, where one classifier selected NONE. B is retained and not pooled. This selected, very small fixture establishes neither coverage nor general coding quality.', '',
 '| Arm | Correct | Mean task s | Median task s | Inference calls total | Input tokens | Generated tokens | Controls |', '|---|---:|---:|---:|---:|---:|---:|---:|']
for arm,s in summary.items():
 lines.append(f"| {arm} | {s['passed']}/{s['n']} | {s['mean_validated_seconds']:.3f} | {s['median_validated_seconds']:.3f} | {s['inference_requests']} | {s['input_tokens']} | {s['generated_tokens']} | {s['controls']} |")
lines+=['','| Bound arm | Mean preparation s | Mean service s | Mean initial queue s | Mean task minus initial queue s |','|---|---:|---:|---:|---:|']
for arm in ['generate','classify']:
 s=summary[arm];lines.append(f"| {arm} | {s['mean_preparation_seconds']:.3f} | {s['mean_service_seconds']:.3f} | {s['mean_initial_queue_seconds']:.3f} | {s['mean_wall_less_initial_queue_seconds']:.3f} |")
g=summary['generate'];c=summary['classify'];n=summary['native']
lines+=['',f"Observed native/classify mean task ratio: {n['mean_validated_seconds']/c['mean_validated_seconds']:.3f}x. Observed generate/classify model service ratio: {g['mean_service_seconds']/c['mean_service_seconds']:.3f}x.", '',
 'Service = scheduled-to-first plus first-to-last output; excludes initial queue but includes later scheduling. Task-minus-queue is arithmetic subtraction of that initial queue only, not an isolated deployment latency prediction. Classification pays six extra sequential remote label-tokenization calls, cold on each task, deliberately included. Native has no comparable per-stage server metrics in this harness.', '',
 'The native comparison changes orchestration (general Pi read/edit/reply versus specialized single request and deterministic reply). Native startup is included; specialized Python import/interpreter startup is excluded. Model, patched server and task oracle are shared, but prompts/tool catalogs differ. Shared traffic and four pairs prevent attributing the entire observed task ratio to classification or making a stable speed claim. The generate/classify comparison better isolates representation, yet includes their different preparation costs.', '',
 'No retries, failed samples or outliers were removed. All-classification requests are audited for sampler bypass. Runtime maintenance evidence lives in ../bound-action-task-20260918-maintenance/. Run A records the original engine failure; run B records post-fix semantic rejection. Both remain preserved.']
(p/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2))
