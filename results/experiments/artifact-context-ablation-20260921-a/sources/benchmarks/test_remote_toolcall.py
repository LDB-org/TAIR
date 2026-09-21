"""Sequential, interleaved API acceptance; outputs are create-only."""
import argparse
import base64
import json
from pathlib import Path
import statistics
import struct
import time
import urllib.request
import urllib.error
import zlib


def png():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    pixels = b''.join(b'\0' + b'\xff\0\0' * 64 + b'\0\0\xff' * 64 for _ in range(64))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 128,64,8,2,0,0,0)) + chunk(b'IDAT',zlib.compress(pixels)) + chunk(b'IEND', b'')


def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18185');p.add_argument('--cases',required=True);p.add_argument('--out',required=True);p.add_argument('--modes',nargs='+',default=['json','hybrid_fields']);p.add_argument('--repeats',type=int,default=1);p.add_argument('--engine-metrics-url')
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    cases=[json.loads(x) for x in Path(a.cases).read_text().splitlines()]
    cases.append({'id':'vision01','request':'Look at the image. Reply with exactly RED if the left half is red, otherwise reply with exactly OTHER.',
                  'name':'reply_user','priority':'normal','content':'RED','image_url':'data:image/png;base64,'+base64.b64encode(png()).decode()})
    (out/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
    with urllib.request.urlopen(a.url+'/health') as response:health=json.load(response)
    (out/'health.json').write_text(json.dumps(health,indent=2))
    rows=[]
    with (out/'rows.jsonl').open('x') as f:
        for i,c in enumerate(cases * a.repeats):
            for mode in (a.modes if i%2==0 else list(reversed(a.modes))):
                payload={'request':c['request'],'mode':mode,'max_tokens':128}
                if 'image_url' in c:payload['image_url']=c['image_url']
                gauges=None
                if a.engine_metrics_url:
                    try:
                        with urllib.request.urlopen(a.engine_metrics_url,timeout=5) as response:
                            metric_text=response.read().decode()
                        gauges=[line for line in metric_text.splitlines() if line.startswith('vllm:') and any(key in line for key in ['num_requests_running','num_requests_waiting','kv_cache_usage_perc'])]
                    except Exception as e:gauges={'error':type(e).__name__}
                start=time.perf_counter()
                try:
                    req=urllib.request.Request(a.url+'/v1/toolcall',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
                    try:response=urllib.request.urlopen(req,timeout=300)
                    except urllib.error.HTTPError as e:response=e
                    with response: result=json.load(response);status=response.status
                except Exception as e:result={'error':type(e).__name__};status=0
                expected={'name':c['name'],'arguments':{'priority':c['priority'],'content':c['content']}}
                row={'engine_gauges_before':gauges,'repeat':i//len(cases),'id':c['id'],'mode':mode,'http_status':status,'wall_seconds':time.perf_counter()-start,'expected':expected,'exact':result.get('call')==expected,'result':result}
                rows.append(row);f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                print(json.dumps({k:row[k] for k in ['id','mode','http_status','wall_seconds','exact']}),flush=True)
    summary={}
    for mode in a.modes:
        rs=[r for r in rows if r['mode']==mode]
        summary[mode]={'n':len(rs),'exact':sum(r['exact'] for r in rs),'valid':sum(bool(r['result'].get('valid')) for r in rs),
          'mean_seconds':statistics.mean(r['wall_seconds'] for r in rs),'median_seconds':statistics.median(r['wall_seconds'] for r in rs),
          'completion_tokens':sum(r['result'].get('completion_tokens',0) for r in rs)}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
