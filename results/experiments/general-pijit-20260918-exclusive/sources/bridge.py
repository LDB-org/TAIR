"""Local Pi transport and source-bound edits; model execution stays in vLLM."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
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
import preset_edits as presets

STATE = Path(os.environ.get('PIJIT_STATE_DIR', str(Path.home() / '.pijit')))
MODEL = os.environ.get('PIJIT_MODEL', '/model')
LABELS = 'ABCDEFGHIJKLMNOP'
TRACE = ContextVar('pijit_trace', default=None)


class CancelledError(RuntimeError):
    pass


@contextmanager
def stage(name):
    started = time.perf_counter()
    try:
        yield
    finally:
        if TRACE.get() is not None:
            timings = TRACE.get()['stage_seconds']
            timings[name] = timings.get(name, 0) + time.perf_counter() - started


def trace_update(**values):
    if TRACE.get() is not None:
        TRACE.get().update(values)


def parallel(function, items, max_workers=8):
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(copy_context().run, function, item) for item in items]
        return [future.result() for future in futures]


def post(route, payload):
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('PIJIT_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['PIJIT_API_KEY']
    request = urllib.request.Request(os.environ['PIJIT_URL'].rstrip('/') + route,
                                     data=json.dumps(payload).encode(), headers=headers)
    record = {'route': route, 'status': 'pending', 'usage_complete': False, 'started_at': time.time()}
    if TRACE.get() is not None:
        TRACE.get()['http_requests'].append(record)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=195) as response:
            record['http_status'] = response.status
            result = json.load(response)
        record.update(status='ok', request_id=result.get('request_id', result.get('id')))
        if route == '/v1/openjev/toolcall':
            selected = result['decision']['index']
            record.update(input_tokens=len(payload['prompt_ids']) + len(payload['continuations'][selected]),
                          generated_argument_tokens=result['generated_argument_tokens'],
                          classification_control_records=result['classification_control_records'],
                          engine_seconds=result.get('seconds'),
                          classification_seconds=result['decision'].get('classification_seconds'),
                          classification_timing=result['decision'].get('timing'),
                          usage_complete=True)
        elif route == '/v1/completions' and result.get('usage'):
            controls = len(result['choices'][0].get('token_ids', []))
            record.update(input_tokens=result['usage']['prompt_tokens'],
                          generated_argument_tokens=0, classification_control_records=controls,
                          usage_complete=controls == result['usage']['completion_tokens'])
        return result
    except Exception as error:
        record.update(status='error', error_type=type(error).__name__)
        if hasattr(error, 'code'):
            record['http_status'] = error.code
        raise
    finally:
        record['seconds'] = time.perf_counter() - started


def tokenize(messages):
    return post('/tokenize', {'model': MODEL, 'messages': messages, 'add_generation_prompt': True,
                             'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})['tokens']


def tokenize_label(label):
    return post('/tokenize', {'model': MODEL, 'prompt': label,
                            'add_special_tokens': False})['tokens']


def validate_labels(ids):
    if (any(not isinstance(ids_, list) or len(ids_) != 1 or type(ids_[0]) is not int or ids_[0] < 0
            for ids_ in ids) or len({ids_[0] for ids_ in ids}) != len(ids)):
        raise ValueError('Candidate labels must be distinct single tokens')
    return [ids_[0] for ids_ in ids]


def labels(count):
    revision = os.environ.get('PIJIT_TOKENIZER_REVISION')
    cache = None
    if revision and os.environ.get('PIJIT_SERIAL_PREPARATION') != '1':
        identity = [os.environ['PIJIT_URL'].rstrip('/'), MODEL, revision, LABELS[:count]]
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        directory = STATE / 'tokenizer-labels'
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache = directory / (key + '.json')
        try:
            ids = json.loads(cache.read_text())
            if not isinstance(ids, list) or len(ids) != count:
                raise ValueError('Wrong label count')
            result = validate_labels(ids)
            trace_update(label_cache_hit=True)
            return result
        except (OSError, ValueError, TypeError):
            pass
    trace_update(label_cache_hit=False)
    ids = parallel(tokenize_label, LABELS[:count])
    result = validate_labels(ids)
    if cache is not None:
        atomic_write(cache, json.dumps(ids))
    return result


def prepare_classification(messages, count):
    if not 1 <= count <= len(LABELS):
        raise ValueError('Classification requires 1..16 candidates')
    return parallel(lambda work: work(), [
        lambda: tokenize(messages), lambda: labels(count)], max_workers=2)


@stage('generation')
def infer(messages, tools, instruction=None):
    if not 1 <= len(tools) <= 16:
        raise ValueError('pijit engine supports 1..16 active tools')
    with stage('generation_preparation'):
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
        if os.environ.get('PIJIT_SERIAL_PREPARATION') == '1':
            tokenized = parallel(tokenize, expanded)
            candidate_ids = labels(len(tools))
        else:
            # Independent waves, at most eight HTTP requests each.
            tokenized, candidate_ids = parallel(lambda work: work(), [
                lambda: parallel(tokenize, expanded), lambda: labels(len(tools))], max_workers=2)
        prefix = tokenized[0]
        if any(ids[:len(prefix)] != prefix for ids in tokenized[1:]):
            raise ValueError('Tokenizer continuation does not preserve the classification prefix')
        suffixes = [ids[len(prefix):] for ids in tokenized[1:]]
    with stage('generation_http'):
        result = post('/v1/openjev/toolcall', {'prompt_ids': prefix, 'candidate_ids': candidate_ids,
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
    if any(t['name'] == 'set_cli_default' for t in tools):
        system += '\nFor an existing integer argparse default prefer set_cli_default; read the current default first.'
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


@stage('cache_classification')
def pick_cached(source, task, options):
    candidates = options[:15] + [None]
    decision = {'candidates': candidates, 'omitted_candidates': max(0, len(options) - 15),
                'thresholds': {'conditional_probability': 0.95, 'margin': 3},
                'accepted': False, 'rejection_reasons': ['classification_incomplete']}
    trace_update(cache_decision=decision)
    with stage('cache_preparation'):
        choices = '\n'.join(label + ': ' + (json.dumps(candidate, ensure_ascii=False) if candidate else
            'NONE: no entry exactly satisfies the task') for label, candidate in zip(LABELS, candidates))
        prompt = tokenize([{'role': 'system', 'content': 'Select a cached edit ONLY if it satisfies the entire task. Otherwise NONE. Return its letter.\n' + choices},
                           {'role': 'user', 'content': 'SOURCE:\n' + source + '\nTASK:\n' + task}])
        ids = labels(len(candidates))
    with stage('cache_http'):
        response = post('/v1/completions', {'model': MODEL, 'prompt': prompt, 'max_tokens': 1,
            'temperature': 0, 'logprobs': len(ids), 'logprob_token_ids': ids, 'return_tokens_as_token_ids': True,
            'return_token_ids': True, 'vllm_xargs': {'openjev_direct_classify': True}, 'cache_salt': uuid.uuid4().hex})
    choice = response['choices'][0]
    scores = [choice['logprobs']['top_logprobs'][0][f'token_id:{i}'] for i in ids]
    selected = max(range(len(scores)), key=scores.__getitem__)
    decision.update(scores=scores, selected_index=selected, selected_candidate=candidates[selected],
                    request_id=response.get('id'))
    if choice['token_ids'] != [ids[selected]]:
        raise ValueError('Engine did not return the classified candidate')
    gate = jit.confidence(scores, selected)
    reasons = []
    if candidates[selected] is None:
        reasons.append('selected_none')
    if gate['conditional_probability'] < 0.95:
        reasons.append('low_conditional_probability')
    if gate['margin'] < 3:
        reasons.append('low_margin')
    accepted = not reasons
    decision.update(gate=gate, accepted=accepted, rejection_reasons=reasons)
    return candidates[selected] if accepted else None, {'gate': gate, 'decision': decision, 'input_tokens': len(prompt),
        'classification_control_records': 1, 'generated_argument_tokens': 0, 'request_id': response.get('id')}


def edit(payload):
    cwd = Path(payload['cwd']).resolve()
    path = (cwd / payload['path']).resolve()
    if not path.is_relative_to(cwd) or path.suffix != '.py':
        raise ValueError('compact_edit requires a Python file within the current project')
    task = payload.get('task')
    preset = payload.get('action') == 'preset'
    if not preset and (not isinstance(task, str) or not task.strip()):
        raise ValueError('An explicit edit task is required')
    directory = paths(cwd)
    with (directory / 'lock').open('a') as lock:
        with stage('lock_wait'):
            fcntl.flock(lock, fcntl.LOCK_EX)
        if preset:
            return locked_preset(path, payload, cwd, directory)
        return locked_edit(path, task, cwd, directory)


def locked_edit(path, task, cwd, directory):
    with stage('retrieval'):
        source = path.read_bytes().decode('utf-8')
        if len(source.encode()) > 200_000:
            raise ValueError('compact_edit currently limits source files to 200 KB')
        ast.parse(source)
        before = jit.digest(source)
        allowed = protocol.compact.task_scope(source, task)
        book = jit.Codebook()
        bookfile = directory / 'codebook.json'
        enabled = os.environ.get('PIJIT_DISABLE_CODEBOOK') != '1'
        trace_update(codebook_enabled=enabled, cache_hit=False, applied=False)
        if enabled and bookfile.exists():
            book.entries = json.loads(bookfile.read_text())
        targets = protocol.compact.scoped_selectors(source, allowed)['C']
        # Only locally admitted same-task entries are eligible, not benchmark or arbitrary entries.
        eligible = [e for e in book.entries if e.get('task_key') == task_key(task) and e.get('path') == str(path)]
        candidate_book = jit.Codebook()
        candidate_book.entries = eligible
        options = candidate_book.retrieve(source, task, set(targets))
        trace_update(retrieval={'book_entries': len(book.entries), 'task_path_matches': len(eligible),
                                'source_matches': sum(e['source_sha256'] == before for e in eligible),
                                'candidate_count': len(options)}, candidates=options)
    requests = []
    candidate = None
    fallback = 'empty_or_inapplicable_codebook' if enabled else 'codebook_disabled'
    trace_update(fallback_reason=fallback)
    if options:
        candidate, record = pick_cached(source, task, options)
        requests.append(record)
        fallback = ','.join(record.get('decision', {}).get('rejection_reasons', [])) or 'none_or_low_confidence'
        trace_update(fallback_reason=fallback)
    hit = False
    edits = None
    with stage('cached_validation'):
        if candidate:
            try:
                edits = candidate['edits']
                updated = protocol.compact.typed_decode(source, before, json.dumps(edits, separators=(',', ':'), ensure_ascii=False), 'stop', allowed)
                compile(updated, str(path), 'exec')
                hit = True
                trace_update(cache_selected_valid=True)
            except (ValueError, SyntaxError, TypeError):
                fallback = 'cached_edit_failed_validation'
                trace_update(fallback_reason=fallback, cache_selected_valid=False)
    trace_update(fallback_reason=None if hit else fallback)
    if not hit:
        tools = protocol.operation_tools(source, allowed)
        messages = [{'role': 'system', 'content': protocol.compact.typed_prompt(source, allowed)},
                    {'role': 'user', 'content': 'SOURCE:\n' + source + '\nTASK:\n' + task}]
        result = infer(messages, tools, protocol.continuation_instruction)
        requests.append({k: result[k] for k in ('input_tokens', 'generated_argument_tokens', 'classification_control_records', 'request_id')})
        with stage('generated_validation'):
            updated = protocol.decode(source, before, result['call'], allowed)
            call = result['call']
            edits = call['arguments'] if call['name'] == 'mixed' else [[call['name'], *args] for args in call['arguments']]
            compile(updated, str(path), 'exec')
    backup, verification = apply_edit(path, source, updated, cwd, directory)
    with stage('admission'):
        admitted = 0
        # Both exact snapshots are eligible; this permits a later value change on the new version.
        for snapshot in (source, updated) if enabled else ():
            count = len(book.entries)
            book.admit(snapshot, task, edits, True)
            if len(book.entries) > count:
                book.entries[-1].update(admission=verification, task_key=task_key(task), path=str(path))
                admitted += 1
        if enabled:
            atomic_write(bookfile, json.dumps(book.entries[-256:], ensure_ascii=False, indent=2))
        trace_update(cache_hit=hit, validation=verification)
    return {'path': str(path), 'applied': True, 'cache_hit': hit, 'admitted': admitted,
            'fallback_reason': None if hit else fallback, 'validation': verification,
            'source_sha256': before, 'updated_sha256': jit.digest(updated), 'backup': str(backup),
            'diff': ''.join(difflib.unified_diff(source.splitlines(True), updated.splitlines(True), fromfile=str(path), tofile=str(path))),
            'input_tokens': sum(r['input_tokens'] for r in requests),
            'generated_argument_tokens': sum(r['generated_argument_tokens'] for r in requests),
            'classification_control_records': sum(r['classification_control_records'] for r in requests), 'requests': requests}


def locked_preset(path, payload, cwd, directory):
    trace_update(preset_id=presets.PRESET_ID, applied=False, cache_hit=False, codebook_enabled=False)
    with stage('preset_binding'):
        source = path.read_bytes().decode('utf-8')
        if len(source.encode()) > 200_000:
            raise ValueError('Preset limits source files to 200 KB')
        updated = presets.set_cli_default(source, payload['option'], payload['expected_default'], payload['value'])
    backup, verification = apply_edit(path, source, updated, cwd, directory)
    return {'path': str(path), 'applied': True, 'preset_id': presets.PRESET_ID,
            'cache_hit': False, 'admitted': 0, 'validation': verification,
            'source_sha256': jit.digest(source), 'updated_sha256': jit.digest(updated), 'backup': str(backup),
            'diff': ''.join(difflib.unified_diff(source.splitlines(True), updated.splitlines(True),
                                             fromfile=str(path), tofile=str(path))),
            'input_tokens': 0, 'generated_argument_tokens': 0, 'classification_control_records': 0,
            'requests': []}


def apply_edit(path, source, updated, cwd, directory):
    before = jit.digest(source)
    with stage('write'):
        if path.read_bytes().decode('utf-8') != source:
            raise ValueError('Source changed during inference; no write performed')
        backup = directory / ('backup-' + uuid.uuid4().hex + '.py')
        atomic_write(backup, source)
        atomic_write(path, updated, path.stat().st_mode & 0o777)
        trace_update(applied=True, backup=str(backup), source_sha256=before, updated_sha256=jit.digest(updated))
    verification = 'schema + Python compile; semantic correctness unverified'
    with stage('verification'):
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
                    trace_update(applied=False, rolled_back=True)
                else:
                    trace_update(rolled_back=False)
                raise
    if path.read_bytes().decode('utf-8') != updated:
        raise ValueError('Source changed during verification; codebook admission skipped')
    return backup, verification


def run(payload):
    started = time.perf_counter()
    trace = {'metrics_version': 2, 'trace_id': uuid.uuid4().hex,
             'session_id': payload.get('session_id'), 'parent_tool_call_id': payload.get('parent_tool_call_id'),
             'stage_seconds': {}, 'http_requests': []}
    token = TRACE.set(trace)
    try:
        result = chat(payload) if payload['action'] == 'chat' else edit(payload)
        result['status'] = 'ok'
    except Exception as error:
        result = {'status': 'cancelled' if isinstance(error, CancelledError) else 'error',
                  'error': f'{type(error).__name__}: {error}'}
    finally:
        TRACE.reset(token)
    inference = [r for r in trace['http_requests'] if r['route'] != '/tokenize']
    trace['accounting'] = {
        'inference_requests': len(inference),
        'usage_complete': all(r['usage_complete'] for r in inference),
        'unknown_usage_requests': sum(not r['usage_complete'] for r in inference),
        **{'known_' + key: sum(r.get(key, 0) for r in inference)
           for key in ('input_tokens', 'generated_argument_tokens', 'classification_control_records')},
    }
    # Preserve error-path state (including rollback) as well as successful responses.
    result = {**trace, **result, 'wall_seconds': time.perf_counter() - started}
    directory = paths(payload['cwd'])
    record = {k: v for k, v in result.items() if k not in ('raw', 'diff', 'argument_token_ids', 'call')}
    record.update(action=payload['action'], timestamp=time.time())
    with (directory / 'metrics.jsonl').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    return result


def main():
    result = run(json.load(sys.stdin))
    print(json.dumps(result, ensure_ascii=False))
    return int(result['status'] != 'ok')


def cancelled(_signal, _frame):
    raise CancelledError('pijit request cancelled; inspect tool state before retrying')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'error': f'{type(error).__name__}: {error}'}))
        sys.exit(1)
