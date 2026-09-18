"""Cold generation -> verified admission -> classified reuse, with fallback costs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=load('benchmark',ROOT/'benchmarks/evaluate_direct_structural.py')
jit=load('jit',ROOT/'deploy/jit_codebook.py')
CASES=[
 ('cold_workers','Change build_parser so --workers defaults to 6. Preserve overrides and all other behavior.','default_workers_six',6,False),
 ('warm_workers','Use 8 as the default value for --workers in build_parser; keep explicit overrides working.','default_workers_six',8,False),
 ('cold_unicode',b.old.CASES['json_unicode'],'json_unicode',None,False),
 ('warm_unicode','In main, make json.dumps keep Unicode host characters unescaped; retain sorted keys and all other output behavior.','json_unicode',None,False),
 ('novel_nan',b.old.CASES['json_no_nan'],'json_no_nan',None,False),
 ('repeat_nan','In main, ensure json.dumps raises ValueError for NaN and Infinity instead of emitting nonstandard JSON. Keep normal output unchanged.','json_no_nan',None,False),
 ('stale_workers','Set --workers default to 12 in build_parser, preserving overrides and other behavior.','default_workers_six',12,True),
 ('warm_new_version','In build_parser use 14 as the default for --workers; preserve explicit overrides and everything else.','default_workers_six',14,True),
 ('novel_guard',b.old.CASES['timeout_upper_guard'],'timeout_upper_guard',None,False),
 ('repeat_guard','Reject timeout greater than 60 in scan_port by raising ValueError before socket creation. Preserve valid timeout behavior and cleanup.','timeout_upper_guard',None,False),
]


def run(a):
 out=a.out.resolve();out.mkdir();(out/'sources').mkdir()
 for name in ['benchmarks/probe_jit_codebook.py','deploy/jit_codebook.py','deploy/compact_structural_protocol.py','deploy/direct_structural_protocol.py','deploy/structural_edit_protocol.py','benchmarks/evaluate_direct_structural.py','benchmarks/evaluate_region_holdout.py','benchmarks/compare_region_edits.py','deploy/vllm_direct_tools.py']:
  shutil.copyfile(ROOT/name,out/'sources'/Path(name).name)
 prior=ROOT/'results/experiments/pi-combined-structural-20260918-a'
 pristine=out/'pristine';shutil.copytree(prior/'pristine',pristine)
 original=(pristine/'port_scanner.py').read_text()
 book=jit.Codebook();rng=random.Random(20260925)
 manifest={'cases':CASES,'seed':20260925,'gate':{'conditional_probability':0.8,'margin':1.0,'calibrated':False},'admission':'Only one kw edit after oracle task test and 17 regressions; integer values become task-integer binding if unambiguous. Other edits generated but not cached.','fallback':'Empty table, no applicable entry, NONE, low confidence or validation failure -> one generated attempt; no repeated generation. Baseline always generates.','scope':'Sequential related scanner tasks with hand-authored oracle; no arbitrary prompts or learned admission verifier. Classification gate does not inspect expected answers. False acceptance measured before oracle rejection.','timing':'End-to-end includes local binding, tokenize SSH calls, inference SSH calls and validation. Engine scheduled-to-last-output is sum of TTFT and decode intervals; queue separately reported.'}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 tokenized=b.remote(a.host,[('/tokenize',{'model':'/model','prompt':v,'add_special_tokens':False}) for v in 'ABCDEFGHIJKLMNO'])['results']
 assert all(t['status']==200 and len(t['body']['tokens'])==1 for t in tokenized)
 label_ids=[t['body']['tokens'][0] for t in tokenized]
 for index,(name,task,case,number,changed) in enumerate(CASES):
  source=original+ ('\n# New source snapshot for invalidation probe.\n' if changed else '')
  allowed=b.protocol.compact.task_scope(source,task)
  check=out/f'check-{index}.py';text=b.old.CHECK
  if number is not None:text=text.replace('.workers==6','.workers=='+str(number))
  check.write_text(text)
  arms=['baseline','jit'];rng.shuffle(arms)
  for arm in arms:
   folder=out/f'{index:02d}-{name}-{arm}';folder.mkdir();work=folder/'workspace';shutil.copytree(pristine,work);(work/'port_scanner.py').write_text(source)
   start=time.perf_counter();row={'case':name,'arm':arm,'source_sha256':jit.digest(source),'book_size_before':len(book.entries),'requests':[],'passed':False,'gate_accepted':False,'false_acceptance':False,'cache_hit':False,'admitted':False}
   def request(route,payload):
    n=len(row['requests']);(folder/f'request-{n}.json').write_text(json.dumps(payload,indent=2))
    t=time.perf_counter();response=b.remote(a.host,[(route,payload)]);(folder/f'response-{n}.json').write_text(json.dumps(response,indent=2))
    item=response['results'][0];assert item['status']==200,item
    body=item['body'];row['requests'].append({'route':route,'seconds':time.perf_counter()-t,'usage':body.get('usage'),'metrics':body.get('metrics'),'request_id':body.get('id')});return body
   def validate(edits):
    try:
     updated=b.protocol.compact.typed_decode(source,jit.digest(source),json.dumps(edits,separators=(',',':')),'stop',allowed)
     (work/'port_scanner.py').write_text(updated)
     return b.old.b.validate(work,case,check)
    except Exception as e:return {'passed':False,'error':repr(e)}
   try:
    if arm=='jit':
     targets=b.protocol.compact.scoped_selectors(source,allowed)['C']
     options=book.retrieve(source,task,set(targets));row['candidates']=options
     if options:
      choices=options+[None];rng.shuffle(choices)
      descriptions='\n'.join(letter+': '+(json.dumps(c,ensure_ascii=False) if c else 'NONE: no cached edit completely satisfies the task; generate a new edit.') for letter,c in zip('ABCDEFGHIJKLMNO',choices))
      messages=[{'role':'system','content':'Choose a cached edit only if it exactly satisfies the whole task. Otherwise choose NONE. Return only its letter.\n'+descriptions},{'role':'user','content':'SOURCE:\n'+source+'\nTASK: '+task}]
      ids=request('/tokenize',{'model':'/model','messages':messages,'add_generation_prompt':True,'chat_template_kwargs':{'thinking':False,'enable_thinking':False}})['tokens']
      payload={'model':'/model','prompt':ids,'max_tokens':1,'temperature':0,'logprobs':len(choices),'logprob_token_ids':label_ids[:len(choices)],'return_tokens_as_token_ids':True,'return_token_ids':True,'vllm_xargs':{'openjev_direct_classify':True},'cache_salt':uuid.uuid4().hex}
      response=request('/v1/completions',payload);ch=response['choices'][0];lp=ch['logprobs']['top_logprobs'][0];scores=[lp[f'token_id:{i}'] for i in payload['logprob_token_ids']];selected=max(range(len(scores)),key=scores.__getitem__)
      assert ch['token_ids']==[label_ids[selected]]
      decision=choices[selected];confidence=jit.confidence(scores,selected);row.update(decision=decision,scores=scores,confidence=confidence)
      row['gate_accepted']=decision is not None and confidence['conditional_probability']>=0.8 and confidence['margin']>=1.0
      if row['gate_accepted']:
       row['cached_validation']=validate(decision['edits']);row['cache_hit']=row['cached_validation']['passed'];row['false_acceptance']=not row['cache_hit'];row['passed']=row['cache_hit']
      row['fallback_reason']='oracle_rejected_cached_edit' if row['false_acceptance'] else 'none_or_low_confidence' if not row['gate_accepted'] else None
     else:row['fallback_reason']='empty_or_inapplicable_codebook'
    if not row['passed']:
     row['generated']=True
     payload={'model':'/model','temperature':0,'max_tokens':512,'chat_template_kwargs':{'thinking':False,'enable_thinking':False},'messages':[{'role':'system','content':b.protocol.compact.typed_prompt(source,allowed)},{'role':'user','content':'Edit the supplied file. Make the smallest necessary change and preserve unrelated behavior.\nFILE: port_scanner.py\nSOURCE:\n'+source+'\nTASK: '+task}],'structured_outputs':{'regex':b.protocol.compact.typed_grammar(source,allowed)},'cache_salt':uuid.uuid4().hex}
     response=request('/v1/chat/completions',payload);choice=response['choices'][0]
     assert choice['finish_reason']=='stop',choice['finish_reason']
     edits=json.loads(choice['message']['content']);row['generated_edits']=edits
     row['generated_validation']=validate(edits);row['passed']=row['generated_validation']['passed']
     if arm=='jit':row['admitted']=book.admit(source,task,edits,row['passed'])
    else:row['generated']=False
   except Exception as e:row['error']=repr(e)
   row['seconds']=time.perf_counter()-start;row['book_size_after']=len(book.entries)
   inference=[r for r in row['requests'] if r['route']!='/tokenize']
   row['usage_complete']=all(r['usage'] is not None for r in inference) and 'error' not in row
   row['usage']={k:sum(r['usage'][k] for r in inference if r['usage']) for k in ['prompt_tokens','completion_tokens','total_tokens']}
   row['control_records']=sum(r['route']=='/v1/completions' for r in inference)
   (folder/'result.json').write_text(json.dumps(row,indent=2));(folder/'codebook-after.json').write_text(json.dumps(book.entries,indent=2))
   with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   print(name,arm,'pass',row['passed'],'hit',row['cache_hit'],'admit',row['admitted'],'tokens',row['usage']['completion_tokens'],round(row['seconds'],2),row.get('error',''),flush=True)
 (out/'codebook.json').write_text(json.dumps(book.entries,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--host',default=os.environ.get('ENGINE_TOOLCALL_HOST','localhost'));run(p.parse_args())
