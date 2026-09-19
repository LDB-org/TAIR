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


@stage('generation')
def infer(messages, tools, instruction=None):
    if not 1 <= len(tools) <= 16:
        raise ValueError('pijit engine supports 1..16 active tools')
    with stage('generation_preparation'):
        options = '\n'.join(f'{label}: {tool["name"]}: {tool.get("description", "")}'
                            for label, tool in zip(LABELS, tools))
        messages = messages + [{'role': 'user', 'content':
            'Choose the single next tool needed for the current task. Reply only with its letter.\n' + options}]
        tails = []
        for label, tool in zip(LABELS, tools):
            suffix = instruction(tool['name']) if instruction else (
                'Selected tool: ' + tool['name'] + '. Generate ONLY its argument JSON. Schema: ' +
                json.dumps(tool['parameters'], ensure_ascii=False))
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


def chat(payload):
    batched = os.environ.get('PIJIT_BATCH_TOOLS') == '1'
    if os.environ.get('PIJIT_LOCAL_ROUTING') == '1' and not batched:
        routed = route_edit(payload)
        if routed is not None:
            return routed
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
    if not supported_match and gate['conditional_probability'] < 0.95:
        reasons.append('low_conditional_probability')
    if not supported_match and gate['margin'] < 3:
        reasons.append('low_margin')
    accepted = not reasons
    decision.update(gate=gate, accepted=accepted, rejection_reasons=reasons,
                    acceptance_basis=('explicit_binding' if bound_match else 'exact_task' if exact_match else 'score_gate') if accepted else None)
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
        candidate_book = jit.Codebook()
        candidate_book.entries = eligible
        options = candidate_book.retrieve(source, task, targets, bound=bound)
        if bound is not None:
            options = [candidate for candidate in options if matches_bound_edit(candidate, bound)]
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
    fallback = 'empty_or_inapplicable_codebook' if enabled else 'codebook_disabled'
    trace_update(fallback_reason=fallback)
    if options and not exact_enabled:
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
        for snapshot in (source, updated) if enabled else ():
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
                admitted += 1
        if enabled:
            atomic_write(bookfile, json.dumps(book.entries[-256:], ensure_ascii=False, indent=2))
        jit_admitted = int(exact_enabled and not exact_hit and edits is not None
                           and exact.admit(source, task, path, edits, updated, verification))
        if jit_admitted:
            atomic_write(exact_file, json.dumps(exact.entries, ensure_ascii=False, indent=2))
        trace_update(jit_admission_origin=('schema' if schema_hit else 'generated') if jit_admitted else None,
                     cache_hit=hit and not schema_hit, schema_hit=schema_hit, jit_hit=exact_hit,
                     jit_admitted=jit_admitted, jit_entries_after=len(exact.entries), validation=verification)
    return {'path': str(path), 'applied': True, 'cache_hit': hit and not schema_hit, 'schema_hit': schema_hit, 'jit_hit': exact_hit, 'jit_admitted': jit_admitted, 'admitted': admitted,
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
