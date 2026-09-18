"""Local Pi transport and source-bound edits; model execution stays in vLLM."""
import ast
from concurrent.futures import ThreadPoolExecutor
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import direct_structural_protocol as protocol
import jit_codebook as jit

STATE = Path(os.environ.get('PIJIT_STATE_DIR', str(Path.home() / '.pijit')))
MODEL = os.environ.get('PIJIT_MODEL', '/model')
LABELS = 'ABCDEFGHIJKLMNOP'


def post(route, payload):
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('PIJIT_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['PIJIT_API_KEY']
    request = urllib.request.Request(os.environ['PIJIT_URL'].rstrip('/') + route,
                                     data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=195) as response:
        return json.load(response)


def tokenize(messages):
    return post('/tokenize', {'model': MODEL, 'messages': messages, 'add_generation_prompt': True,
                             'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})['tokens']


def labels(count):
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda label: post('/tokenize', {'model': MODEL, 'prompt': label,
                        'add_special_tokens': False})['tokens'], LABELS[:count]))
    if any(len(ids_) != 1 for ids_ in ids) or len({ids_[0] for ids_ in ids}) != count:
        raise ValueError('Candidate labels must be distinct single tokens')
    return [ids_[0] for ids_ in ids]


def infer(messages, tools, instruction=None):
    if not 1 <= len(tools) <= 16:
        raise ValueError('pijit engine supports 1..16 active tools')
    options = '\n'.join(f'{label}: {tool["name"]}: {tool.get("description", "")}'
                        for label, tool in zip(LABELS, tools))
    messages = messages + [{'role': 'user', 'content':
        'Choose the single next tool needed for the current task. Reply only with its letter.\n' + options}]
    expanded = [messages]
    for label, tool in zip(LABELS, tools):
        suffix = instruction(tool['name']) if instruction else (
            'Selected tool: ' + tool['name'] + '. Generate ONLY its argument JSON. Schema: ' +
            json.dumps(tool['parameters'], ensure_ascii=False))
        expanded.append(messages + [{'role': 'assistant', 'content': label}, {'role': 'user', 'content': suffix}])
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokenized = list(pool.map(tokenize, expanded))
    prefix = tokenized[0]
    if any(ids[:len(prefix)] != prefix for ids in tokenized[1:]):
        raise ValueError('Tokenizer continuation does not preserve the classification prefix')
    suffixes = [ids[len(prefix):] for ids in tokenized[1:]]
    result = post('/v1/openjev/toolcall', {'prompt_ids': prefix, 'candidate_ids': labels(len(tools)),
        'continuations': suffixes, 'tools': tools, 'max_tokens': 2048})
    selected = result['decision']['index']
    result['input_tokens'] = len(prefix) + len(suffixes[selected])
    return result


def text_content(content):
    if isinstance(content, str):
        return content
    blocks = []
    for block in content or []:
        if block.get('type') == 'image':
            raise ValueError('pijit currently supports text and source files; image transport is not implemented')
        if block.get('type') == 'text':
            blocks.append(block['text'])
        elif block.get('type') == 'toolCall':
            blocks.append('TOOL CALL ' + json.dumps(block, ensure_ascii=False))
    return '\n'.join(blocks)


def chat(payload):
    context = payload['context']
    tools = [{key: t[key] for key in ('name', 'description', 'parameters')} for t in context.get('tools', [])]
    tools.append({'name': 'reply_user', 'description': 'Deliver the final answer, or ask the user a necessary question.',
                  'parameters': {'type': 'object', 'properties': {'content': {'type': 'string'}},
                                 'required': ['content'], 'additionalProperties': False}})
    system = context.get('systemPrompt', '') + '\nAll output is a tool call. Select reply_user to answer. '
    system += ('For supported Python changes prefer compact_edit; read the file first. '
               'Use normal edit/write for unsupported edits or new files. Do not call compact_edit again '
               'for a change already reported as applied. Test changes when appropriate.\nTOOLS:\n' +
               json.dumps(tools, ensure_ascii=False))
    messages = [{'role': 'system', 'content': system}]
    for message in context['messages']:
        role = message['role']
        text = text_content(message.get('content'))
        if role == 'toolResult':
            role = 'user'
            text = f'TOOL RESULT {message.get("toolName", "")} id={message.get("toolCallId", "")} error={message.get("isError", False)}:\n{text}'
        if role in ('user', 'assistant'):
            messages.append({'role': role, 'content': text})
    return infer(messages, tools)


def task_key(task):
    # Conservative reuse: identical wording, allowing one unambiguous integer binding.
    if jit.integer_binding(task) is not None:
        task = re.sub(r'(?<![\w.])-?\d+(?!\w|\.\d)', '{integer}', task)
    return ' '.join(task.split())


def paths(cwd):
    directory = STATE / 'workspaces' / hashlib.sha256(str(Path(cwd).resolve()).encode()).hexdigest()[:20]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def atomic_write(path, text, mode=0o600):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def pick_cached(source, task, options):
    candidates = options[:15] + [None]
    choices = '\n'.join(label + ': ' + (json.dumps(candidate, ensure_ascii=False) if candidate else
        'NONE: no entry exactly satisfies the task') for label, candidate in zip(LABELS, candidates))
    prompt = tokenize([{'role': 'system', 'content': 'Select a cached edit ONLY if it satisfies the entire task. Otherwise NONE. Return its letter.\n' + choices},
                       {'role': 'user', 'content': 'SOURCE:\n' + source + '\nTASK:\n' + task}])
    ids = labels(len(candidates))
    response = post('/v1/completions', {'model': MODEL, 'prompt': prompt, 'max_tokens': 1,
        'temperature': 0, 'logprobs': len(ids), 'logprob_token_ids': ids, 'return_tokens_as_token_ids': True,
        'return_token_ids': True, 'vllm_xargs': {'openjev_direct_classify': True}, 'cache_salt': uuid.uuid4().hex})
    choice = response['choices'][0]
    scores = [choice['logprobs']['top_logprobs'][0][f'token_id:{i}'] for i in ids]
    selected = max(range(len(scores)), key=scores.__getitem__)
    if choice['token_ids'] != [ids[selected]]:
        raise ValueError('Engine did not return the classified candidate')
    gate = jit.confidence(scores, selected)
    accepted = gate['conditional_probability'] >= 0.95 and gate['margin'] >= 3
    return candidates[selected] if accepted else None, {'gate': gate, 'input_tokens': len(prompt),
        'classification_control_records': 1, 'generated_argument_tokens': 0, 'request_id': response.get('id')}


def edit(payload):
    cwd = Path(payload['cwd']).resolve()
    path = (cwd / payload['path']).resolve()
    if not path.is_relative_to(cwd) or path.suffix != '.py':
        raise ValueError('compact_edit requires a Python file within the current project')
    task = payload['task']
    if not isinstance(task, str) or not task.strip():
        raise ValueError('An explicit edit task is required')
    directory = paths(cwd)
    with (directory / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return locked_edit(path, task, cwd, directory)


def locked_edit(path, task, cwd, directory):
    source = path.read_bytes().decode('utf-8')
    if len(source.encode()) > 200_000:
        raise ValueError('compact_edit currently limits source files to 200 KB')
    ast.parse(source)
    before = jit.digest(source)
    allowed = protocol.compact.task_scope(source, task)
    book = jit.Codebook()
    bookfile = directory / 'codebook.json'
    if bookfile.exists():
        book.entries = json.loads(bookfile.read_text())
    targets = protocol.compact.scoped_selectors(source, allowed)['C']
    # Only locally admitted same-task entries are eligible, not benchmark or arbitrary entries.
    eligible = [e for e in book.entries if e.get('task_key') == task_key(task) and e.get('path') == str(path)]
    candidate_book = jit.Codebook()
    candidate_book.entries = eligible
    options = candidate_book.retrieve(source, task, set(targets))
    requests = []
    candidate = None
    fallback = 'empty_or_inapplicable_codebook'
    if options:
        candidate, record = pick_cached(source, task, options)
        requests.append(record)
        fallback = 'none_or_low_confidence'
    hit = False
    edits = None
    if candidate:
        try:
            edits = candidate['edits']
            updated = protocol.compact.typed_decode(source, before, json.dumps(edits, separators=(',', ':'), ensure_ascii=False), 'stop', allowed)
            compile(updated, str(path), 'exec')
            hit = True
        except (ValueError, SyntaxError, TypeError):
            fallback = 'cached_edit_failed_validation'
    if not hit:
        tools = protocol.operation_tools(source, allowed)
        messages = [{'role': 'system', 'content': protocol.compact.typed_prompt(source, allowed)},
                    {'role': 'user', 'content': 'SOURCE:\n' + source + '\nTASK:\n' + task}]
        result = infer(messages, tools, protocol.continuation_instruction)
        requests.append({k: result[k] for k in ('input_tokens', 'generated_argument_tokens', 'classification_control_records', 'request_id')})
        updated = protocol.decode(source, before, result['call'], allowed)
        call = result['call']
        edits = call['arguments'] if call['name'] == 'mixed' else [[call['name'], *args] for args in call['arguments']]
        compile(updated, str(path), 'exec')
    if path.read_bytes().decode('utf-8') != source:
        raise ValueError('Source changed during inference; no write performed')
    backup = directory / ('backup-' + uuid.uuid4().hex + '.py')
    atomic_write(backup, source)
    atomic_write(path, updated, path.stat().st_mode & 0o777)
    verification = 'schema + Python compile; semantic correctness unverified'
    command = os.environ.get('PIJIT_VERIFY_CMD')
    if command:
        try:
            checked = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True)
            try:
                stdout, stderr = checked.communicate(timeout=90)
            except BaseException:
                os.killpg(checked.pid, signal.SIGKILL)
                checked.communicate()
                raise
            if checked.returncode:
                raise ValueError('Project verification failed: ' + (stdout + stderr)[-3000:])
            verification = 'schema + Python compile + configured project command (not a task oracle)'
        except Exception:
            if path.read_bytes().decode('utf-8') == updated:
                atomic_write(path, source, path.stat().st_mode & 0o777)
            raise
    if path.read_bytes().decode('utf-8') != updated:
        raise ValueError('Source changed during verification; codebook admission skipped')
    admitted = 0
    # Both exact snapshots are eligible; this permits a later value change on the new version.
    for snapshot in (source, updated):
        count = len(book.entries)
        book.admit(snapshot, task, edits, True)
        if len(book.entries) > count:
            book.entries[-1].update(admission=verification, task_key=task_key(task), path=str(path))
            admitted += 1
    atomic_write(bookfile, json.dumps(book.entries[-256:], ensure_ascii=False, indent=2))
    return {'path': str(path), 'applied': True, 'cache_hit': hit, 'admitted': admitted,
            'fallback_reason': None if hit else fallback, 'validation': verification,
            'source_sha256': before, 'updated_sha256': jit.digest(updated), 'backup': str(backup),
            'diff': ''.join(difflib.unified_diff(source.splitlines(True), updated.splitlines(True), fromfile=str(path), tofile=str(path))),
            'input_tokens': sum(r['input_tokens'] for r in requests),
            'generated_argument_tokens': sum(r['generated_argument_tokens'] for r in requests),
            'classification_control_records': sum(r['classification_control_records'] for r in requests), 'requests': requests}


def main():
    payload = json.load(sys.stdin)
    started = time.perf_counter()
    result = chat(payload) if payload['action'] == 'chat' else edit(payload)
    result['wall_seconds'] = time.perf_counter() - started
    directory = paths(payload['cwd'])
    record = {k: v for k, v in result.items() if k not in ('raw', 'diff', 'argument_token_ids', 'call')}
    record.update(action=payload['action'], timestamp=time.time())
    with (directory / 'metrics.jsonl').open('a') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    print(json.dumps(result, ensure_ascii=False))


def cancelled(_signal, _frame):
    raise RuntimeError('pijit request cancelled; inspect tool state before retrying')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    try:
        main()
    except Exception as error:
        print(json.dumps({'error': f'{type(error).__name__}: {error}'}))
        sys.exit(1)
