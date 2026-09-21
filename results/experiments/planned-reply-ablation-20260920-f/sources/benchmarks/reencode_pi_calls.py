"""Count compact-protocol tokens for the exact values produced by a native run.

Only tokenize/detokenize endpoints are used; this does not measure latency gains.
"""

import os
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

REMOTE = '''import json,sys,urllib.request
data=json.load(sys.stdin)
def post(path,p):
 r=urllib.request.Request('http://127.0.0.1:8000/'+path,data=json.dumps(p).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=30) as f:return json.load(f)
out=[]
for row in data:
 raw=post('detokenize',{'model':'/model','tokens':row['native_ids']})['prompt']
 reencoded=post('tokenize',{'model':'/model','prompt':raw,'add_special_tokens':False})['tokens']
 compact=post('tokenize',{'model':'/model','prompt':row['compact'],'add_special_tokens':False})['tokens']
 tool_only=raw[raw.index('<｜DSML｜tool_calls>'):]
 native_tool_ids=post('tokenize',{'model':'/model','prompt':tool_only,'add_special_tokens':False})['tokens']
 out.append(dict(row,native_raw=raw,native_reencoded_ids=reencoded,compact_ids=compact,native_tool_only_ids=native_tool_ids))
print(json.dumps(out,ensure_ascii=False))
'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    parser.add_argument('--host', default=os.environ.get('TAIR_ENGINE_HOST', os.environ.get('ENGINE_TOOLCALL_HOST', 'localhost')))
    args = parser.parse_args()
    run = Path(args.run)
    spec = importlib.util.spec_from_file_location('protocol', Path(__file__).resolve().parents[1] / 'deploy/pi_engine_protocol.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    protocol = module.Protocol(json.loads((run / 'tools.json').read_text()))
    data = []
    for r in map(json.loads, (run / 'inference.jsonl').read_text().splitlines()):
        calls = r.get('calls', [])
        if len(calls) != 1:
            raise ValueError('This diagnostic requires exactly one native call per turn')
        frame = protocol.encode(calls[0])
        assert protocol.decode(frame, 'stop') == calls[0]
        data.append({'turn': r['turn'], 'name': calls[0]['name'], 'native_ids': r['trace']['token_ids'], 'compact': frame})
    with (run / 'same-values-tokenization.json').open('x') as f:
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', args.host, 'python3 -c ' + shlex.quote(REMOTE)],
                                input=json.dumps(data), text=True, capture_output=True, timeout=120, check=True)
        rows = json.loads(result.stdout)
        json.dump(rows, f, ensure_ascii=False, indent=2)
    for row in rows:
        print(row['turn'], row['name'], 'native', len(row['native_ids']), 'compact_without_eos', len(row['compact_ids']),
              'native_retokenization_exact', row['native_ids'] == row['native_reencoded_ids'], 'native_suffix', row['native_ids'][-3:])
