"""Live fail-closed and candidate-mask checks, with create-only evidence."""
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error


def post(url, payload):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:response=urllib.request.urlopen(req,timeout=300)
    except urllib.error.HTTPError as e:response=e
    with response:return {'status':response.status,'body':json.load(response)}


def main():
    out=Path(sys.argv[1])
    with out.open('x') as f:
        rows={}
        rows['invalid_mode']=post('http://127.0.0.1:18185/v1/toolcall',{'request':'reply hello','mode':'invalid'})
        rows['truncated']=post('http://127.0.0.1:18185/v1/toolcall',{'request':'Reply with exactly: one two three four five six seven eight nine ten','max_tokens':1})
        rows['mask']=post('http://127.0.0.1:8000/v1/chat/completions',{
          'model':'/model','messages':[{'role':'user','content':'Output only the letter C. Never output A or B.'}],
          'temperature':0,'max_tokens':1,'allowed_token_ids':[35,36],
          'chat_template_kwargs':{'thinking':False,'enable_thinking':False}})
        t=rows['truncated'];m=rows['mask']
        rows['passed']={'invalid_mode':rows['invalid_mode']['status']==400,
          'truncation_rejected':t['status']==422 and t['body'].get('call') is None and t['body'].get('wire') is None and not t['body'].get('valid',True),
          'candidate_mask':m['status']==200 and m['body'].get('choices',[{}])[0].get('message',{}).get('content') in ['A','B']}
        json.dump(rows,f,ensure_ascii=False,indent=2)
        print(json.dumps(rows['passed']),flush=True)
        if not all(rows['passed'].values()):raise SystemExit(1)

if __name__=='__main__':main()
