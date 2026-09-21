"""Recheck artifacts and summarize a completed paired plan experiment.

Usage: python benchmarks/summarize_plan_experiment.py EXPERIMENT_NAME OUTPUT_JSON
"""
import hashlib,json,shlex,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base=root/'results/experiments'
p=base/sys.argv[1]
rows=json.loads((p/'report.json').read_text());manifest=json.loads((p/'manifest.json').read_text())
assert len(rows)==len(manifest['schedule'])
assert [(r['task'], r['arm']) for r in rows] == [tuple(pair) for pair in manifest['schedule']]
summary={'experiment':p.name,'manifest_sha256':hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest(),'arms':{},'cases':[]}
for r in rows:
 folder=p/(r['task']+'-'+r['arm'])
 events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()]
 calls=[e for e in events if e.get('type')=='tool_execution_end']
 job=next(j for j in manifest['cases'] if j['id']==r['task'])
 check=subprocess.run([sys.executable,'-B','-c',job['check']],cwd=folder/'project-after',capture_output=True,timeout=15)
 assert (check.returncode==0)==r['validation']['passed'],r['task']
 item={k:r[k] for k in ['task','arm','phase','passed','seconds','tool_errors','reuse_executed','usage_complete','known_generated_argument_tokens','known_input_tokens','inference_requests']}
 if 'workflow_validation' in r:item['workflow_validation']=r['workflow_validation']
 item.update(artifact_passed=check.returncode==0,no_tool_execution=not calls,last_tool_failed=bool(calls and calls[-1].get('isError')))
 item['pending_assistant_turns']=max(0, sum(e.get('type')=='message_start' and e.get('message',{}).get('role')=='assistant' for e in events)-sum(e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant' for e in events))
 item['closed']=r['passed'] and bool(calls) and not item['last_tool_failed']
 summary['cases'].append(item)
for arm in manifest.get('arms', ['native','tair']):
 rs=[r for r in rows if r['arm']==arm];ms=[m for r in rs for m in r['metrics']];cs=[c for c in summary['cases'] if c['arm']==arm]
 a={k:sum(r[k] for r in rs) for k in ['passed','seconds','known_generated_argument_tokens','known_input_tokens','known_classification_control_records','inference_requests','tool_errors']}
 a['artifact_passed']=sum(c['artifact_passed'] for c in cs)
 a.update(tasks=len(rs),closed=sum(c['closed'] for c in cs),usage_complete=all(r['usage_complete'] for r in rs),correct_reuse=sum(c['reuse_executed'] and c['closed'] for c in cs),tokenize_http=sum(h['route']=='/tokenize' for m in ms for h in m.get('http_requests',[])) if arm!='native' else None,local_tokenizations=sum(len(m.get('local_tokenization',[])) for m in ms))
 a['stages']={key:sum(m.get('stage_seconds',{}).get(key,0) for m in ms) for key in ['generation_preparation','generation_http']} if arm!='native' else None
 a['pending_assistant_turns']=sum(c['pending_assistant_turns'] for c in cs)
 a['token_counts_are_lower_bounds']=not a['usage_complete']
 a['repeat_subset']={k:sum(r[k] for r in rs if r['phase']=='repeat') for k in ['passed','seconds','known_generated_argument_tokens']}
 summary['arms'][arm]=a
summary['artifact_reverification_agrees']=len(rows)
hs=[h for r in rows if r['arm']=='tair' for m in r['metrics'] for h in m.get('http_requests',[]) if h['route']=='/v1/openjev/toolcall']
known=[h for h in hs if isinstance(h.get('cached_prefix_tokens'),int)]
summary['prefix_cache']={'requests':len(hs),'recorded':len(known),'nonzero_requests':sum(h['cached_prefix_tokens']>0 for h in known),'cached_tokens':sum(h['cached_prefix_tokens'] for h in known),'server_modes':sorted({h.get('prefix_cache_mode','unknown') for h in hs})}
summary['repair_process_audit']={}
for arm in manifest.get('arms', ['native','tair']):
 folder=p/('repair_failure-'+arm)
 if not folder.exists():continue
 events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()]
 starts=[e for e in events if e.get('type')=='tool_execution_start']
 first=starts[0] if starts else {}
 step=first.get('args',{}).get('steps',[{}])[0] if arm!='native' else {'name':first.get('toolName'),'arguments':first.get('args')}
 job=next(j for j in manifest['cases'] if j['id']=='repair_failure')
 summary['repair_process_audit'][arm]={'first_action':step,'checker_unchanged':(folder/'project-after/check_calc.py').read_text()==job['files']['check_calc.py']}
 tokens=shlex.split(step.get('arguments',{}).get('command',''))
 if tokens[:2]==['command','--']:
  tokens=tokens[2:]
 first_check=step.get('name')=='bash' and (tokens==['python3','check_calc.py'] or
   len(tokens)==5 and tokens[0]=='cd' and tokens[2:]==['&&','python3','check_calc.py'])
 summary['repair_process_audit'][arm]['requested_check_was_first']=first_check
 for case in summary['cases']:
  if case['arm']==arm and case['task']=='repair_failure':
   case['explicit_workflow_passed']=first_check and summary['repair_process_audit'][arm]['checker_unchanged']
for arm,a in summary['arms'].items():
 a['closed_with_workflow_checks']=sum(c['closed'] and c.get('explicit_workflow_passed',True)
   for c in summary['cases'] if c['arm']==arm)
Path(sys.argv[2]).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='cases'},ensure_ascii=False,indent=2))
print('NONCLOSED',json.dumps([c for c in summary['cases'] if not c['closed']],ensure_ascii=False))
