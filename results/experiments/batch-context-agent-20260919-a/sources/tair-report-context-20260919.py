import json,sys
from pathlib import Path
p=Path(sys.argv[1])
rows=[json.loads(x) for x in (p/'rows.jsonl').read_text().splitlines()]
s=json.loads((p/'summary.json').read_text())['arms']
prof={}
for arm in s:
 rr=[r for r in rows if r['arm']==arm]; mm=[m for r in rr for m in r['metrics']]
 errors=blocked=multi_messages=0
 for r in rr:
  f=p/f"{r['repeat']}-{r['case']}-{r['arm']}-{r['round']}"/'events.jsonl'
  for line in f.read_text().splitlines():
   e=json.loads(line)
   if e.get('type')!='message_end':continue
   m=e['message']
   if m['role']=='assistant':multi_messages+=sum(c['type']=='toolCall' for c in m.get('content',[]))>1
   if m['role']=='toolResult':
    errors+=bool(m.get('isError'))
    blocked+=any(c.get('text','').startswith('Plan stopped:') for c in m.get('content',[]))
 prof[arm]={'outer_model_requests':sum(m['accounting']['inference_requests'] for m in mm if m['action']=='chat'),
 'plans':sum(bool(m.get('batch_tool_count')) for m in mm),'multiple_operation_plans':sum(m.get('batch_tool_count',0)>1 for m in mm),
 'planned_operations':sum(m.get('batch_tool_count',0) for m in mm),'max_plan_length':max([m.get('batch_tool_count',0) for m in mm] or [0]),
 'observed_multi_tool_responses':multi_messages,'tool_result_errors':errors,'blocked_steps':blocked,
 'by_case':{case:{'seconds':sum(r['validated_seconds'] for r in rs),'requests':sum(m['accounting']['inference_requests'] for r in rs for m in r['metrics']),
 'passed':sum(r['passed'] for r in rs),'tasks':len(rs)} for case in sorted({r['case'] for r in rr}) for rs in [[r for r in rr if r['case']==case]]}}
(p/'batch-profile.json').write_text(json.dumps(prof,indent=2)+'\n')
lines=['# Multi-operation Agent experiment ('+p.name+')','',
'Real Pi 0.85.1 on the existing 6 x RTX 5090 service. Three scenarios: CLI properties, alias, and a function fix with requested new tests. Independent cold/warm pairs restore source and keep only per-arm runtime state. Fresh Agent sessions, interleaved arm order, no benchmark retries.','',
'## Full task comparison','','| Arm | Passed/tasks | Total seconds | Outer model requests | All inference requests | Generated tokens | Control records | Input tokens | Edit hits |',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for arm in ['native','batched','contextual']:
 r=s[arm];lines.append(f"| {arm} | {r['passed']}/{r['tasks']} | {r['wall_seconds']:.2f} | {prof[arm]['outer_model_requests']} | {r['inference_requests']} | {r['known_generated_argument_tokens']} | {r['known_classification_control_records']} | {r['known_input_tokens']} | {r['cache_hits']} |")
lines+=['','Total time includes Pi startup, planning, tool execution, in-loop tests/recovery, final reply and independent behavior oracle. Nested compact-edit inference is included. Post-run artifact unittest reruns are outside measured task time. Failed tasks remain in totals and are not equivalent completed work.','',
'## Observed batching','','| Arm | Plans | Multi-operation plans | Maximum steps | Multi-tool responses | Tool errors including recovery | Blocked later steps |','|---|---:|---:|---:|---:|---:|---:|']
for arm in ['native','batched','contextual']:
 q=prof[arm];lines.append('| '+arm+' | '+' | '.join(str(q[k]) for k in ['plans','multiple_operation_plans','max_plan_length','observed_multi_tool_responses','tool_result_errors','blocked_steps'])+' |')
lines+=['','These are executed plan envelopes, not a promise that the entire task needs one inference. Plans themselves are generated; the existing compact-edit codebook is reused only inside compact_edit. Source discovery and final result interpretation may need further turns.','',
'## Scenario totals','','| Scenario | Native seconds / requests | Batched seconds / requests | Contextual seconds / requests |','|---|---:|---:|---:|']
for case in prof['native']['by_case']:
 lines.append('| '+case+' | '+' | '.join(f"{prof[a]['by_case'][case]['seconds']:.2f} / {prof[a]['by_case'][case]['requests']}" for a in ['native','batched','contextual'])+' |')
lines+=['','## Failures','']
failed=[r for r in rows if not r['passed']]
if not failed:lines.append('Every full task passed the behavior oracle and original/additional test integrity check.')
for r in failed:lines.append(f"- {r['repeat']}-{r['case']}-{r['arm']}-{r['round']}: behavior passed={r['validation']['passed']}; requested-test integrity passed={r['test_integrity']}; no retry or removal.")
lines+=['','## Controls and limits','',
'Native is the ordinary tools API on the same patched vLLM service, not a separate unpatched server. It retains the previous harness settings including parallel_tool_calls=false. Batched uses the prior multi-operation client with tokenizer caches and directory guard. Contextual adds a bounded filename inventory and observed-file edit restrictions, forbids empty edit spans, and defers replacement of unread existing files. Both use the same inner codebook and bypass the local single-clause dispatcher. It wraps standard Pi tools for sequential execution and blocks remaining steps after failure; successful earlier steps are not rolled back. Tool hooks remain active.','',
'Both TAIR arms replace supported individual outer choices with the plan envelope (1..8 operations) and final reply; unsupported custom tools remain separate. Context gathering, failed/deferred generations and all recovery are included. This is an implementation comparison, not an isolated ablation of individual constraints. All actual runtime sources are archived per run. Prompts, grammar and control granularity differ, so this is an implementation comparison, not an isolated claim about classification speed.','',
'Only a small handcrafted workload on a shared backend is covered. Counts, correctness, cold/warm timing and generated tokens are separate. Compile-only edit admission does not establish semantics; final behavior and test-integrity checks are independent. A tool error recovered inside an otherwise successful task remains visible in the batch profile.','',
'`rows.jsonl`, `final-result.json`, raw Pi events, source snapshots and `batch-profile.json` contain the accounting. `verification.json`, `environment.json`, engine classification events and independent unittest reruns provide the post-run audit. Probe evidence in the separate batch-tools-execution-20260919 archive uses a mocked provider and real Pi tools; it is not a GPU performance result.']
(p/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(prof))
