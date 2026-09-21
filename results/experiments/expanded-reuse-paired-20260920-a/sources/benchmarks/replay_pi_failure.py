"""Replay one frozen failed conversation; report next calls, never execute them."""
import argparse
import importlib.util
import json
from pathlib import Path
import uuid


def main(args):
    spec = importlib.util.spec_from_file_location('protocol', args.worker)
    protocol = importlib.util.module_from_spec(spec); spec.loader.exec_module(protocol)
    payload = json.loads(args.request.read_text())
    with args.out.open('x') as output:
        for repeat in range(2):
            for mode in (['engine_raw', 'engine_named'] if repeat == 0 else ['engine_named', 'engine_raw']):
                request = dict(payload, protocol_mode=mode, session_id=uuid.uuid4().hex)
                result = protocol.infer(request, 'http://127.0.0.1:8000')
                row = {'mode': mode, 'repeat': repeat, 'result': result}
                output.write(json.dumps(row, ensure_ascii=False) + '\n'); output.flush()
                print(mode, repeat, result.get('call'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', required=True, type=Path)
    p.add_argument('--request', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    main(p.parse_args())
