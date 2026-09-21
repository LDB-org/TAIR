"""Paired prompt ablation for the three previous operation-selection failures."""

import os
import importlib.util,json,random,shutil,uuid
from pathlib import Path
spec=importlib.util.spec_from_file_location('b',Path(__file__).with_name('evaluate_direct_structural.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def main(out):
 out.mkdir();prior=b.ROOT/'results/experiments/pi-combined-structural-20260918-a'
 data=json.loads((prior/'prepared.json').read_text());expected={'socket_creation':'catch','guard_empty_host':'raise_if','default_workers_six':'kw'}
 plans={};requests=[]
 for case in expected:
  d=data[case];options='\n'.join(f'{letter}: {t["name"]}: {t["description"]}' for letter,t in zip('ABCDEF',d['tools']))
  messages=[{'role':'system','content':'Select the ONE operation kind required by the task. Reply with its option letter only. Do not generate edit tuples or arguments in this step.\n'+options},d['payloads']['native']['messages'][1]]
  requests.append(('/tokenize',{'model':'/model','messages':messages,'add_generation_prompt':True,'chat_template_kwargs':{'thinking':False,'enable_thinking':False}}))
  plans[case]={'messages':messages,'expected':expected[case]}
 tokenized=b.remote(os.environ.get('TAIR_ENGINE_HOST', os.environ.get('ENGINE_TOOLCALL_HOST', 'localhost')),requests)['results']
 for (case,p),t in zip(plans.items(),tokenized):
  assert t['status']==200;p['clean_ids']=t['body']['tokens'];p['original_ids']=data[case]['direct']['prompt_ids'];p['candidate_ids']=data[case]['direct']['candidate_ids'];p['tools']=data[case]['tools']
 (out/'plans.json').write_text(json.dumps(plans,indent=2));shutil.copyfile(__file__,out/'probe_operation_prompt.py')
 jobs=[(c,a) for c in plans for a in ['original','clean']];random.Random(20260924).shuffle(jobs)
 for case,arm in jobs:
  p=plans[case];body={'model':'/model','prompt':p[arm+'_ids'],'temperature':0,'max_tokens':1,'logprobs':len(p['candidate_ids']),'logprob_token_ids':p['candidate_ids'],'return_tokens_as_token_ids':True,'return_token_ids':True,'vllm_xargs':{'openjev_direct_classify':True},'cache_salt':uuid.uuid4().hex}
  result=b.remote(os.environ.get('TAIR_ENGINE_HOST', os.environ.get('ENGINE_TOOLCALL_HOST', 'localhost')),[('/v1/completions',body)]);item=result['results'][0];assert item['status']==200,item
  response=item['body'];lp=response['choices'][0]['logprobs']['top_logprobs'][0];scores=[lp[f'token_id:{i}'] for i in p['candidate_ids']];index=max(range(len(scores)),key=scores.__getitem__);selected=p['tools'][index]['name']
  row={'case':case,'arm':arm,'expected':p['expected'],'selected':selected,'correct':selected==p['expected'],'scores':scores,'response':response,'request':body}
  with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  print(case,arm,selected,row['correct'],flush=True)

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
