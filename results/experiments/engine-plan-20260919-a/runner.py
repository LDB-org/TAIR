import subprocess, socket, time, pathlib, sys
root=pathlib.Path('/Users/zacharyzcr/Projects/TAIR')
out=root/'results/experiments/engine-plan-20260919-a'
s=socket.socket(); s.bind(('127.0.0.1',0)); port=s.getsockname()[1]; s.close()
p=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'])
try:
    for _ in range(50):
        if p.poll() is not None: raise RuntimeError('tunnel failed')
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.2): break
        except OSError: time.sleep(.1)
    result=subprocess.run(['/tmp/tair-test-venv-20260918/bin/python',str(root/'benchmarks/benchmark_engine_plan.py'),'--url',f'http://127.0.0.1:{port}','--out',str(out),'--repeats','3'],cwd=root)
    sys.exit(result.returncode)
finally:
    p.terminate(); p.wait(timeout=10)
