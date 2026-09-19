"""Observe first content and remaining stream time; not GPU-only timings."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import urllib.request

spec=importlib.util.spec_from_file_location('service',sys.argv[1])
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)

class StreamingBackend(service.Backend):
    def post(self,path,payload):
        if path!='/v1/chat/completions':return super().post(path,payload)
        payload=dict(payload,stream=True,stream_options={'include_usage':True},stream_interval=1)
        if getattr(self,'drop_grammar',False):payload.pop('structured_outputs',None)
        start=time.perf_counter();chunks=[];text=[];token_ids=[];usage={};finish=None;request_id=None;done=False;metrics=None
        req=urllib.request.Request(self.url+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=120) as response:
            for line in response:
                if not line.startswith(b'data: '):continue
                raw=line[6:].strip()
                if raw==b'[DONE]':done=True;break
                data=json.loads(raw);request_id=data.get('id',request_id)
                if data.get('usage'):usage=data['usage']
                if data.get('metrics') is not None:metrics=data['metrics']
                if not data.get('choices'):continue
                c=data['choices'][0];part=c.get('delta',{}).get('content') or ''
                if part:chunks.append({'seconds':time.perf_counter()-start,'text':part});text.append(part)
                token_ids.extend(c.get('token_ids') or [])
                if c.get('finish_reason'):finish=c['finish_reason']
        elapsed=time.perf_counter()-start
        if not done:raise RuntimeError('Incomplete SSE')
        first=chunks[0]['seconds'] if chunks else None
        self.timing={'first_content_seconds':first,'after_first_content_seconds':elapsed-first if first is not None else None,'wall_seconds':elapsed,'chunks':chunks}
        return {'id':request_id,'usage':usage,'metrics':metrics,'choices':[{'message':{'content':''.join(text)},'finish_reason':finish,'token_ids':token_ids}]}

backend=StreamingBackend('http://127.0.0.1:8000','/model')
cases=[('h01','Send the user precisely this reply: The report is ready.'),('h11','Urgent: reply with exactly: 3 < 5 && 8 > 2')]
with Path(sys.argv[2]).open('x') as f:
    for i,(id,request) in enumerate(cases):
        for mode in (['json','hybrid_fused','fused_unconstrained'] if i==0 else ['fused_unconstrained','hybrid_fused','json']):
            backend.drop_grammar = mode=='fused_unconstrained'
            result=service.run(backend,request,mode='hybrid_fused' if backend.drop_grammar else mode)
            row={'id':id,'mode':mode,'result':result,'timing':backend.timing}
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
            print(json.dumps({'id':id,'mode':mode,**{k:v for k,v in backend.timing.items() if k!='chunks'}}),flush=True)
