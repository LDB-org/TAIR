import json,statistics
from pathlib import Path
root=Path('results/experiments')
p=root/'schema-jit-agent-20260918-b'
rows=[json.loads(l) for l in (p/'rows.jsonl').read_text().splitlines()]
report=[]
for case in ('properties','alias','summary_bug','all'):
 for arm in ('native','generation','accelerated'):
  for round_ in (1,2):
   selected=[r for r in rows if (case=='all' or r['case']==case) and r['arm']==arm and r['round']==round_]
   if not selected:continue
   metrics=[m for r in selected for m in r['metrics']]
   edits=[m for m in metrics if m['action']=='edit']
   report.append({'case':case,'arm':arm,'round':round_,'n':len(selected),'passed':sum(r['passed'] for r in selected),
    'seconds':statistics.mean(r['validated_seconds'] for r in selected),
    'compact_edit_seconds_per_task':sum(m['wall_seconds'] for m in edits)/len(selected),
    'edit_calls':len(edits),'jit_hits':sum(m.get('jit_hit',False) for m in edits),
    'schema_hits':sum(m.get('schema_hit',False) for m in edits),
    'admitted':sum(m.get('jit_admitted',0) for m in edits),
    'admitted_generated':sum(m.get('jit_admission_origin')=='generated' for m in edits),
    'local_routes':sum(bool(m.get('local_route')) for m in metrics),
    'tool_errors':sum(t['error'] for r in selected for t in r['tool_calls']),
    'usage_complete':all(r['usage_complete'] for r in selected),
    **{k:sum(m['accounting'][k] for m in metrics) for k in ['inference_requests','known_input_tokens','known_generated_argument_tokens','known_classification_control_records']}})
(p/'analysis.json').write_text(json.dumps(report,indent=2))
for r in report:
 print(r['case'],r['arm'],r['round'],r['n'],r['passed'],round(r['seconds'],3),'edit',round(r['compact_edit_seconds_per_task'],4),'jit',r['jit_hits'], '/',r['edit_calls'],'schema',r['schema_hits'],'admitted',r['admitted'])
