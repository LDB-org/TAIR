import json,statistics
from pathlib import Path
p=Path('results/experiments/outer-agent-20260918-a')
rows=[json.loads(l) for l in (p/'rows.jsonl').read_text().splitlines()]
summary=[]
for case in ('properties','alias','summary_bug','all'):
 for arm in ('native','accelerated','optimized'):
  for round_ in (1,2):
   rs=[r for r in rows if (case=='all' or r['case']==case) and r['arm']==arm and r['round']==round_]
   if not rs:continue
   ms=[m for r in rs for m in r['metrics']];outer=[m for m in ms if m['action']=='chat'];edits=[m for m in ms if m['action']=='edit']
   result={'case':case,'arm':arm,'round':round_,'n':len(rs),'passed':sum(r['passed'] for r in rs),
    'mean_seconds':statistics.mean(r['validated_seconds'] for r in rs),'sample_seconds':[r['validated_seconds'] for r in rs],
    'preparation_seconds':sum(m.get('stage_seconds',{}).get('generation_preparation',0) for m in ms),
    'outer_http_seconds':sum(m.get('stage_seconds',{}).get('generation_http',0) for m in outer),
    'compact_edit_seconds':sum(m['wall_seconds'] for m in edits),
    'outer_requests':sum(m['accounting']['inference_requests'] for m in outer),
    'tokenize_requests':sum(h['route']=='/tokenize' for m in ms for h in m.get('http_requests',[])),
    'continuation_cache_hits':sum(m.get('continuation_cache_hit',False) for m in ms),
    'cache_rejections':sum(bool(m.get('continuation_cache_rejected')) for m in ms),
    'directory_redirects':sum(bool(m.get('directory_read_redirect')) for m in ms),
    'tool_errors':sum(t['error'] for r in rs for t in r['tool_calls']),
    'jit_hits':sum(m.get('jit_hit',False) for m in ms),
    'schema_hits':sum(m.get('schema_hit',False) for m in ms),
    'usage_complete':all(r['usage_complete'] for r in rs),
    **{k:sum(m['accounting'][k] for m in ms) for k in ('inference_requests','known_input_tokens','known_generated_argument_tokens','known_classification_control_records')}}
   summary.append(result)
   print(case,arm,round_,result['n'],round(result['mean_seconds'],3),'prep',round(result['preparation_seconds']/len(rs),3),'outer',result['outer_requests'],'tokenize',result['tokenize_requests'],'errors',result['tool_errors'])
(p/'analysis.json').write_text(json.dumps(summary,indent=2))
