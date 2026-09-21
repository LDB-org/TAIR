"""Live verification of fused framing constraints and rejection of partial output."""
import json
from pathlib import Path
import re
import sys
from check_remote_toolcall_safety import post


def main():
    with Path(sys.argv[1]).open('x') as f:
        rows={}
        rows['invalid_mode']=post('http://127.0.0.1:18185/v1/toolcall',{'request':'reply hello','mode':'invalid'})
        rows['truncated']=post('http://127.0.0.1:18185/v1/toolcall',{'request':'Reply exactly: one two three four five','mode':'hybrid_fused','max_tokens':1})
        rows['grammar']=post('http://127.0.0.1:8000/v1/chat/completions',{
          'model':'/model','messages':[{'role':'user','content':'Output exactly Z then a newline then hello. Never output A B C or D.'}],
          'temperature':0,'max_tokens':32,'structured_outputs':{'regex':r'[ABCD]\n[\s\S]+'},'return_token_ids':True,
          'chat_template_kwargs':{'thinking':False,'enable_thinking':False}})
        t=rows['truncated'];g=rows['grammar'];choice=g['body'].get('choices',[{}])[0]
        rows['passed']={'invalid_mode':rows['invalid_mode']['status']==400,
          'truncation_rejected':t['status']==422 and t['body'].get('call') is None and t['body'].get('wire') is None and t['body'].get('upstream_requests')==1,
          'grammar_enforced':g['status']==200 and choice.get('finish_reason')=='stop' and bool(re.fullmatch(r'[ABCD]\n[\s\S]+',choice.get('message',{}).get('content') or ''))}
        json.dump(rows,f,ensure_ascii=False,indent=2);print(json.dumps(rows['passed']),flush=True)
        if not all(rows['passed'].values()):raise SystemExit(1)

if __name__=='__main__':main()
