"""Local Pi transport and source-bound edits; model execution stays in vLLM."""
import ast
import copy
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
import shlex
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
import schema_actions
import native_planner
import adaptive_plan
import tool_plan
import local_tokenizer
from vllm_direct_tools import PLAN_TOTAL_TOKENS

STATE = Path(os.environ.get('PIJIT_STATE_DIR', str(Path.home() / '.pijit')))
MODEL = os.environ.get('PIJIT_MODEL', '/model')
LABELS = 'ABCDEFGHIJKLMNOP'
TRACE = ContextVar('pijit_trace', default=None)


class CancelledError(RuntimeError):
    pass


def is_validation_error(error):
    module = sys.modules.get('jsonschema.exceptions')
    return module is not None and isinstance(error, module.ValidationError)


def public_error(error):
    # Pi treats any "500" in errorMessage as a retryable provider failure.
    # Full schema dumps contain unrelated limits such as "500 lines".
    if is_validation_error(error):
        return f'ValidationError: tool arguments failed {error.validator} validation'
    return f'{type(error).__name__}: {error}'


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
                          cached_prefix_tokens=result['decision'].get('cached_prefix_tokens'),
                          prefix_cache_mode=result.get('prefix_cache_mode'),
                          usage_complete=True)
        elif route == '/v1/chat/completions' and result.get('usage'):
            record.update(input_tokens=result['usage']['prompt_tokens'],
                          generated_argument_tokens=result['usage']['completion_tokens'],
                          classification_control_records=0, usage_complete=True,
                          cached_input_tokens=(result['usage'].get('prompt_tokens_details') or {}).get('cached_tokens'))
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
            try:
                failure = json.loads(error.read())
                if route == '/v1/openjev/toolcall' and 'generated_argument_tokens' in failure:
                    decision = failure.get('decision')
                    selected = decision['index'] if decision else None
                    record.update(generated_argument_tokens=failure['generated_argument_tokens'],
                                  classification_control_records=failure['classification_control_records'],
                                  input_tokens=len(payload['prompt_ids'])+(len(payload['continuations'][selected]) if selected is not None else 0),
                                  usage_complete=failure.get('usage_complete', False), plan_budget=failure.get('plan_budget'))
                    trace_update(plan_token_budget=failure.get('plan_budget'))
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
        raise
    finally:
        record['seconds'] = time.perf_counter() - started


def tokenize(messages):
    return tokenize_payload({'model': MODEL, 'messages': messages, 'add_generation_prompt': True,
                             'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})


def tokenize_label(label):
    return tokenize_payload({'model': MODEL, 'prompt': label, 'add_special_tokens': False})


def tokenize_payload(payload):
    directory = os.environ.get('PIJIT_LOCAL_TOKENIZER')
    if not directory:
        return post('/tokenize', payload)['tokens']
    started = time.perf_counter()
    tokens = local_tokenizer.encode(payload, directory, os.environ.get('PIJIT_TOKENIZER_REVISION'))
    if tokens is None:
        return post('/tokenize', payload)['tokens']
    record = dict(seconds=time.perf_counter()-started, token_count=len(tokens), verified=False)
    if TRACE.get() is not None:
        TRACE.get().setdefault('local_tokenization', []).append(record)
    if os.environ.get('PIJIT_LOCAL_TOKENIZER_VERIFY') == '1':
        if tokens != post('/tokenize', payload)['tokens']:
            raise ValueError('Local tokenizer disagrees with deployed tokenizer')
        record['verified'] = True
    return tokens


def validate_labels(ids):
    if (any(not isinstance(ids_, list) or len(ids_) != 1 or type(ids_[0]) is not int or ids_[0] < 0
            for ids_ in ids) or len({ids_[0] for ids_ in ids}) != len(ids)):
        raise ValueError('Candidate labels must be distinct single tokens')
    return [ids_[0] for ids_ in ids]


def labels(count, values=None):
    selected = LABELS[:count] if values is None else values
    if len(selected) != count or not 1 <= count <= len(LABELS):
        raise ValueError('Invalid classification labels')
    revision = os.environ.get('PIJIT_TOKENIZER_REVISION')
    cache = None
    if revision and os.environ.get('PIJIT_SERIAL_PREPARATION') != '1':
        identity = [os.environ['PIJIT_URL'].rstrip('/'), MODEL, revision, selected]
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
    ids = parallel(tokenize_label, selected)
    result = validate_labels(ids)
    if cache is not None:
        atomic_write(cache, json.dumps(ids))
    return result


def prepare_classification(messages, count):
    if not 1 <= count <= len(LABELS):
        raise ValueError('Classification requires 1..16 candidates')
    return parallel(lambda work: work(), [
        lambda: tokenize(messages), lambda: labels(count)], max_workers=2)


@stage('schema_classification')
def classify_schema(messages, schema):
    codes = schema.get('enum')
    if (schema.get('type') != 'string' or not isinstance(codes, list)
            or not 1 <= len(codes) <= 16 or not all(isinstance(c, str) and c for c in codes)
            or len(set(codes)) != len(codes)):
        raise ValueError('Expected a finite unique string-enum classification schema')
    # Schema enum is compiled to tokenizer-specific candidate IDs, never appended to messages.
    prompt, ids = parallel(lambda work: work(), [lambda: tokenize(messages),
        lambda: labels(len(codes), codes)], max_workers=2)
    response = post('/v1/completions', {'model': MODEL, 'prompt': prompt, 'max_tokens': 1,
        'temperature': 0, 'logprobs': len(ids), 'logprob_token_ids': ids,
        'return_tokens_as_token_ids': True, 'return_token_ids': True,
        'vllm_xargs': {'openjev_direct_classify': True}, 'cache_salt': uuid.uuid4().hex})
    choice = response['choices'][0]
    scores = [choice['logprobs']['top_logprobs'][0][f'token_id:{i}'] for i in ids]
    selected = max(range(len(scores)), key=scores.__getitem__)
    if choice['token_ids'] != [ids[selected]]:
        raise ValueError('Engine output disagrees with schema classification')
    return {'code': codes[selected], 'schema': schema, 'gate': jit.confidence(scores, selected),
            'scores': scores, 'input_tokens': len(prompt), 'generated_argument_tokens': 0,
            'classification_control_records': 1, 'request_id': response['id']}


def schema_edit(source, task):
    if schema_actions.bind(source, task) is None:
        record = {'code': None, 'binding': None, 'applied_candidate': False,
                  'fallback_reason': 'locally_unsupported', 'classification_skipped': True,
                  'input_tokens': 0, 'generated_argument_tokens': 0, 'classification_control_records': 0}
        trace_update(schema_decision=record)
        return None, record
    record = classify_schema([{'role': 'system', 'content': schema_actions.INSTRUCTION},
        {'role': 'user', 'content': 'SOURCE:\n' + source + '\nTASK:\n' + task}], schema_actions.SCHEMA)
    gate = record['gate']
    updated, binding = None, None
    accepted = (gate['conditional_probability'] >= 0.95 and gate['margin'] >= 3
                and gate['candidate_mass'] >= 0.1)
    if accepted:
        updated, binding = schema_actions.decode(source, task, record['code'])
    record.update(binding=binding, applied_candidate=updated is not None,
                  fallback_reason=None if updated is not None else
                  'low_confidence' if not accepted else 'generate_or_unbound')
    trace_update(schema_decision=record)
    return updated, record


def continuation_tokens(messages, tails):
    tokenized = parallel(tokenize, [messages, *[messages + tail for tail in tails]])
    prefix = tokenized[0]
    if any(ids[:len(prefix)] != prefix for ids in tokenized[1:]):
        raise ValueError('Tokenizer continuation does not preserve the classification prefix')
    return prefix, [ids[len(prefix):] for ids in tokenized[1:]]


def valid_continuations(value, count):
    return (isinstance(value, list) and len(value) == count
            and all(isinstance(seq, list) and seq and all(type(t) is int and t >= 0 for t in seq)
                    for seq in value))


def prepare_continuations(messages, tails):
    revision = os.environ.get('PIJIT_TOKENIZER_REVISION')
    enabled = os.environ.get('PIJIT_CONTINUATION_CACHE') == '1' and revision
    if not enabled:
        return continuation_tokens(messages, tails)
    identity = ['continuations/v1', os.environ['PIJIT_URL'].rstrip('/'), MODEL, revision,
                {'thinking': False, 'enable_thinking': False}, tails]
    key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
    directory = STATE / 'tokenizer-continuations'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache = directory / (key + '.json')
    try:
        record = json.loads(cache.read_text())
        suffixes = record['continuations']
        digest = hashlib.sha256(json.dumps(suffixes).encode()).hexdigest()
        if (record['key'] != key or record['sha256'] != digest
                or not valid_continuations(suffixes, len(tails))):
            raise ValueError('Invalid continuation cache')
        trace_update(continuation_cache_hit=True)
        return tokenize(messages), suffixes
    except (OSError, ValueError, TypeError, KeyError):
        pass
    trace_update(continuation_cache_hit=False)
    prefix, suffixes = continuation_tokens(messages, tails)
    # This optimization is opt-in and revision-pinned. Admit only after matching
    # the current real context against an independent short calibration context.
    calibration = [{'role': 'user', 'content': 'Tokenizer continuation calibration.'}]
    try:
        _, calibrated = continuation_tokens(calibration, tails)
    except ValueError:
        trace_update(continuation_cache_rejected='context_dependent_prefix')
        return prefix, suffixes
    if suffixes != calibrated or not valid_continuations(suffixes, len(tails)):
        trace_update(continuation_cache_rejected='context_dependent_suffix')
        return prefix, suffixes
    atomic_write(cache, json.dumps({'key': key, 'continuations': suffixes,
        'sha256': hashlib.sha256(json.dumps(suffixes).encode()).hexdigest()}))
    return prefix, suffixes


def session_cache_options():
    trace = TRACE.get() or {}
    if os.environ.get('PIJIT_PREFIX_CACHE') != '1':
        return {}
    if not trace.get('prefix_cache_supported'):
        trace_update(prefix_cache_skipped='server_unsupported')
        return {}
    if not trace.get('session_id') or not trace.get('workspace_id'):
        trace_update(prefix_cache_skipped='missing_session_or_workspace')
        return {}
    identity = [str(STATE.resolve()), os.environ['PIJIT_URL'].rstrip('/'), MODEL,
                trace['workspace_id'], trace['session_id']]
    salt = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    trace_update(prefix_cache_requested=True)
    return {'cache_salt': salt}


@stage('generation')
def infer(messages, tools, instruction=None, classification_prompt=None, branch_instruction=None, plan_budget=False):
    if not 1 <= len(tools) <= 16:
        raise ValueError('pijit engine supports 1..16 active tools')
    with stage('generation_preparation'):
        options = '\n'.join(f'{label}: {tool["name"]}: {tool.get("description", "")}'
                            for label, tool in zip(LABELS, tools))
        messages = messages + [{'role': 'user', 'content':
            classification_prompt or ('Choose the single next tool needed for the current task. Reply only with its letter.\n' + options)}]
        tails = []
        for index, (label, tool) in enumerate(zip(LABELS, tools)):
            suffix = instruction(tool['name']) if instruction else (
                'Selected tool: ' + tool['name'] + '. Generate ONLY its argument JSON. Schema: ' +
                json.dumps(tool['parameters'], ensure_ascii=False))
            if branch_instruction:
                suffix = branch_instruction(index, tool)
            tails.append([{'role': 'assistant', 'content': label}, {'role': 'user', 'content': suffix}])
        if os.environ.get('PIJIT_SERIAL_PREPARATION') == '1':
            prefix, suffixes = prepare_continuations(messages, tails)
            candidate_ids = labels(len(tools))
        else:
            prepared, candidate_ids = parallel(lambda work: work(), [
                lambda: prepare_continuations(messages, tails), lambda: labels(len(tools))], max_workers=2)
            prefix, suffixes = prepared
    with stage('generation_http'):
        result = post('/v1/openjev/toolcall', {'prompt_ids': prefix, 'candidate_ids': candidate_ids,
            'continuations': suffixes, 'tools': tools, 'max_tokens': PLAN_TOTAL_TOKENS if plan_budget else 2048,
            **session_cache_options(),
            **({'plan_budget': True} if plan_budget else {})})
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


def route_edit(payload):
    """Route explicit, locally supported user clauses after a successful source read."""
    context = payload['context']
    if not any(t['name'] == 'compact_edit' for t in context.get('tools', [])):
        return None
    messages = context['messages']
    user_positions = [i for i, m in enumerate(messages) if m['role'] == 'user']
    if not user_positions:
        return None
    start = user_positions[-1]
    tasks = schema_actions.clauses(text_content(messages[start].get('content')))
    calls, paths_read, attempted = {}, set(), set()
    cwd = Path(payload['cwd']).resolve()
    for message in messages[start + 1:]:
        if message['role'] == 'assistant':
            for block in message.get('content', []):
                if isinstance(block, dict) and block.get('type') == 'toolCall':
                    calls[block['id']] = block
                    if block['name'] == 'compact_edit':
                        args = block['arguments']
                        attempted.update((str((cwd / args['path']).resolve()), clause)
                                         for clause in schema_actions.clauses(args['task']))
        if message['role'] == 'toolResult' and not message.get('isError'):
            call = calls.get(message.get('toolCallId'), {})
            if call.get('name') == 'read':
                path = (cwd / call['arguments']['path']).resolve()
                if path.is_relative_to(cwd) and path.suffix == '.py' and path.is_file():
                    paths_read.add(path)
    batches = {}
    for task in tasks:
        candidates = []
        for path in sorted(paths_read):
            if (str(path), task) in attempted or path.stat().st_size > 200_000:
                continue
            try:
                if schema_actions.can_route(path.read_text(), task):
                    candidates.append(path)
            except (ValueError, SyntaxError, UnicodeError):
                continue
        if len(candidates) == 1:
            batches.setdefault(candidates[0], []).append(task)
    if batches:
        path, clauses = next(iter(batches.items()))
        limit = 1 if any(os.environ.get(key) == '1' for key in
                         ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS')) else 8
        call = {'name': 'compact_edit', 'arguments': {
            'path': str(path.relative_to(cwd)), 'task': ' '.join(clauses[:limit])}}
        trace_update(local_route='supported_user_clause', routed_call=call)
        return {'call': call, 'input_tokens': 0, 'generated_argument_tokens': 0,
                'classification_control_records': 0, 'request_id': 'local-' + uuid.uuid4().hex}
    return None


def guard_directory_read(result, payload, tools):
    call = result['call']
    if call['name'] != 'read' or not any(t['name'] == 'bash' for t in tools):
        return result
    args = call.get('arguments', {})
    if not isinstance(args.get('path'), str):
        return result
    cwd = Path(payload['cwd']).resolve()
    path = (cwd / args['path']).resolve()
    if not path.is_relative_to(cwd) or not path.is_dir():
        return result
    replacement = {'name': 'bash', 'arguments': {'command': shlex.join(['ls', '-la', '--', str(path)])}}
    trace_update(directory_read_redirect={'original_call': call, 'replacement_call': replacement})
    return {**result, 'call': replacement}


def observed_files(payload):
    """Files whose contents were successfully read or supplied by a write."""
    cwd = Path(payload['cwd']).resolve()
    calls, observed = {}, set()
    for message in payload['context']['messages']:
        if message['role'] == 'assistant':
            for block in message.get('content', []):
                if isinstance(block, dict) and block.get('type') == 'toolCall':
                    calls[block['id']] = block
        if message['role'] == 'toolResult' and not message.get('isError'):
            call = calls.get(message.get('toolCallId'), {})
            path = call.get('arguments', {}).get('path')
            if call.get('name') in ('read', 'write') and isinstance(path, str):
                observed.add((cwd / path).resolve())
    return observed


def contextual_tools(payload, tools):
    cwd, known = Path(payload['cwd']).resolve(), observed_files(payload)
    names = lambda paths: sorted({str(p.relative_to(cwd)) if p.is_relative_to(cwd) else str(p) for p in paths})
    entries = []
    with os.scandir(cwd) as iterator:
        for entry in iterator:
            if entry.name.startswith('.'):
                continue
            entries.append(entry.name + ('/' if entry.is_dir(follow_symlinks=False) else ''))
            if len(entries) == 64:
                break
    offered = []
    for tool in copy.deepcopy(tools):
        if tool['name'] == 'write' and entries and not known:
            continue
        if tool['name'] in ('edit', 'compact_edit'):
            eligible = known if tool['name'] == 'edit' else {p for p in known if p.suffix == '.py' and p.is_relative_to(cwd)}
            if not eligible:
                continue
            tool['parameters']['properties']['path'] = {'type': 'string', 'enum': names(eligible)}
        if tool['name'] == 'edit':
            properties = tool['parameters']['properties']
            if 'edits' in properties:
                properties['edits']['minItems'] = 1
            # xgrammar 0.2.3 loses JSON escapes with minLength; the edit tool rejects empty spans.
        offered.append(tool)
    trace_update(plan_known_files=names(known), plan_inventory_entries=len(entries))
    instruction = ('\nLocal workspace root entries (partial listing, filenames only): ' + json.dumps(sorted(entries)) +
                   '\nFiles already observed in prior tool results: ' + json.dumps(names(known)) +
                   '\nRead relevant files together before planning changes to existing files. '
                   'A read in this response does not supply its contents until the next turn. '
                   'Use write for new files; read existing files before replacing them. '
                   'Use nonempty oldText copied exactly from observed content. '
                   'Do not emit placeholder oldText or guessed paths. Once files are observed, group edits and tests.')
    return offered, instruction


def defer_unread_writes(calls, payload, tools):
    """A create-file tool must not bypass the existing-file discovery phase."""
    known, cwd = observed_files(payload), Path(payload['cwd']).resolve()
    for index, call in enumerate(calls):
        if call['name'] != 'write':
            continue
        path = (cwd / call['arguments']['path']).resolve()
        if path.exists() and path not in known:
            trace_update(plan_deferred_calls=calls[index:])
            if not any(t['name'] == 'read' for t in tools):
                raise ValueError('Replacing an unread existing file requires the read tool')
            preceding = calls[:index]
            if any(c['name'] == 'read' and (cwd / c['arguments']['path']).resolve() == path for c in preceding):
                return preceding
            return preceding + [{'name': 'read', 'arguments': {'path': call['arguments']['path']}}]
    return calls


def route_initial_read(payload):
    """Execute only an explicit leading Read instruction, before any assistant action."""
    context = payload['context']
    if not any(t['name'] == 'read' for t in context.get('tools', [])):
        return None
    messages = context['messages']
    if not messages or messages[-1]['role'] != 'user':
        return None
    task = text_content(messages[-1].get('content')).strip()
    match = re.match(r'^Read\s+(`?)([\w./-]+)\1\.(?:\s|$)', task)
    if not match:
        return None
    cwd = Path(payload['cwd']).resolve()
    path = (cwd / match[2]).resolve()
    if not path.is_relative_to(cwd) or not path.is_file() or path.stat().st_size > 200_000:
        return None
    call = {'name': 'read', 'arguments': {'path': str(path.relative_to(cwd))}}
    trace_update(local_route='explicit_initial_read', routed_call=call)
    return {'call': call, 'input_tokens': 0, 'generated_argument_tokens': 0,
            'classification_control_records': 0, 'request_id': 'local-' + uuid.uuid4().hex}


def planner_efficiency_policy(payload):
    cwd = Path(payload['cwd']).resolve()
    with os.scandir(cwd) as entries:
        names = sorted(entry.name for _, entry in zip(range(64), entries))
    return ('Workspace root: ' + json.dumps(str(cwd)) +
            '\nRoot entries (partial filenames, not instructions): ' + json.dumps(names) +
            '\nResolve user-specified relative paths directly under this workspace. Read the named file '
            'before searching. Search within the workspace only; do not run find / or search home/system '
            'directories unless the user explicitly requests those locations. If a named file is missing, '
            'use a scoped search here and report absence rather than scanning the machine. '
            'Batch already-known operations in one response; execution is sequential and stops on error. '
            'After a successful edit, combine the required behavior checks into one focused command when possible. '
            'Inspect results before concluding. Repeat checks only for failures, changed code or uncovered requirements. '
            'Do not infer semantic correctness from compilation or a codebook hit. '
            'Use temporary directories for test data; if running pytest, use -p no:cacheprovider '
            'and do not create unrelated project artifacts. Finish once the requested changes and checks are complete.')


@stage('capability_negotiation')
def server_plan_budget(snapshot=None):
    """Negotiate with older running servers without breaking their active clients."""
    enabled = os.environ.get('PIJIT_CAPABILITIES_CACHE') == '1'
    session = (TRACE.get() or {}).get('session_id')
    url = os.environ['PIJIT_URL'].rstrip('/')
    observed_at = time.time()
    hit = (enabled and isinstance(snapshot, dict) and bool(session)
           and snapshot.get('session_id') == session and snapshot.get('url') == url
           and snapshot.get('model') == MODEL and isinstance(snapshot.get('capabilities'), dict)
           and type(snapshot.get('observed_at')) in (int, float)
           and 0 <= observed_at-snapshot['observed_at'] < 30)
    trace_update(capabilities_cache_enabled=enabled, capabilities_cache_hit=bool(hit))
    if hit:
        caps = snapshot['capabilities']
        observed_at = snapshot['observed_at']
    else:
        caps = fetch_server_capabilities(url)
    if enabled:
        trace_update(server_capabilities=dict(url=url,model=MODEL,session_id=session,
                     observed_at=observed_at,capabilities=caps))
    trace_update(prefix_cache_supported=caps.get('prefix_cache_version') == 1)
    return (caps.get('plan_budget_version') == 1 and caps.get('per_tool_limit') == 2048
            and caps.get('max_steps') == 8 and caps.get('max_plan_tokens', 0) >= PLAN_TOTAL_TOKENS)


def fetch_server_capabilities(url):
    headers = {}
    if os.environ.get('PIJIT_API_KEY'):
        headers['Authorization'] = 'Bearer '+os.environ['PIJIT_API_KEY']
    request = urllib.request.Request(url+'/v1/openjev/capabilities', headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise



def plan_history(messages):
    """Preserve the model's native assistant-call / tool-result protocol."""
    result=[]
    for message in messages:
        role=message['role']
        content=message.get('content', [])
        if role=='assistant':
            blocks=content if isinstance(content,list) else []
            text=text_content([b for b in blocks if b.get('type')!='toolCall']) if isinstance(content,list) else text_content(content)
            calls=[dict(id=b['id'],type='function',function=dict(name=b['name'],arguments=json.dumps(b['arguments'],ensure_ascii=False)))
                   for b in blocks if b.get('type')=='toolCall']
            converted=dict(role='assistant',content=text or None)
            if calls: converted['tool_calls']=calls
            result.append(converted)
        elif role=='toolResult':
            raw=text_content(content)
            if message.get('toolName')=='plan':
                try:
                    data=json.loads(raw)
                    if isinstance(data,dict) and 'results' in data and 'learning' in data:
                        data.pop('learning')
                        raw=json.dumps(data,ensure_ascii=False)
                except (ValueError,TypeError):
                    pass
            result.append(dict(role='tool',tool_call_id=message.get('toolCallId',''),name=message.get('toolName','plan'),
                               content='PLAN EXECUTION RESULT error='+str(message.get('isError',False))+':\n'+raw))
        elif role=='user':
            result.append(dict(role='user',content=text_content(content)))
    return result


def latest_plan_result(messages):
    """Render the latest execution once without nested JSON-string escaping."""
    latest_user = max((i for i, m in enumerate(messages) if m['role']=='user'), default=-1)
    calls = {}
    latest = ''
    for message in messages[latest_user+1:]:
        if message['role']=='assistant':
            for block in message.get('content', []):
                if isinstance(block, dict) and block.get('type')=='toolCall':
                    calls[block['id']] = block.get('arguments', {})
        elif message['role']=='toolResult':
            raw = text_content(message.get('content'))
            try:
                result = json.loads(raw)
            except (ValueError, TypeError):
                result = None
            if message.get('isError') and isinstance(result, dict):
                steps = calls.get(message.get('toolCallId'), {}).get('steps', [])
                index = result.get('failed_step')
                failed = steps[index] if type(index) is int and 0 <= index < len(steps) else {}
                latest = ('LATEST EXECUTION FAILED. Completed earlier steps remain applied.\nFAILED CALL:\n'
                          +json.dumps(failed, ensure_ascii=False)+'\nERROR OUTPUT:\n'+str(result.get('error', raw))
                          +'\nReconcile the actual output with the CURRENT requirements. A self-written assertion may be wrong; '
                          'fix the implementation or the check, then run the corrected check. Do not repeat an unchanged failed command.')
            else:
                latest = 'LATEST EXECUTION '+('FAILED' if message.get('isError') else 'SUCCEEDED')+'. Use its actual results in the conversation.'
    return latest


def generic_plan_chat(payload):
    tools = payload.get('inner_tools', [])
    allowed = {'read', 'write', 'edit', 'bash', 'grep', 'find', 'ls'}
    if not tools or len({t['name'] for t in tools}) != len(tools) or any(t['name'] not in allowed for t in tools):
        raise ValueError('Invalid Pi inner tool catalog')
    budget_enabled = server_plan_budget(payload['server_capabilities']) if payload.get('server_capabilities') else server_plan_budget()
    trace_update(plan_budget_supported=budget_enabled, plan_budget_mode='per_subtool' if budget_enabled else 'legacy_plan_2048')
    context = payload['context']
    task = next((text_content(m.get('content')) for m in reversed(context['messages']) if m['role']=='user'), '')
    book = tool_plan.ToolContentBook(paths(payload['cwd'])/'tool-plan-codebook.sqlite3')
    retrieval_start = time.perf_counter()
    book_entries = book.count()
    compact_catalog = os.environ.get('PIJIT_COMPACT_CATALOG') == '1'
    reuse_routing = os.environ.get('PIJIT_REUSE_ROUTING') == '1'
    reuse_enabled = os.environ.get('PIJIT_PLAN_DISABLE_REUSE') != '1'
    candidate_limit = min(2 if compact_catalog or reuse_routing else 7, 15-len(tools)) if reuse_enabled else 0
    trace_update(plan_reuse_enabled=reuse_enabled)
    payload_mismatches = 0
    def retrieve(content_book, template=False):
        def eligible(entry):
            nonlocal payload_mismatches
            compatible = tool_plan.compatible_payload(dict(entry, plan_template=template), task)
            payload_mismatches += not compatible
            return compatible
        return content_book.candidates(task, {}, limit=candidate_limit, eligible=eligible)
    can_reuse_write = reuse_enabled and any(t['name']=='write' for t in tools)
    candidates = retrieve(book) if can_reuse_write else []
    template_book = None
    if can_reuse_write and os.environ.get('PIJIT_PLAN_TEMPLATES') == '1':
        template_book = tool_plan.ToolContentBook(paths(payload['cwd'])/'tool-plan-templates.sqlite3')
        templates = [dict(entry, plan_template=True) for entry in retrieve(template_book, template=True)]
        candidates = (templates + candidates)[:candidate_limit]
    candidates = [dict(entry, request_delta=tool_plan.request_delta(entry['contract'], task),
                       contract_changes=tool_plan.contract_changes(entry['contract'], task))
                  for entry in candidates]
    trace_update(payload_mismatch_candidates=payload_mismatches)
    retrieval_seconds = time.perf_counter()-retrieval_start
    trace_update(template_entries=template_book.count() if template_book else 0)
    trace_update(generic_plan=True, book_entries=book_entries, candidate_count=len(candidates), retrieval_seconds=retrieval_seconds)
    success_reply = os.environ.get('PIJIT_PLAN_SUCCESS_REPLY') == '1'
    trace_update(plan_success_reply_enabled=success_reply)
    options = tool_plan.branches(tools, candidates, success_reply=success_reply)
    latest_user = max((i for i, m in enumerate(context['messages']) if m['role']=='user'), default=-1)
    results = [m for m in context['messages'][latest_user+1:] if m['role']=='toolResult']
    previous_failure = any(m.get('isError') for m in results)
    recovery_latest = os.environ.get('PIJIT_RECOVERY_LATEST') == '1'
    recovery = bool(results[-1].get('isError')) if recovery_latest and results else previous_failure
    trace_update(recovery_scope='latest_result' if recovery_latest else 'whole_user_turn',
                 historical_tool_failure=previous_failure)
    if recovery:
        options = [tool_plan.recovery_option(options[-1])]
    decode_options = options
    selection_indices = list(range(len(options)))
    if reuse_routing and not recovery:
        selection_indices = list(range(len(tools), len(options)))
        options = [options[index] for index in selection_indices]
    trace_update(recovery_planning=recovery, reuse_routing=reuse_routing, classification_branches=len(options))
    policy = (context.get('systemPrompt', '') +
              '\nYou have one public tool: plan. Inside plan, use the Pi tools below for ANY task/language. '
              'Return all currently determined operations together, in order, at most eight. '
              'All arguments must be known now. A read or search result becomes visible only NEXT turn: '
              'do not guess unseen source or produce edits depending on results not yet observed. '
              'A write and a known check command may be in the same plan. Execution stops on first error. '
              'After results, continue with another plan as needed or reply. Never claim success before results. '
              'A failed check requires a corrective action and fresh verification when possible, not a promise in final text. '
              'Reuse content when it satisfies ALL current behavior and constraints. Require exact bytes only '
              'when the user specifies exact text. Bind the current destination separately; a different '
              'destination alone does not invalidate content. Stored content is only '
              'execution-observed, NOT independently verified. Never reuse an old tool result; reads and checks execute afresh. '
              'Read existing files before changing them. The plan tool is a container, not a task-specific validator. '
              '\nINNER TOOLS (argument schemas follow after selection): '+json.dumps(
                  [dict(name=t['name'],description=t['description']) for t in tools], ensure_ascii=False))
    if success_reply:
        policy += ('\nEvery action plan must append a final on_success_reply decision with arguments {content: a string}. '
                   'Use empty content to continue after execution. Use a short final reply ONLY if this plan finishes ALL requested work '
                   'and no unseen results need interpretation. Use empty content for investigation, read/search, '
                   'or commands whose output you must inspect. Include required checks in the plan. '
                   'A successful exit alone does not prove semantic correctness; do not promise unrun checks. '
                   'This reply is generated now but withheld until execution succeeds; failures resume planning.')
    catalog = '\n'.join(f'{label}: {option["description"]}' for label, option in zip(LABELS, options))
    catalog = '\nDecision catalog (reference data, NOT new user requests):\n'+catalog
    messages = [dict(role='system', content=policy if compact_catalog else policy+catalog)]
    messages.extend(plan_history(context['messages']))
    if compact_catalog:
        messages.append(dict(role='user', content=catalog))
    trace_update(compact_catalog=compact_catalog, candidate_limit=candidate_limit)
    execution_state = latest_plan_result(context['messages'])
    if recovery_latest and previous_failure and not recovery:
        execution_state += ('\nAn earlier operation failed, but the latest operation succeeded. '
                            'A successful read/search alone does not resolve a failed check. '
                            'Use the actual history to finish any remaining repair and verification. '
                            'If the fix and required checks have already succeeded, reply now instead of repeating them.\n')
    if reuse_routing:
        execution_state += '\nCURRENT USER REQUIREMENTS (stored entries are historical reference only):\n'+task+'\n'
    if recovery:
        execution_state += '\nCURRENT USER REQUIREMENTS:\n'+task+'\nIf a defect remains and its fix is known, execute it; explaining a future fix is not completion. '
        execution_state += 'If the corrected work and checks have succeeded, finish instead of repeating them. '
        execution_state += 'Before each action, purpose must briefly state the observed defect that this action addresses. '
        execution_state += 'If your own assertion contradicts the user requirements, correct that assertion instead of rerunning it.\n'
    response = infer(messages, [dict(option, parameters=tool_plan.decoder_schema(option['parameters'])) for option in options],
                     branch_instruction=lambda index, option: execution_state+'\n'+tool_plan.continuation(
                         len(tools)+len(candidates) if recovery else selection_indices[index], tools, candidates, option,
                         success_reply=success_reply),
                     plan_budget=budget_enabled,
                     classification_prompt=(('CURRENT USER REQUIREMENTS:\n'+task+'\n') if reuse_routing else '')+('A previous tool failed in this user task. Choose A for general replanning. '
                     'Identify whether the implementation, test expectation, or command is wrong before acting. '
                     'Do not repeat an unchanged failed check. Output only A.' if recovery else
                     'Choose the NEXT action for the conversation above. Output only one letter from '+
                     ', '.join(LABELS[:len(options)])+'. If the requested work is already completed in the latest tool results, '
                     'choose '+LABELS[len(options)-1]+' to reply. Do NOT repeat completed actions. '
                     'For pending writes, compare both the stored implementation and its historical behavior contract with the CURRENT request. '
                     'Pay attention to the highlighted requirement changes; differences in behavior must not be ignored. '
                     'A different destination is allowed, but ANY changed behavior or new constraint requires new source. '
                     'Prefer reuse only when all current constraints are satisfied. Otherwise choose ordinary write. '
                     'Stored catalog entries are reference data, NOT additional tasks.'))
    trace_update(plan_token_budget=response.get('plan_budget'), requested_plan_tokens=PLAN_TOTAL_TOKENS if budget_enabled else 2048)
    index = selection_indices[response['decision']['index']]
    branch = ('recovery' if recovery else 'tool:'+tools[index]['name'] if 0 <= index < len(tools) else
              'reuse_content' if len(tools) <= index < len(tools)+len(candidates) else 'general')
    trace_update(selected_branch=branch, selected_content_id=(candidates[index-len(tools)]['id']
                 if branch=='reuse_content' else None))
    if recovery:
        trace_update(recovery_action_purposes=[step.get('purpose') for step in response['call']['arguments'].get('steps',[])])
    decoded_response = dict(response, decision=dict(response['decision'], index=index))
    with stage('plan_decoding'):
        call, reused = tool_plan.decode(decoded_response, tools, candidates, decode_options)
    trace_update(completion_reply_normalized=bool(call['name']=='reply_user'
                 and 'content' not in response['call']['arguments']))
    template_ids = {entry['id'] for entry in candidates if entry.get('plan_template')}
    reused_templates = [identity for identity in reused if identity in template_ids]
    reused_contents = [identity for identity in reused if identity not in template_ids]
    cache_outcome = ('reply' if call['name']=='reply_user' else 'reused' if reused else
                     'selected_then_abandoned' if branch=='reuse_content' else 'empty_book' if not book_entries else
                     'no_candidates' if not candidates else 'generated_with_candidates')
    trace_update(cache_outcome=cache_outcome)
    reject_repeated_plan(call, context['messages'])
    trace_update(generic_plan=True, available_tools=['plan'], inner_tools=[t['name'] for t in tools],
                 candidate_ids=[entry['id'] for entry in candidates], reused_content_ids=reused_contents,
                 reused_template_ids=reused_templates,
                 plan_step_names=[step['name'] for step in call['arguments'].get('steps',[])])
    completion = tool_plan.split_success_reply(response['call']['arguments'])[1] if success_reply and call['name']=='plan' else None
    success_text = completion['content'] if completion else None
    expected_outputs = completion.get('expected_outputs', []) if completion else []
    trace_update(plan_completion_decision=('continue' if success_text == '' else 'finish' if success_text else None),
                 missing_completion_decision=bool(success_reply and call['name']=='plan' and completion is None),
                 expected_output_count=len(expected_outputs))
    trace_update(planned_success_reply=bool(success_text))
    return dict(response, call=call, plan_task=task, on_success_reply=success_text, expected_plan_outputs=expected_outputs,
                reused_content_ids=reused_contents,
                reused_template_ids=reused_templates, generic_plan=True, cache_hit=bool(reused), plan_budget_supported=budget_enabled)


def reject_repeated_plan(call, messages):
    if call['name'] != 'plan':
        return
    latest = max((i for i, m in enumerate(messages) if m['role']=='user'), default=-1)
    previous, last_completed, repeated_failures = {}, None, 0
    for message in messages[latest+1:]:
        if message['role']=='assistant':
            for block in message.get('content', []):
                if isinstance(block, dict) and block.get('type')=='toolCall' and block['name']=='plan':
                    previous[block['id']] = block['arguments']
        elif message['role']=='toolResult':
            attempted = previous.get(message.get('toolCallId'))
            repeated_failures = repeated_failures + 1 if message.get('isError') and attempted == call['arguments'] else 0
            last_completed = None if message.get('isError') else attempted
    if repeated_failures >= 2:
        raise ValueError('Repeated identical failed plan rejected after one retry; task remains incomplete')
    if last_completed == call['arguments'] and any(s['name'] in ('write','edit') for s in call['arguments']['steps']):
        raise ValueError('Duplicate completed mutation plan rejected; no tools executed again')


def complete_tool_plan(payload):
    # Called by the local executor only after all steps completed successfully.
    book = tool_plan.ToolContentBook(paths(payload['cwd'])/'tool-plan-codebook.sqlite3')
    reused = payload.get('reused_content_ids', [])
    reused_sources = set()
    if reused:
        with book.connection() as db:
            reused_sources = {row[0] for row in db.execute(
                'SELECT source FROM entries WHERE id IN ('+','.join('?' for _ in reused)+')', reused)}
    reused_templates = payload.get('reused_template_ids', [])
    templates = None
    if os.environ.get('PIJIT_PLAN_TEMPLATES') == '1':
        templates = tool_plan.ToolContentBook(paths(payload['cwd'])/'tool-plan-templates.sqlite3')
        if reused_templates:
            with templates.connection() as db:
                reused_sources.update(json.loads(row[0])['content'] for row in db.execute(
                    'SELECT source FROM entries WHERE id IN ('+','.join('?' for _ in reused_templates)+')', reused_templates))
    writes = [step['arguments']['content'] for step in payload['steps']
              if step['name']=='write' and step['arguments']['content'] not in reused_sources]
    admitted = book.admit([(payload['task'], content, 'tool_execution_succeeded; semantic_correctness_unverified')
                           for content in writes]) if writes else []
    if reused:
        book.record_reuse(reused)
    template_admitted = []
    if templates is not None:
        source = tool_plan.plan_template.capture(payload['steps'])
        if source and not reused_templates:
            template_admitted = templates.admit([(payload['task'], source, 'tool_execution_succeeded')])
        templates.record_reuse(reused_templates)
    trace_update(template_admitted=template_admitted, reused_template_ids=reused_templates)
    trace_update(generic_plan=True, plan_completed=True, executed_tools=[s['name'] for s in payload['steps']])
    return dict(admitted=admitted, cache_hit=bool(reused or reused_templates), admission_count=len(admitted),
                template_admitted=template_admitted,
                admission_reason='new_write_content' if admitted else 'deduplicated_or_reused' if any(s['name']=='write' for s in payload['steps']) else 'no_write_steps',
                book_entries_after=book.count(), validation='tool execution only; not semantic verification')


def plan_validator_command():
    command = json.loads(os.environ.get('PIJIT_PLAN_VERIFY_ARGV', '[]'))
    if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg.strip() for arg in command):
        raise ValueError('A trusted PIJIT_PLAN_VERIFY_ARGV validator is required; no ordinary-tool fallback in plan-only mode')
    return command


def strict_plan_chat(payload):
    """Expose exactly one action; ordinary text remains available after its result."""
    plan_validator_command()
    if os.environ.get('PIJIT_ADAPTIVE_PLAN') != '1':
        raise ValueError('Plan-only mode requires adaptive plan and a trusted validator')
    context = dict(payload['context'])
    context['tools'] = [tool for tool in context.get('tools', []) if tool['name'] == 'plan']
    if len(context['tools']) != 1:
        raise ValueError('Plan-only mode requires exactly one registered plan tool')
    messages = context['messages']
    latest_user = max((i for i, message in enumerate(messages) if message['role'] == 'user'), default=-1)
    attempted = any(message['role'] == 'toolResult' and message.get('toolName') == 'plan'
                    for message in messages[latest_user + 1:])
    policy = ('STRICT PLAN-ONLY MODE. The only executable tool is plan. Never call read, write, edit, bash, '
              'compact_edit or other tools. Create new Python modules with full behavior contracts through plan. '
              'Do not suggest ordinary-tool recovery. The configured trusted validator performs checks. '
              'After a plan result, report its actual outcome; if unsupported or rejected, explain the limitation. '
              'Do not claim that plain text code was executed or admitted. Existing outputs cannot be overwritten.')
    trace_update(native_planner=True, plan_only=True, available_tools=['plan'])
    result = native_planner.chat(dict(payload, context=context), post, MODEL, policy,
                                 max_tokens=int(os.environ.get('PIJIT_PLANNER_MAX_TOKENS', '2048')),
                                 tool_choice=None if attempted else 'plan')
    calls = result.get('calls') or [result['call']]
    if len(calls) != 1 or calls[0]['name'] not in (('plan', 'reply_user') if attempted else ('plan',)):
        raise ValueError('Plan-only mode rejected a response outside the plan protocol')
    return result


def chat(payload):
    if os.environ.get('PIJIT_TOOL_PLAN') == '1':
        return generic_plan_chat(payload)
    if os.environ.get('PIJIT_PLAN_ONLY') == '1':
        return strict_plan_chat(payload)
    batched = os.environ.get('PIJIT_BATCH_TOOLS') == '1'
    efficient = os.environ.get('PIJIT_PLANNER_EFFICIENCY') == '1'
    if efficient:
        routed = route_initial_read(payload)
        if routed is not None:
            return routed
    if os.environ.get('PIJIT_LOCAL_ROUTING') == '1' and (not batched or os.environ.get('PIJIT_BATCH_LOCAL_ROUTING') == '1'):
        routed = route_edit(payload)
        if routed is not None:
            return routed
    if os.environ.get('PIJIT_NATIVE_PLANNER') == '1':
        policy = ((Path(__file__).parent / 'requirements.txt').read_text()
                  if os.environ.get('PIJIT_COMPLETION_CHECKS') == '1' else '')
        if efficient:
            policy += '\n' + planner_efficiency_policy(payload)
        available = [tool['name'] for tool in payload['context'].get('tools', [])]
        if os.environ.get('PIJIT_ADAPTIVE_PLAN') == '1' and 'plan' in available:
            policy += ('\nFor requested NEW Python modules, use the plan tool with workspace-relative destination paths '
                       'and COMPLETE per-module behavior contracts, including imports and negative constraints. '
                       'Do not pre-create empty output files. Do not implement those modules through write or bash '
                       'before trying plan. Existing-file edits and non-Python outputs use ordinary tools. '
                       'After a plan error, use the reported verification failure to recover with ordinary tools. '
                       'Avoid repeating an inventory or source read already present in observations.')
        first_plan = (os.environ.get('PIJIT_ADAPTIVE_PLAN') == '1' and 'plan' in available
                      and not any(m['role'] == 'assistant' for m in payload['context']['messages']))
        trace_update(native_planner=True, available_tools=available)
        return native_planner.chat(payload, post, MODEL, policy,
                                   workspace_cache=os.environ.get('PIJIT_NATIVE_PREFIX_CACHE') == '1',
                                   cache_namespace=str(STATE.resolve()),
                                   max_tokens=int(os.environ.get('PIJIT_PLANNER_MAX_TOKENS', '2048')),
                                   tool_choice='plan' if first_plan else None)
    context = payload['context']
    tools = [{key: t[key] for key in ('name', 'description', 'parameters')} for t in context.get('tools', [])]
    contextual = batched and os.environ.get('PIJIT_PLAN_CONTEXT') == '1'
    plan_instruction = ''
    if contextual:
        with stage('plan_preparation'):
            tools, plan_instruction = contextual_tools(payload, tools)
    tools.append({'name': 'reply_user', 'description': 'Deliver the final answer, or ask the user a necessary question.',
                  'parameters': {'type': 'object', 'properties': {'content': {'type': 'string'}},
                                 'required': ['content'], 'additionalProperties': False}})
    plan = batch_tool(tools) if batched and len(tools) < 16 else None
    system = context.get('systemPrompt', '') + '\nAll output is a tool call. Select reply_user to answer. '
    system += ('For supported Python changes prefer compact_edit; read the file first. '
               'Use normal edit/write for unsupported edits or new files. Do not call compact_edit again '
               'for a change already reported as applied. Test changes when appropriate.\nTOOLS:\n' +
               json.dumps(tools, ensure_ascii=False))
    system += plan_instruction
    if any(t['name'] == 'compact_edit' for t in tools):
        system += ('\nWhen all requested changes to an existing Python file are call keyword/default changes '
                   '(including integer/float/string/boolean CLI defaults, help and required), option aliases, '
                   'function-entry guards, or catch/return, select compact_edit rather than edit/write. '
                   'Copy the requested edit clauses into task; exclude test commands and final-answer instructions. '
                   'Keep ordinary edit/write for unsupported transformations, other languages and new files. '
                   'Read files before editing. Read files, not directories; use bash to list directories. ')
        if os.environ.get('PIJIT_SCHEMA_ACTIONS') == '1' or os.environ.get('PIJIT_JIT_ACTIONS') == '1':
            system += 'Use one atomic change per compact_edit call.'
        else:
            system += 'Group up to eight related supported changes to the same file into one compact_edit call.'
    if any(t['name'] == 'set_cli_default' for t in tools):
        system += '\nFor an existing integer argparse default prefer set_cli_default; read the current default first.'
    if plan:
        system += ('\nUse execute_plan to return a list of 1 to 8 already-determined operations in one turn. '
                   'Read known relevant files together. Once source is known, batch all edits and the test command. '
                   'Include requested test additions as edits, not merely running existing tests. '
                   'Do not split already-known edits and their test command across separate turns. '
                   'Steps execute in order and stop on the first error. All arguments must be known now: '
                   'never guess unread source or depend on discovering an earlier step result. '
                   'Wait for results before reporting success; reply_user cannot be a plan step.')
    if os.environ.get('PIJIT_COMPLETION_CHECKS') == '1':
        system += '\n' + (Path(__file__).parent / 'requirements.txt').read_text() + '\n'
    messages = [{'role': 'system', 'content': system}]
    for message in context['messages']:
        role = message['role']
        text = text_content(message.get('content'))
        if role == 'toolResult':
            role = 'user'
            text = f'TOOL RESULT {message.get("toolName", "")} id={message.get("toolCallId", "")} error={message.get("isError", False)}:\n{text}'
        if role in ('user', 'assistant'):
            messages.append({'role': role, 'content': text})
    inference_tools = ([t for t in tools if t['name'] not in
                        {'read', 'edit', 'write', 'bash', 'compact_edit'}] + [plan]) if plan else tools
    result = infer(messages, inference_tools)
    if result['call']['name'] == 'execute_plan':
        if plan is None:
            raise ValueError('Batch tool is not enabled')
        import jsonschema
        jsonschema.validate(result['call']['arguments'], plan['parameters'])
        calls = result['call']['arguments']['steps']
        if contextual:
            calls = defer_unread_writes(calls, payload, tools)
        if os.environ.get('PIJIT_DIRECTORY_GUARD') == '1':
            calls = [guard_directory_read({'call': call}, payload, tools)['call'] for call in calls]
        trace_update(batch_tool_count=len(calls), batch_tool_names=[c['name'] for c in calls])
        return {**result, 'calls': calls}
    if os.environ.get('PIJIT_DIRECTORY_GUARD') == '1':
        result = guard_directory_read(result, payload, tools)
    return result


def batch_tool(tools):
    steps = [{'type': 'object', 'properties': {
        'name': {'const': t['name']}, 'arguments': t['parameters']},
        'required': ['name', 'arguments'], 'additionalProperties': False}
        for t in tools if t['name'] in {'read', 'edit', 'write', 'bash', 'compact_edit'}]
    if not steps:
        return None
    return {'name': 'execute_plan', 'description':
            'Plan all known remaining operations together: 1 to 8 tool calls in order; stop on error.',
            'parameters': {'type': 'object', 'properties': {'steps': {
                'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': {'oneOf': steps}}},
                'required': ['steps'], 'additionalProperties': False}}


def task_key(task):
    # Conservative reuse: identical wording, allowing one unambiguous integer binding.
    if jit.integer_binding(task) is not None:
        task = re.sub(r'(?<![\w.])-?\d+(?!\w|\.\d)', '{integer}', task)
    return ' '.join(task.split())


def bound_edit(source, task, *, existing_alias=False):
    """Bind only the complete explicit CLI requests supported by the local parser."""
    edits = schema_actions.bind_edit(source, task, existing_alias=existing_alias)
    if edits is None:
        return None
    nodes = protocol.compact.base.catalogue(source)
    targets = [name for name, key in protocol.compact.selectors(source)['C'].items()
               if any(isinstance(arg, ast.Constant) and arg.value == edits[0][1] for arg in nodes[key].args)]
    if len(targets) != 1:
        return None
    edits[0][1] = targets[0]
    return edits


def matches_bound_edit(candidate, edits):
    # JSON comparison preserves bool/int distinctions that Python equality loses.
    return candidate is not None and json.dumps(candidate['edits']) == json.dumps(edits)


def cache_match_basis(source, task, candidate, bound):
    if candidate is None:
        return None
    if bound is not None and matches_bound_edit(candidate, bound):
        return 'explicit_binding'
    if (candidate.get('exact_task') == task.strip()
            and candidate.get('source_sha256') == jit.digest(source)):
        return 'exact_task'
    return None


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
        operations = sorted({edit[0] for candidate in candidates if candidate for edit in candidate['edits']})
        guide = '\n'.join(op + ': ' + ' '.join(protocol.OPS[op]) for op in operations if op in protocol.OPS)
        choices = '\n'.join(label + ': ' + (json.dumps({'edits': candidate['edits']}, ensure_ascii=False) if candidate else
            'NONE: no entry exactly satisfies the task') for label, candidate in zip(LABELS, candidates))
        prompt, ids = prepare_classification([{'role': 'system', 'content':
            'Select a cached edit ONLY if it satisfies the entire task. Otherwise NONE. Return its letter.\n'
            'Each edit starts with an operation name; its remaining fields are defined below.\n' + guide + '\n' + choices},
                           {'role': 'user', 'content': 'SOURCE:\n' + source + '\nTASK:\n' + task}], len(candidates))
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
    bound = bound_edit(source, task)
    bound_match = bound is not None and matches_bound_edit(candidates[selected], bound)
    candidate = candidates[selected]
    exact_match = (candidate is not None and candidate.get('exact_task') == task.strip()
                   and candidate.get('source_sha256') == jit.digest(source))
    supported_match = bound_match or exact_match
    reasons = []
    if candidates[selected] is None:
        reasons.append('selected_none')
    elif bound is not None and not bound_match:
        reasons.append('explicit_binding_mismatch')
    elif candidate.get('exact_task') is not None and not exact_match:
        reasons.append('exact_task_mismatch')
    if candidate is not None and not supported_match:
        reasons.append('unverified_task_match')
    if not supported_match and gate['conditional_probability'] < 0.95:
        reasons.append('low_conditional_probability')
    if not supported_match and gate['margin'] < 3:
        reasons.append('low_margin')
    accepted = not reasons
    decision.update(gate=gate, accepted=accepted, rejection_reasons=reasons,
                    acceptance_basis=cache_match_basis(source, task, candidate, bound) if accepted else None)
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
    safe_book = os.environ.get('PIJIT_SAFE_CODEBOOK') == '1'
    verify_command = os.environ.get('PIJIT_VERIFY_CMD', '')
    verify_key = jit.digest(verify_command) if verify_command else None
    if safe_book and any(os.environ.get(key) == '1' for key in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS')):
        raise ValueError('Safe codebook cannot be combined with schema/JIT action modes')
    with stage('retrieval'):
        source = path.read_bytes().decode('utf-8')
        if len(source.encode()) > 200_000:
            raise ValueError('compact_edit currently limits source files to 200 KB')
        ast.parse(source)
        before = jit.digest(source)
        allowed = protocol.compact.task_scope(source, task)
        book = jit.Codebook()
        bookfile = directory / 'codebook.json'
        schema_mode = os.environ.get('PIJIT_SCHEMA_ACTIONS') == '1'
        enabled = (os.environ.get('PIJIT_DISABLE_CODEBOOK') != '1' and not schema_mode
                   and os.environ.get('PIJIT_JIT_ACTIONS') != '1')
        trace_update(codebook_enabled=enabled, cache_hit=False, applied=False)
        if enabled and bookfile.exists():
            book.entries = json.loads(bookfile.read_text())
        targets = set().union(*(set(t) for t in protocol.compact.scoped_selectors(source, allowed).values()))
        # Explicit bindings allow supported paraphrases; other tasks retain exact wording checks.
        bound = bound_edit(source, task)
        eligible = [e for e in book.entries if e.get('path') == str(path)
                    and (bound is not None or e.get('task_key') == task_key(task))]
        if safe_book and bound is None:
            eligible = [e for e in eligible if verify_key is not None
                        and e.get('reuse_policy') == 'verified-v1'
                        and e.get('verification_command_sha256') == verify_key]
        candidate_book = jit.Codebook()
        candidate_book.entries = eligible
        options = candidate_book.retrieve(source, task, targets, bound=bound)
        if bound is not None:
            options = [candidate for candidate in options if matches_bound_edit(candidate, bound)]
        options = [candidate for candidate in options if cache_match_basis(source, task, candidate, bound)]
        if safe_book and len(options) > 1:
            options = []  # Ambiguous learned outputs must be regenerated, not guessed.
        trace_update(retrieval={'book_entries': len(book.entries), 'task_path_matches': len(eligible),
                                'source_matches': sum(e['source_sha256'] == before for e in eligible),
                                'candidate_count': len(options)}, candidates=options)
    exact_enabled = os.environ.get('PIJIT_JIT_ACTIONS') == '1' and os.environ.get('PIJIT_DISABLE_CODEBOOK') != '1'
    exact_file = directory / 'jit-actions.json'
    exact = jit.ExactCodebook(json.loads(exact_file.read_text()) if exact_enabled and exact_file.exists() else [])
    exact_entry = exact.retrieve(source, task, path) if exact_enabled else None
    trace_update(jit_entries_before=len(exact.entries), jit_hit=False)
    requests = []
    candidate = None
    bound_reuse = False
    exact_reuse = False
    fallback = 'empty_or_inapplicable_codebook' if enabled else 'codebook_disabled'
    trace_update(fallback_reason=fallback)
    if options and not exact_enabled:
        if safe_book and len(options) == 1:
            candidate = options[0]
            bound_reuse = cache_match_basis(source, task, candidate, bound) == 'explicit_binding'
            exact_reuse = not bound_reuse
        elif os.environ.get('PIJIT_BOUND_REUSE') == '1' and bound is not None and len(options) == 1:
            candidate, bound_reuse = options[0], True
        else:
            candidate, record = pick_cached(source, task, options)
            requests.append(record)
            fallback = ','.join(record.get('decision', {}).get('rejection_reasons', [])) or 'none_or_low_confidence'
            trace_update(fallback_reason=fallback)
    hit = False
    exact_hit = False
    schema_hit = False
    edits = None
    if exact_entry:
        with stage('jit_validation'):
            try:
                edits = exact_entry['edits']
                updated = protocol.compact.typed_decode(source, before, json.dumps(edits, separators=(',', ':'), ensure_ascii=False), 'stop', allowed)
                compile(updated, str(path), 'exec')
                if jit.digest(updated) != exact_entry['updated_sha256']:
                    raise ValueError('JIT result hash mismatch')
                hit = exact_hit = True
            except (ValueError, SyntaxError, TypeError, KeyError):
                edits = None
                trace_update(jit_rejected=True)
    if schema_mode and not hit:
        updated, record = schema_edit(source, task)
        if not record.get('classification_skipped'):
            requests.append(record)
        hit = schema_hit = updated is not None
        fallback = record['fallback_reason']
        if hit and exact_enabled:
            binding = record['binding']
            candidate_edits = [['kw', binding['option'], binding['keyword'], binding['value']]]
            try:
                decoded = protocol.compact.typed_decode(source, before, json.dumps(candidate_edits, separators=(',', ':'), ensure_ascii=False), 'stop', allowed)
                if decoded == updated:
                    edits = candidate_edits
            except (ValueError, SyntaxError, TypeError):
                pass
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
            if bound is not None and not matches_bound_edit({'edits': edits}, bound):
                raise ValueError('Generated edit contradicts the explicit task binding')
            compile(updated, str(path), 'exec')
    backup, verification = apply_edit(path, source, updated, cwd, directory)
    with stage('admission'):
        admitted = 0
        # Both exact snapshots are eligible; this permits a later value change on the new version.
        can_admit = enabled and (not safe_book or bound is not None or bool(verify_command))
        for snapshot in (source, updated) if can_admit else ():
            count = len(book.entries)
            # Exact-task actions must not replay again on their already-edited result.
            if snapshot != source and bound is None:
                continue
            admitted_edits, admitted_bound = edits, bound
            if snapshot != source and matches_bound_edit({'edits': edits}, bound):
                admitted_bound = bound_edit(snapshot, task, existing_alias=True)
                if admitted_bound is None:
                    continue
                admitted_edits = admitted_bound
            book.admit(snapshot, task, admitted_edits, True, bound=admitted_bound, exact_task=admitted_bound is None)
            if len(book.entries) > count:
                book.entries[-1].update(admission=verification, task_key=task_key(task), path=str(path))
                if safe_book:
                    book.entries[-1].update(reuse_policy='verified-v1',
                        verification_command_sha256=verify_key,
                        validation_scope='explicit_binding' if bound is not None else 'configured_project_check')
                admitted += 1
        if enabled:
            atomic_write(bookfile, json.dumps(book.entries[-256:], ensure_ascii=False, indent=2))
        jit_admitted = int(exact_enabled and not exact_hit and edits is not None
                           and exact.admit(source, task, path, edits, updated, verification))
        if jit_admitted:
            atomic_write(exact_file, json.dumps(exact.entries, ensure_ascii=False, indent=2))
        trace_update(jit_admission_origin=('schema' if schema_hit else 'generated') if jit_admitted else None,
                     safe_codebook=safe_book, exact_reuse_hit=hit and exact_reuse,
                     admission_skipped_reason='no_task_binding_or_project_check' if enabled and not can_admit else None,
                     bound_reuse_hit=hit and bound_reuse,
                     cache_hit=hit and not schema_hit, schema_hit=schema_hit, jit_hit=exact_hit,
                     jit_admitted=jit_admitted, jit_entries_after=len(exact.entries), validation=verification)
    return {'path': str(path), 'applied': True, 'cache_hit': hit and not schema_hit, 'schema_hit': schema_hit, 'jit_hit': exact_hit, 'jit_admitted': jit_admitted, 'admitted': admitted,
            'bound_reuse_hit': hit and bound_reuse,
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


def adaptive(payload):
    if os.environ.get('PIJIT_ADAPTIVE_PLAN') != '1':
        raise ValueError('Adaptive plan is not enabled')
    command = plan_validator_command()
    cwd = Path(payload['cwd']).resolve()
    contracts = payload['contracts']
    if not isinstance(contracts, dict) or not contracts or not all(isinstance(c, str) and c.strip() for c in contracts.values()):
        raise ValueError('Provide nonempty per-module contracts')
    normalized = {}
    for name, contract in contracts.items():
        target = (cwd / name).resolve()
        if not target.is_relative_to(cwd) or target == cwd:
            raise ValueError('Plan destination escapes workspace')
        relative = str(target.relative_to(cwd))
        if relative in normalized:
            raise ValueError('Duplicate normalized plan destination')
        normalized[relative] = contract
    contracts = normalized
    directory = paths(str(cwd))
    book = adaptive_plan.PlanBook(directory / 'plan-codebook.sqlite3')
    def verify(path, contract):
        result = subprocess.run(command + [str(path), contract, str(cwd)], cwd=cwd,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError('Trusted project verification failed: ' + (result.stderr or result.stdout)[-1500:])
        return 'Configured validator passed: ' + hashlib.sha256(json.dumps(command).encode()).hexdigest()
    def transport(_url, route, body):
        return post(route, body)
    result = adaptive_plan.run_plan(os.environ['PIJIT_URL'].rstrip('/'), payload['task'], contracts,
                                    cwd, book, verify, transport, reuse=(os.environ.get('PIJIT_PLAN_ONLY') == '1' or os.environ.get('PIJIT_PLAN_DISABLE_REUSE') != '1'))
    attempts = result['attempts']
    trace_update(adaptive_plan=True, recovery=result['recovered'], reuse_steps=result['reuse_steps'],
                 admitted=result['admitted'], candidates=[a['candidate_ids'] for a in attempts],
                 verification_errors=[a.get('verification_error') for a in attempts])
    return dict(paths=list(contracts), validation='trusted project behavior validator',
                cache_hit=result['reuse_steps'] > 0, recovered=result['recovered'], admitted=result['admitted'],
                generated_argument_tokens=sum(a['generated_tokens'] for a in attempts),
                classification_control_records=sum(a['controls'] for a in attempts),
                input_tokens=sum(a['logical_input_tokens'] for a in attempts))


def run(payload):
    started = time.perf_counter()
    trace = {'metrics_version': 2, 'trace_id': uuid.uuid4().hex,
             'session_id': payload.get('session_id'), 'parent_tool_call_id': payload.get('parent_tool_call_id'),
             'workspace_id': hashlib.sha256(str(Path(payload['cwd']).resolve()).encode()).hexdigest() if payload.get('cwd') else None,
             'stage_seconds': {}, 'http_requests': []}
    token = TRACE.set(trace)
    try:
        if os.environ.get('PIJIT_PLAN_ONLY') == '1' and payload['action'] not in ('chat', 'plan', 'plan_stats', 'tool_plan_complete'):
            raise ValueError('Plan-only mode disables ordinary tool execution')
        if payload['action'] == 'tool_plan_complete':
            if os.environ.get('PIJIT_TOOL_PLAN') != '1':
                raise ValueError('Generic tool plan is not enabled')
            result = complete_tool_plan(payload)
        elif payload['action'] == 'plan_stats':
            book = adaptive_plan.PlanBook(paths(payload['cwd']) / 'plan-codebook.sqlite3')
            result = dict(entries=book.count(), tool_plan_entries=tool_plan.ToolContentBook(paths(payload['cwd'])/'tool-plan-codebook.sqlite3').count())
        elif payload['action'] == 'plan':
            result = adaptive(payload)
        else:
            result = chat(payload) if payload['action'] == 'chat' else edit(payload)
        result['status'] = 'ok'
    except Exception as error:
        if is_validation_error(error):
            trace_update(validation_error=dict(rule=error.validator, path=list(error.absolute_path),
                         message=error.message, instance=error.instance))
        result = {'status': 'cancelled' if isinstance(error, CancelledError) else 'error',
                  'error': public_error(error)}
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
        print(json.dumps({'error': public_error(error)}))
        sys.exit(1)
