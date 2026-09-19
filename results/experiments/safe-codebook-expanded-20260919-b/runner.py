import subprocess, socket, time, pathlib, sys
root=pathlib.Path('/Users/zacharyzcr/Projects/TAIR')
out=root/'results/experiments/safe-codebook-expanded-20260919-b'
s=socket.socket(); s.bind(('127.0.0.1',0)); port=s.getsockname()[1]; s.close()
p=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'])
def server_snapshot():
    return subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','rs-yuesheng-gpu-public', 'docker inspect --format="{{.State.StartedAt}} {{.Image}}" vllm-deepseek-v4-sm120-situ; curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health'], text=True)
before = server_snapshot()
try:
    for _ in range(50):
        if p.poll() is not None: raise RuntimeError('tunnel failed')
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.2): break
        except OSError: time.sleep(.1)
    result=subprocess.run(['/tmp/tair-test-venv-20260918/bin/python',str(root/'benchmarks/benchmark_safe_codebook.py'),'--url',f'http://127.0.0.1:{port}','--out',str(out),'--repeats','4','--suite','expanded'],cwd=root)
    (out/'server-before.txt').write_text(before)
    (out/'server-after.txt').write_text(server_snapshot())
    sys.exit(result.returncode)
finally:
    p.terminate(); p.wait(timeout=10)
