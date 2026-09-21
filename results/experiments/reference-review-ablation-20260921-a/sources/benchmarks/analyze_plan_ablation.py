"""Independently recheck and compare native, plan-only, and codebook arms.

Usage: python benchmarks/analyze_plan_ablation.py EXPERIMENT_NAME OUTPUT_JSON
"""
import json,statistics,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
output=Path(sys.argv[2])
subprocess.run([sys.executable,str(root/'benchmarks/summarize_plan_experiment.py'),sys.argv[1],str(output)],check=True,stdout=subprocess.DEVNULL)
p=root/'results/experiments'/sys.argv[1]
rows=json.loads((p/'report.json').read_text());summary=json.loads(output.read_text())
assert {'native','tair_no_reuse','tair'}==set(summary['arms'])
summary['phase_groups']={}
for phase in sorted({r['phase'] for r in rows}):
 summary['phase_groups'][phase]={}
 for arm in summary['arms']:
  rs=[r for r in rows if r['arm']==arm and r['phase']==phase]
  summary['phase_groups'][phase][arm]={k:sum(r[k] for r in rs) for k in ['passed','seconds','known_generated_argument_tokens','inference_requests','tool_errors']}
  summary['phase_groups'][phase][arm]['tasks']=len(rs)
for arm in summary['arms']:
 rs=[r for r in rows if r['arm']==arm]
 summary['arms'][arm]['median_seconds']=statistics.median(r['seconds'] for r in rs)
 ms=[m for r in rs for m in r['metrics']]
 if arm!='native':
  chats=[m for m in ms if m.get('action')=='chat' and m.get('generic_plan')]
  assert chats and all(m.get('plan_reuse_enabled')==(arm!='tair_no_reuse') for m in chats)
  assert all(m.get('candidate_count')==0 and not m.get('cache_hit') for m in chats) if arm=='tair_no_reuse' else True
  replies=[m for m in chats if m.get('cache_outcome')=='reply']
  summary['arms'][arm]['reply_requests']=len(replies)
  summary['arms'][arm]['reply_http_seconds']=sum(h['seconds'] for m in replies for h in m.get('http_requests',[]))
  summary['arms'][arm]['reply_generated_tokens']=sum(m['accounting']['known_generated_argument_tokens'] for m in replies)
  summary['arms'][arm]['admissions']=sum(m.get('admission_count',0) for m in ms)
  summary['arms'][arm]['runtime_reuse_config_verified']=len(chats)
summary['paired_differences']={}
by={(r['task'],r['arm']):r for r in rows}
for reference,arm in [('native','tair_no_reuse'),('tair_no_reuse','tair')]:
 pairs=[(by[(r['task'],reference)],r) for r in rows if r['arm']==arm]
 summary['paired_differences'][reference+' -> '+arm]={'pairs':len(pairs),'faster_tasks':sum(b['seconds']<a['seconds'] for a,b in pairs),'median_seconds_saved':statistics.median(a['seconds']-b['seconds'] for a,b in pairs),'median_relative_seconds_saved':statistics.median(1-b['seconds']/a['seconds'] for a,b in pairs),'quality_matched_all':all(a['passed'] and b['passed'] for a,b in pairs)}
# Explicit post-hoc sensitivity, not an alternative headline denominator.
pairs=[(by[(r['task'],'native')],r) for r in rows if r['arm']=='tair_no_reuse']
worst=max(pairs,key=lambda pair:pair[0]['seconds'])[0]['task']
summary['posthoc_longest_native_task_sensitivity']={'excluded_task':worst,'note':'Main totals retain every task; this post-hoc view only quantifies outlier influence.','native_seconds':sum(a['seconds'] for a,b in pairs if a['task']!=worst),'plan_no_reuse_seconds':sum(b['seconds'] for a,b in pairs if a['task']!=worst)}
output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['cases','repair_process_audit']},ensure_ascii=False,indent=2))
