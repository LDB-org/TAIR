"""Persisted code reuse using the existing fused vLLM classification endpoint.

One direct entry decision per plan; other outputs may be generated in the same
engine session. Execution and trusted verification remain outside the engine.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

from jsonschema import validate


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def plan_schema(paths, reuse=False):
    path = dict(type='string', enum=list(paths))
    choices = [obj(dict(op=dict(const='write'), path=path, content=dict(type='string')))]
    if reuse:
        choices.append(obj(dict(op=dict(const='reuse'), path=path)))
    return obj(dict(steps=dict(type='array', minItems=len(paths), maxItems=len(paths), items=dict(anyOf=choices))))


class PlanBook:
    """Atomic, bounded, process-locked publication of verified generated modules."""
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        if data['version'] != 1:
            raise ValueError('Unsupported book version')
        entries = data['entries']
        for entry in entries:
            if entry['source_sha256'] != digest(entry['source']):
                raise ValueError('Corrupt codebook source')
            if entry['id'] != digest(entry['contract'] + '\0' + entry['source']):
                raise ValueError('Corrupt codebook identity')
        return entries

    def admit(self, modules):
        """Internal publication after execute_and_learn has verified the whole plan."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            entries = self.load()
            known = {e['id'] for e in entries}
            admitted = []
            for contract, source, evidence in modules:
                if not contract.strip() or not evidence.strip():
                    raise ValueError('Contract and verification evidence required')
                compile(source, '<admitted>', 'exec')
                identity = digest(contract + '\0' + source)
                if identity in known:
                    continue
                entries.append(dict(id=identity, contract=contract, source=source,
                                    source_sha256=digest(source), verification=evidence))
                known.add(identity)
                admitted.append(identity)
            # The existing endpoint supports 16 candidates, including GENERATE.
            entries = entries[-15:]
            fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix='.plan-book-')
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(dict(version=1, entries=entries), stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return admitted


def post(url, route, body):
    request = urllib.request.Request(url + route, data=json.dumps(body).encode(),
                                    headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def prepare(url, task, contracts, entries, transport=post):
    """Build branch prompts without using expected answers or keyword routing."""
    if not contracts or len(contracts) > 4 or len(entries) > 15:
        raise ValueError('One to four outputs and at most fifteen entries supported')
    labels = 'ABCDEFGHIJKLMNOP'[:len(entries) + 1]
    catalog = {label: dict(id=e['id'], contract=e['contract'], source=e['source'])
               for label, e in zip(labels, entries)}
    catalog[labels[-1]] = 'GENERATE: no listed entry fully satisfies any requested module'
    messages = [dict(role='system', content=(
        'Construct one complete plan for all requested Python modules. Do not execute it. '
        'Choose an entry only if its ENTIRE behavior satisfies a requested module contract. '
        'New encoding, overwrite, directory or API requirements must not be ignored. '
        'If an entry applies, select its letter and reuse it for matching output paths; '
        'generate remaining modules in the same plan. Otherwise choose GENERATE. '
        'An entry is immutable; only its destination path can be bound. '
        'No shell, network, extra files or import-time I/O. Catalog: ' + json.dumps(catalog))),
        dict(role='user', content=json.dumps(dict(task=task, output_contracts=contracts), ensure_ascii=False)),
        dict(role='user', content='Return ONLY the single letter for an applicable entry, or GENERATE if none applies.')]

    def tokenize(msg):
        return transport(url, '/tokenize', dict(model='/model', messages=msg, add_generation_prompt=True,
                         chat_template_kwargs=dict(thinking=False, enable_thinking=False)))['tokens']

    prefix = tokenize(messages)
    tools, tails, ids = [], [], []
    for index, label in enumerate(labels):
        tokens = transport(url, '/tokenize', dict(model='/model', prompt=label, add_special_tokens=False))['tokens']
        if len(tokens) != 1:
            raise ValueError('Classification labels must be single tokens')
        ids.append(tokens[0])
        reuse = index < len(entries)
        schema = plan_schema(contracts, reuse)
        instruction = ('Reuse the selected immutable entry for at least one applicable output using op=reuse and path only. '
                       'Generate complete source for other outputs using op=write. ' if reuse else
                       'Generate complete source for every output using op=write. ')
        complete = tokenize(messages + [dict(role='assistant', content=label), dict(role='user', content=
                            instruction + 'Return ONLY the complete plan JSON. Schema: ' + json.dumps(schema))])
        if complete[:len(prefix)] != prefix:
            raise ValueError('Tokenizer did not preserve the classification prefix')
        tails.append(complete[len(prefix):])
        # The only external call name is plan; branch identity is the decision index.
        tools.append(dict(name='plan', parameters=schema))
    return dict(prompt_ids=prefix, candidate_ids=ids, continuations=tails, tools=tools, max_tokens=2048)


def infer(url, task, contracts, book, transport=post):
    start = time.perf_counter()
    entries = book.load()
    payload = prepare(url, task, contracts, entries, transport)
    prepared = time.perf_counter()
    response = transport(url, '/v1/openjev/toolcall', payload)
    index = response['decision']['index']
    if not 0 <= index <= len(entries) or not response['same_engine_session'] or response['finish_reason'] != 'stop':
        raise ValueError('Invalid or incomplete engine decision')
    if response['classification_control_records'] != 1 or response['call']['name'] != 'plan':
        raise ValueError('Expected one classified plan')
    arguments = response['call']['arguments']
    validate(arguments, payload['tools'][index]['parameters'])
    steps = []
    for step in arguments['steps']:
        if step['op'] == 'reuse':
            entry = entries[index]
            steps.append(dict(step, entry_id=entry['id'], source_sha256=entry['source_sha256'], content=entry['source']))
        else:
            steps.append(dict(step))
    if index < len(entries) and not any(s['op'] == 'reuse' for s in steps):
        raise ValueError('Selected entry was not used')
    return dict(plan=dict(name='plan', arguments=dict(steps=steps)), response=response, request=payload,
                selected_entry=entries[index]['id'] if index < len(entries) else None,
                preparation_seconds=prepared-start, inference_seconds=time.perf_counter()-prepared,
                logical_input_tokens=len(payload['prompt_ids'])+len(payload['continuations'][index]),
                generated_tokens=response['generated_argument_tokens'], controls=1, inference_requests=1)


def execute_and_learn(result, contracts, folder, book, verifier):
    """Verifier(path, contract) must return nonempty trusted evidence or raise.

    Verification is mandatory for reuse too. Failed validation never admits any
    part of a plan. The caller owns the verifier; model-provided tests are not it.
    """
    folder = Path(folder).resolve()
    steps = result['plan']['arguments']['steps']
    names = [s['path'] for s in steps]
    if len(names) != len(set(names)) or set(names) != set(contracts):
        raise ValueError('Wrong, duplicate or missing output paths')
    for step in steps:
        if Path(step['path']).is_absolute() or '..' in Path(step['path']).parts:
            raise ValueError('Path escapes workspace')
        target = (folder / step['path']).resolve()
        if not target.is_relative_to(folder) or target == folder:
            raise ValueError('Path escapes workspace')
        if target.exists():
            raise ValueError('Only new outputs supported')
        if step['op'] == 'reuse' and digest(step['content']) != step['source_sha256']:
            raise ValueError('Corrupt expanded entry')
        compile(step['content'], str(target), 'exec')
    modules = []
    # Validate the entire plan before publishing artifacts or any new entry.
    with tempfile.TemporaryDirectory(prefix='tair-verify-') as directory:
        staging = Path(directory)
        for step in steps:
            path = staging / step['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(step['content'])
        for step in steps:
            path = staging / step['path']
            evidence = verifier(path, contracts[step['path']])
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError('Verifier must return evidence')
            if path.read_text() != step['content']:
                raise ValueError('Verifier modified candidate source')
            if step['op'] == 'write':
                modules.append((contracts[step['path']], step['content'], evidence))
        for step in steps:
            path = folder / step['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x') as stream:
                stream.write(step['content'])
    return book.admit(modules) if modules else []
