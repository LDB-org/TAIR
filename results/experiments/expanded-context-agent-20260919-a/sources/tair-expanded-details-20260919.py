import json,sys
from collections import Counter
from pathlib import Path
p=Path(sys.argv[1]); output={}
rows=[json.loads(x) for x in (p/'rows.jsonl').read_text().splitlines()]
for arm in dict.fromkeys(r['arm'] for r in rows):
 errors=[]; plans=[]
 for r in [r for r in rows if r['arm']==arm]:
  case=f"{r['repeat']}-{r['case']}-{arm}-{r['round']}"
  calls={}
  for line in (p/case/'events.jsonl').read_text().splitlines():
   try:event=json.loads(line)
   except ValueError:continue
   if event.get('type')!='message_end':continue
   msg=event['message']
   if msg['role']=='assistant':
    for c in msg.get('content',[]):
     if c.get('type')=='toolCall':calls[c['id']]=c
   if msg['role']=='toolResult' and msg.get('isError'):
    text='\n'.join(c.get('text','') for c in msg.get('content',[]))
    category=('blocked' if text.startswith('Plan stopped:') else
              'missing_path' if 'ENOENT' in text else
              'empty_old_text' if 'oldText' in text and 'empty' in text.lower() else
              'test_failure' if 'FAILED (' in text else 'other')
    errors.append({'case':case,'category':category,'call':calls.get(msg.get('toolCallId')),'text':text})
  plans.extend({'case':case,'known_files':m.get('plan_known_files'),'tools':m.get('batch_tool_names'),
                'deferred_calls':m.get('plan_deferred_calls')} for m in r['metrics'] if m.get('batch_tool_count'))
 signatures=Counter(json.dumps({'case':e['case'],'name':e['call']['name'],'arguments':e['call']['arguments']},sort_keys=True) for e in errors if e['category']!='blocked' and e.get('call'))
 output[arm]={'repeated_failed_calls':sum(n-1 for n in signatures.values()),'largest_failed_call_repeat_count':max(signatures.values(),default=0),'errors_by_category':{k:sum(e['category']==k for e in errors) for k in sorted({e['category'] for e in errors})},'errors':errors,'plans':plans}
(p/'planning-details.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({a:v['errors_by_category'] for a,v in output.items()}))
