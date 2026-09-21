"""Measure capability GETs and local plan decoding; never send an inference request."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main(out, pi_root, samples):
    if samples < 2:
        raise ValueError('At least two samples required')
    package=json.loads((pi_root/'package.json').read_text())
    if package['version']!='0.85.1':
        raise ValueError('Pinned Pi 0.85.1 required')
    out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('profile_bridge',ROOT/'integrations/pijit/bridge.py')
    bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    catalog_script=('import * as pi from '+json.dumps((pi_root/'dist/index.js').as_uri())+'; '
        'console.log(JSON.stringify([pi.createReadTool,pi.createEditTool,pi.createWriteTool,pi.createBashTool,'
        'pi.createGrepTool,pi.createFindTool,pi.createLsTool].map(f=>{const t=f(process.cwd());'
        'return {name:t.name,description:t.description,parameters:t.parameters}})));')
    tools=json.loads(subprocess.run(['node','--input-type=module','-e',catalog_script],cwd=ROOT,
        capture_output=True,text=True,check=True,timeout=30).stdout)
    (out/'catalog.json').write_text(json.dumps(tools,indent=2))
    fixture=ROOT/'results/experiments/planned-reply-ablation-20260920-g/jsonl_base-tair_no_reuse/events.jsonl'
    events=[json.loads(line) for line in fixture.read_text().splitlines()]
    steps=next(event['args']['steps'] for event in events if event.get('type')=='tool_execution_start')
    index=next(i for i,tool in enumerate(tools) if tool['name']==steps[0]['name'])
    options=bridge.tool_plan.branches(tools,[])
    response=dict(decision=dict(index=index),same_engine_session=True,finish_reason='stop',
        classification_control_records=1,call=dict(name='plan',arguments=dict(first=steps[0]['arguments'],rest=steps[1:])))
    (out/'decode-fixture.json').write_text(json.dumps(response,indent=2))
    manifest=dict(pi_version=package['version'],samples=samples,inference_requests=0,
        fixture=str(fixture.relative_to(ROOT)),fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        method='Separate sequential capability GET timings and local decode timings. No model generation or tool execution. First decode includes lazy imports; warm samples are reported separately. Not an end-to-end speedup test.')
    for name in ['integrations/pijit/bridge.py','deploy/tool_plan.py','benchmarks/profile_plan_client.py']:
        target=out/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    stderr=(out/'ssh-stderr.log').open('w')
    tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
        '-o','ConnectTimeout=10','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000',
        'rs-yuesheng-gpu-public'],stderr=stderr)
    try:
        for _ in range(40):
            if tunnel.poll() is not None:
                raise RuntimeError('SSH tunnel exited')
            try:
                with urllib.request.urlopen(url+'/health',timeout=1) as reply:
                    if reply.status==200:break
            except OSError:time.sleep(.25)
        else:raise RuntimeError('Service not ready')
        bridge.os.environ['PIJIT_URL']=url
        capabilities=[]
        for _ in range(samples):
            trace=dict(stage_seconds={});token=bridge.TRACE.set(trace)
            try:supported=bridge.server_plan_budget()
            finally:bridge.TRACE.reset(token)
            capabilities.append(dict(supported=supported,**trace))
        decode=[]
        for _ in range(samples+1):
            started=time.perf_counter()
            call,reused=bridge.tool_plan.decode(response,tools,[],options)
            decode.append(time.perf_counter()-started)
            assert call['arguments']['steps']==steps and not reused
        report=dict(capabilities=capabilities,decode_seconds=decode,
            capability_median_seconds=statistics.median(c['stage_seconds']['capability_negotiation'] for c in capabilities),
            first_decode_seconds=decode[0],warm_decode_median_seconds=statistics.median(decode[1:]),
            inference_requests=0)
        (out/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({k:v for k,v in report.items() if k not in ('capabilities','decode_seconds')}))
    finally:
        tunnel.terminate()
        try:tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
        stderr.close()
        files=sorted(p for p in out.rglob('*') if p.is_file())
        (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--pi-root',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=5)
    args=parser.parse_args();main(args.out.resolve(),args.pi_root.resolve(),args.samples)
