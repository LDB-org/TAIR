"""Mixed concurrency, fail-closed truncation, and ordinary API canaries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import urllib.error

from test_deepseek_candidate_scores import post
from test_remote_toolcall import png
import base64


def main(a):
    a.out.mkdir(parents=True, exist_ok=False)
    prepared = json.loads((a.measured/'inputs.json').read_text())
    expected = {name: {'name': name, 'arguments': args}
                for name, _, args in json.loads((a.measured/'cases.json').read_text())}
    jobs = [(name, mode) for name in ['read', 'edit', 'write', 'reply_user'] for mode in ['direct', 'whole']]

    def run(job):
        name, mode = job
        started = time.perf_counter()
        response = post(a.url, '/v1/openjev/toolcall' if mode == 'direct' else '/v1/completions', prepared[name][mode])
        call = response['call'] if mode == 'direct' else json.loads(response['choices'][0]['text'])
        return {'case': name, 'mode': mode, 'seconds': time.perf_counter()-started,
                'exact': call == expected[name], 'response': response}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(run, jobs))
    (a.out/'concurrent.json').write_text(json.dumps(rows, indent=2))
    probes = {}
    original = prepared['reply_user']['direct']
    for label, body in [('invalid_table', {**original, 'candidate_ids': original['candidate_ids'][:-1]}),
                        ('truncated', {**original, 'max_tokens': 1})]:
        try:
            response = post(a.url, '/v1/openjev/toolcall', body)
            probes[label] = {'status': 200, 'response': response}
        except urllib.error.HTTPError as error:
            probes[label] = {'status': error.code, 'response': json.loads(error.read())}
    chat = {'model': '/model', 'temperature': 0, 'max_tokens': 128,
            'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}}
    probes['text'] = post(a.url, '/v1/chat/completions', {**chat,
        'messages': [{'role': 'user', 'content': 'Reply with exactly OK and nothing else.'}]})
    probes['native_tool'] = post(a.url, '/v1/chat/completions', {**chat,
        'messages': [{'role': 'user', 'content': 'Call reply_user with content exactly OK.'}],
        'tools': [{'type': 'function', 'function': {'name': 'reply_user', 'description': 'Send the final reply.',
                    'parameters': {'type': 'object', 'properties': {'content': {'type': 'string'}}, 'required': ['content']}}}],
        'tool_choice': 'required'})
    probes['vision'] = post(a.url, '/v1/chat/completions', {**chat,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': 'Reply RED if the left half of the image is red, otherwise OTHER. One word only.'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,'+base64.b64encode(png()).decode()}}]}]})
    (a.out/'probes.json').write_text(json.dumps(probes, indent=2))
    (a.out/Path(__file__).name).write_text(Path(__file__).read_text())
    native = probes['native_tool']['choices'][0]['message']['tool_calls'][0]['function']
    checks = {'concurrent_exact': sum(r['exact'] for r in rows), 'concurrent_n': len(rows),
              'invalid_table_rejected': probes['invalid_table']['status'] == 400,
              'truncation_rejected': probes['truncated']['status'] == 500 and 'call' not in probes['truncated']['response'],
              'ordinary_text_ok': probes['text']['choices'][0]['message']['content'] == 'OK',
              'native_tool_ok': native['name'] == 'reply_user' and json.loads(native['arguments']) == {'content': 'OK'},
              'vision_ok': probes['vision']['choices'][0]['message']['content'].strip() == 'RED'}
    (a.out/'summary.json').write_text(json.dumps(checks, indent=2))
    print(json.dumps(checks), flush=True)
    assert checks['concurrent_exact'] == checks['concurrent_n'] and all(v for k, v in checks.items() if k.endswith(('_ok', '_rejected')))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:8000')
    p.add_argument('--measured', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    main(p.parse_args())
