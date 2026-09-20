"""Persisted code reuse using the existing fused vLLM classification endpoint.

One direct entry decision per plan; other outputs may be generated in the same
engine session. Execution and trusted verification remain outside the engine.
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
from pathlib import Path
import tempfile
import time
import urllib.request

from plan_book import PlanBook, digest


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def plan_schema(paths, reuse=False):
    path = dict(type='string', enum=list(paths))
    choices = [obj(dict(op=dict(const='write'), path=path, content=dict(type='string')))]
    if reuse:
        choices.append(obj(dict(op=dict(const='reuse'), path=path)))
    return obj(dict(steps=dict(type='array', minItems=len(paths), maxItems=len(paths), items=dict(anyOf=choices))))


def post(url, route, body):
    request = urllib.request.Request(url + route, data=json.dumps(body).encode(),
                                    headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


@lru_cache(maxsize=256)
def label_token(url, label, transport):
    tokens = transport(url, "/tokenize", dict(model="/model", prompt=label, add_special_tokens=False))["tokens"]
    if len(tokens) != 1:
        raise ValueError("Classification labels must be single tokens")
    return tokens[0]


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
        dict(role='user', content=f'Return ONLY one of these single letters: {", ".join(labels)}. '
             f'Choose {labels[-1]} when no entry applies; this letter means GENERATE. '
             'Do not output the word GENERATE.')]

    def tokenize(msg):
        return transport(url, '/tokenize', dict(model='/model', messages=msg, add_generation_prompt=True,
                         chat_template_kwargs=dict(thinking=False, enable_thinking=False)))['tokens']

    tools, sequences = [], [messages]
    for index, label in enumerate(labels):
        reuse = index < len(entries)
        schema = plan_schema(contracts, reuse)
        instruction = ('Recheck the selected entry against the ENTIRE requested contract. '
                       'If applicable, reuse it with op=reuse and path only; generate remaining outputs. '
                       'If the classification was mistaken, abandon reuse and generate every output '
                       'with op=write IN THIS RESPONSE. Never force an incompatible reuse. ' if reuse else
                       'Generate complete source for every output using op=write. ')
        sequences.append(messages + [dict(role='assistant', content=label), dict(role='user', content=
                         instruction + 'Return ONLY the complete plan JSON. Schema: ' + json.dumps(schema))])
        tools.append(dict(name='plan', parameters=schema))
    # These requests only tokenize; they do not schedule model inference.
    with ThreadPoolExecutor(max_workers=8) as pool:
        label_jobs = [pool.submit(label_token, url, label, transport) for label in labels]
        sequence_jobs = [pool.submit(tokenize, sequence) for sequence in sequences]
        ids = [job.result() for job in label_jobs]
        tokenized = [job.result() for job in sequence_jobs]
    prefix, complete = tokenized[0], tokenized[1:]
    if any(tokens[:len(prefix)] != prefix for tokens in complete):
        raise ValueError('Tokenizer did not preserve the classification prefix')
    tails = [tokens[len(prefix):] for tokens in complete]

    return dict(prompt_ids=prefix, candidate_ids=ids, continuations=tails, tools=tools, max_tokens=2048)


def infer(url, task, contracts, book, transport=post, force_generate=False):
    from jsonschema import validate

    start = time.perf_counter()
    entries = [] if force_generate else book.candidates(task, contracts)
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
    abandoned = index < len(entries) and not any(s['op'] == 'reuse' for s in steps)
    return dict(plan=dict(name='plan', arguments=dict(steps=steps)), response=response, request=payload,
                selected_entry=entries[index]['id'] if index < len(entries) else None,
                classification_abandoned=abandoned, candidate_ids=[e['id'] for e in entries],
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
            try:
                evidence = verifier(path, contracts[step['path']])
            except Exception as error:
                if step['op'] == 'reuse':
                    book.reject(step['entry_id'], contracts[step['path']])
                raise VerificationError(str(error)) from error
            if not isinstance(evidence, str) or not evidence.strip():
                raise VerificationError('Verifier must return evidence')
            if path.read_text() != step['content']:
                raise VerificationError('Verifier modified candidate source')
            if step['op'] == 'write':
                modules.append((contracts[step['path']], step['content'], evidence))
        for step in steps:
            path = folder / step['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x') as stream:
                stream.write(step['content'])
    admitted = book.admit(modules) if modules else []
    reused = [step['entry_id'] for step in steps if step['op'] == 'reuse']
    if reused:
        book.record_reuse(reused)
    return admitted


class VerificationError(ValueError):
    """The trusted validator rejected behavior; no generated result was published."""


def run_plan(url, task, contracts, folder, book, verifier, transport=post, reuse=True):
    """One bounded recovery attempt, forced generation with all costs preserved."""
    attempts = []
    for recovery in (False, True):
        result = infer(url, task, contracts, book, transport, force_generate=(recovery or not reuse))
        attempts.append(result)
        try:
            admitted = execute_and_learn(result, contracts, folder, book, verifier)
            return dict(attempts=attempts, admitted=admitted, recovered=recovery,
                        reuse_steps=sum(s['op']=='reuse' for s in result['plan']['arguments']['steps']),
                        plan=result['plan'])
        except VerificationError as error:
            result['verification_error'] = str(error)
            if recovery:
                raise
