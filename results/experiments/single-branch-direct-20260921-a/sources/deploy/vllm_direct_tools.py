"""Pinned vLLM experiment: option logits -> resumable KV -> argument grammar.

Internal control IDs use vLLM's token transport, but are not sampled text.
Mixed batches retain the original sampler for other requests; its classification
row is discarded. Dedicated classification batches bypass the sampler entirely.
"""
import asyncio
import json
import math
import os
import time
import uuid


PLAN_STEP_TOKENS = 2048
PLAN_MAX_STEPS = 8
PLAN_STRUCTURE_TOKENS = 1024
PLAN_TOTAL_TOKENS = PLAN_STEP_TOKENS * PLAN_MAX_STEPS + PLAN_STRUCTURE_TOKENS


class PlanBudgetExceeded(ValueError):
    pass


class StreamingPlanBudget:
    """Inspect closed argument objects; never execute or accept partial JSON."""
    def __init__(self, encode):
        self.encode = encode
        self.stack = []
        self.offset = 0
        self.string_start = None
        self.escaped = False
        self.counts = {}

    def feed(self, text):
        for pos in range(self.offset, len(text)):
            char = text[pos]
            if self.string_start is not None:
                if self.escaped:
                    self.escaped = False
                elif char == '\\':
                    self.escaped = True
                elif char == '"':
                    if self.stack and self.stack[-1]['expect_key']:
                        self.stack[-1]['key'] = json.loads(text[self.string_start:pos+1])
                    self.string_start = None
                continue
            if char == '"':
                self.string_start = pos
            elif char in '{[':
                parent = self.stack[-1] if self.stack else None
                path = parent['path'] + (parent['key'],) if parent else ()
                self.stack.append(dict(path=path, start=pos, kind=char,
                                       key=0 if char == '[' else None, expect_key=char == '{'))
            elif char == ':' and self.stack:
                self.stack[-1]['expect_key'] = False
            elif char == ',' and self.stack:
                frame = self.stack[-1]
                if frame['kind'] == '[':
                    frame['key'] += 1
                else:
                    frame['expect_key'] = True
            elif char in '}]' and self.stack:
                frame = self.stack.pop()
                path = frame['path']
                index = None
                if path == ('first',):
                    index = 0
                elif (len(path) == 3 and path[0] in ('steps', 'rest')
                      and isinstance(path[1], int) and path[2] == 'arguments'):
                    index = path[1] + (path[0] == 'rest')
                if index is not None:
                    value = json.loads(text[frame['start']:pos+1])
                    count = len(self.encode(json.dumps(value, ensure_ascii=False, separators=(',', ':'))))
                    self.counts[index] = count
                    if count > PLAN_STEP_TOKENS:
                        raise PlanBudgetExceeded('Subtool argument budget exceeded at step '+str(index))
        self.offset = len(text)


def generation_diagnostics(text):
    """Describe an unsuccessful JSON stream without returning generated content."""
    report = dict(characters=len(text), trailing_whitespace_characters=len(text)-len(text.rstrip()),
                  json_value_complete=False, json_document_complete=False)
    start = len(text)-len(text.lstrip())
    try:
        _, end = json.JSONDecoder().raw_decode(text, start)
        report.update(json_value_complete=True, json_document_complete=not text[end:].strip(),
                      json_value_end=end, unconsumed_characters=len(text)-end)
    except json.JSONDecodeError as error:
        report.update(json_error_position=error.pos, json_error_message=error.msg)
    except (ValueError, RecursionError) as error:
        report['json_error_type'] = type(error).__name__
    return report


def measure_plan_arguments(arguments, encode):
    """Count compact JSON argument tokens, before any cached-content expansion.

    These independent per-call counts are NOT sampled output token attribution:
    structural JSON, whitespace and BPE boundaries differ from the whole stream.
    """
    if set(arguments) == {'first', 'rest'}:
        values = [arguments['first'], *[step['arguments'] for step in arguments['rest']]]
    elif set(arguments) == {'steps'}:
        values = [step['arguments'] for step in arguments['steps']]
    elif set(arguments) == {'content'}:
        values = [arguments]
    else:
        raise ValueError('Unsupported budgeted plan shape')
    if not 1 <= len(values) <= PLAN_MAX_STEPS:
        raise PlanBudgetExceeded('Plan must contain one to eight argument objects')
    counts = [len(encode(json.dumps(value, ensure_ascii=False, separators=(',', ':')))) for value in values]
    return dict(version=1, per_tool_limit=PLAN_STEP_TOKENS, max_steps=PLAN_MAX_STEPS,
                total_generation_limit=PLAN_TOTAL_TOKENS, argument_tokens=counts,
                exceeded_steps=[i for i, count in enumerate(counts) if count > PLAN_STEP_TOKENS],
                counting='tokenized_compact_argument_json_before_reuse_expansion')


def classification_timing(metrics):
    """Snapshot before streaming continuation can mutate the engine timestamps."""
    names = ('queued_ts', 'scheduled_ts', 'first_token_ts')
    stamps = {name: getattr(metrics, name, None) for name in names}
    stamps = {name: value if isinstance(value, (int, float)) and math.isfinite(value) and value > 0
              else None for name, value in stamps.items()}
    def interval(start, end):
        a, b = stamps[start], stamps[end]
        return b - a if a is not None and b is not None and b >= a else None
    return {'engine_monotonic_timestamps': stamps,
            'initial_queue_seconds': interval('queued_ts', 'scheduled_ts'),
            'scheduled_to_first_output_seconds': interval('scheduled_ts', 'first_token_ts')}


def audit(event, **data):
    payload = json.dumps({'event': event, 'pid': os.getpid(), 'time': time.time(), **data})+'\n'
    fd = os.open('/tmp/openjev-direct-events.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, payload.encode())
    finally:
        os.close(fd)


def classify(runner, logits, spec_decode_metadata):
    """Called before the normal sampler; None preserves the original path."""
    import torch
    from vllm.v1.outputs import SamplerOutput
    decisions = {}
    for index, req_id in enumerate(runner.input_batch.req_ids):
        params = runner.requests[req_id].sampling_params
        if params and (params.extra_args or {}).get('openjev_direct_classify'):
            decisions[index] = params.logprob_token_ids
    if not decisions:
        return None
    if spec_decode_metadata is not None:
        raise RuntimeError('OpenJev experiment does not support speculative decoding')
    metadata = runner.input_batch.sampling_metadata
    runner.input_batch.update_async_output_token_ids()
    raw = logits.float()
    all_direct = len(decisions) == raw.shape[0]
    if all_direct:
        selected = torch.empty(raw.shape[0], dtype=torch.int64, device=raw.device)
    else:
        # Preserve concurrent normal requests exactly, including their processors.
        normal = runner.sampler(logits=logits.clone(), sampling_metadata=metadata)
        selected = normal.sampled_token_ids[:, 0].long()
    for index, ids in decisions.items():
        candidates = torch.tensor(ids, dtype=torch.int64, device=raw.device)
        selected[index] = candidates[raw[index, candidates].argmax()]
        audit('classify', request_id=runner.input_batch.req_ids[index],
              sampler_bypassed=all_direct, candidate_ids=ids,
              computed_tokens=runner.requests[runner.input_batch.req_ids[index]].num_computed_tokens)
    if all_direct:
        scores = runner.sampler.gather_specific_token_logprobs(
            raw.log_softmax(-1), metadata.logprob_token_ids, selected)
        return SamplerOutput(sampled_token_ids=selected.to(torch.int32).unsqueeze(-1),
                             logprobs_tensors=scores)
    normal.sampled_token_ids = selected.to(torch.int32).unsqueeze(-1)
    return normal


def resumed(scheduler, session, update):
    """Update fields upstream streaming continuation currently leaves behind."""
    session.max_tokens = update.max_tokens
    session.structured_output_request = update.structured_output_request
    if session.structured_output_request is not None:
        from vllm.v1.request import RequestStatus
        session.status = RequestStatus.WAITING_FOR_STRUCTURED_OUTPUT_GRAMMAR
    audit('resume', request_id=session.request_id,
          computed_tokens=session.num_computed_tokens, prompt_tokens=session.num_prompt_tokens,
          max_tokens=session.max_tokens, structured=session.structured_output_request is not None,
          block_ids=scheduler.kv_cache_manager.get_blocks(session.request_id).get_block_ids())


def paused(scheduler, request):
    if not (request.sampling_params.extra_args or {}).get('openjev_direct_classify'):
        return
    # Retire worker metadata, NOT the scheduler request or its KV blocks. V2
    # otherwise retains a slot while a resumed request waits for its grammar.
    scheduler.finished_req_ids.add(request.request_id)
    audit('retire_worker_slot', request_id=request.request_id,
          computed_tokens=request.num_computed_tokens,
          block_ids=scheduler.kv_cache_manager.get_blocks(request.request_id).get_block_ids())


def classify_v2(sampler, logits, expanded_idx_mapping, idx_mapping, idx_mapping_np,
                pos, input_ids, expanded_local_pos, return_logprobs=False):
    """V2: remove classification rows from sampling, including in mixed batches."""
    import torch
    table = getattr(sampler, '_openjev_candidates', {})
    direct = [(i, table[int(slot)]) for i, slot in enumerate(idx_mapping_np) if int(slot) in table]
    if not direct:
        return None
    if logits.shape[0] != len(idx_mapping_np):
        raise RuntimeError('OpenJev classification requires one logit row per request')
    selected = torch.empty(logits.shape[0], dtype=torch.int64, device=logits.device)
    processed = logits.clone()
    direct_rows = {i for i, _ in direct}
    normal = [i for i in range(len(idx_mapping_np)) if i not in direct_rows]
    if normal:
        rows = torch.tensor(normal, device=logits.device)
        sampled, ordinary_logits = sampler.sample(logits[rows], expanded_idx_mapping[rows],
            idx_mapping[rows], idx_mapping_np[normal], pos[rows], input_ids[rows],
            expanded_local_pos[rows], return_logprobs=return_logprobs)
        selected[rows] = sampled
        processed = processed.to(dtype=ordinary_logits.dtype)
        processed[rows] = ordinary_logits
    for row, ids in direct:
        candidates = torch.tensor(ids, dtype=torch.int64, device=logits.device)
        selected[row] = candidates[logits[row, candidates].argmax()]
        slot = int(idx_mapping_np[row])
        req_id = next(k for k, v in sampler.req_states.req_id_to_index.items() if v == slot)
        audit('classify', request_id=req_id, sampler_bypassed=True, runner='v2',
              candidate_ids=ids, normal_rows_sampled=len(normal))
    return selected, processed


def attach_router(app):
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field

    class ToolRequest(BaseModel):
        prompt_ids: list[int]
        candidate_ids: list[int]
        continuations: list[list[int]]
        tools: list[dict]
        max_tokens: int = Field(default=192, ge=1, le=PLAN_TOTAL_TOKENS)
        plan_budget: bool = False
        cache_salt: str | None = Field(default=None, min_length=1, max_length=128)

    router = APIRouter()

    @router.get('/v1/openjev/capabilities')
    async def capabilities():
        return dict(plan_budget_version=1, per_tool_limit=PLAN_STEP_TOKENS, max_steps=PLAN_MAX_STEPS,
                    max_plan_tokens=PLAN_TOTAL_TOKENS, legacy_max_tokens=2048, prefix_cache_version=1)

    @router.post('/v1/openjev/toolcall')
    async def toolcall(body: ToolRequest, request: Request):
        from vllm.engine.protocol import StreamingInput
        from vllm.inputs import tokens_input
        from vllm.sampling_params import SamplingParams, StructuredOutputsParams, RequestOutputKind
        engine = request.app.state.engine_client
        if not body.plan_budget and body.max_tokens > 2048:
            return JSONResponse({'error': 'Large output requires plan_budget=true'}, status_code=400)
        if body.plan_budget and any(tool.get('name') != 'plan' for tool in body.tools):
            return JSONResponse({'error': 'Per-tool budget requires plan branches'}, status_code=400)
        n = len(body.candidate_ids)
        if not body.prompt_ids or not 1 <= n <= 16 or len(body.tools) != n or len(body.continuations) != n:
            return JSONResponse({'error': 'Inconsistent candidate table'}, status_code=400)
        if len(set(body.candidate_ids)) != n or any(not c for c in body.continuations):
            return JSONResponse({'error': 'Invalid candidates or empty continuation'}, status_code=400)
        vocab = engine.model_config.get_vocab_size()
        if any(t < 0 or t >= vocab for seq in [body.prompt_ids, body.candidate_ids, *body.continuations] for t in seq):
            return JSONResponse({'error': 'Token outside vocabulary'}, status_code=400)
        request_id = 'openjev-'+uuid.uuid4().hex
        cache_salt = 'tair-session-v1:' + body.cache_salt if body.cache_salt else request_id
        classify_params = SamplingParams(temperature=0, max_tokens=1,
            logprob_token_ids=body.candidate_ids, logprobs=n,
            output_kind=RequestOutputKind.DELTA, extra_args={'openjev_direct_classify': True})
        bypass = n == 1 and os.environ.get('TAIR_SINGLE_BRANCH_DIRECT') == '1'
        initial_params = (SamplingParams(temperature=0, max_tokens=body.max_tokens,
            structured_outputs=StructuredOutputsParams(json=body.tools[0]['parameters']),
            output_kind=RequestOutputKind.DELTA) if bypass else classify_params)
        queue = asyncio.Queue()

        async def inputs():
            if bypass:
                yield StreamingInput(prompt=tokens_input(body.prompt_ids + body.continuations[0],
                    cache_salt=cache_salt), sampling_params=initial_params)
                return
            yield StreamingInput(prompt=tokens_input(body.prompt_ids, cache_salt=cache_salt), sampling_params=classify_params)
            continuation = await queue.get()
            yield continuation

        begin = time.perf_counter()
        decision = (dict(index=0, name=body.tools[0]['name'], control_id=None, logprobs=None,
                         classification_seconds=0, timing={}, selection_mode='single_branch') if bypass else None)
        text = ''
        argument_ids = []
        finish = None
        budget = None
        streaming_budget = None
        if body.plan_budget and os.environ.get('TAIR_STREAM_PLAN_BUDGET') == '1':
            tokenizer = engine.get_tokenizer()
            streaming_budget = StreamingPlanBudget(lambda value: tokenizer.encode(value, add_special_tokens=False))
        try:
            if bypass:
                audit('decision', request_id=request_id, selected_index=0, control_id=None,
                      candidate_count=1, continuation_tokens=len(body.continuations[0]),
                      max_tokens=body.max_tokens, selection_mode='single_branch')
            async with asyncio.timeout(180):
                async for result in engine.generate(inputs(), initial_params, request_id):
                    if bypass and 'cached_prefix_tokens' not in decision:
                        decision['cached_prefix_tokens'] = getattr(result, 'num_cached_tokens', None)
                    for output in result.outputs:
                        if decision is None and output.token_ids:
                            control = output.token_ids[0]
                            selected = body.candidate_ids.index(control)
                            tool = body.tools[selected]
                            scores = output.logprobs[0]
                            decision = {'index': selected, 'name': tool['name'], 'control_id': control,
                                'cached_prefix_tokens': getattr(result, 'num_cached_tokens', None),
                                'logprobs': [scores[t].logprob for t in body.candidate_ids],
                                'timing': classification_timing(getattr(result, 'metrics', None)),
                                'classification_seconds': time.perf_counter()-begin}
                            params = SamplingParams(temperature=0, max_tokens=body.max_tokens,
                                structured_outputs=StructuredOutputsParams(json=tool['parameters']),
                                output_kind=RequestOutputKind.DELTA)
                            audit('decision', request_id=request_id, selected_index=selected,
                                  control_id=control, candidate_count=n,
                                  continuation_tokens=len(body.continuations[selected]),
                                  max_tokens=body.max_tokens)
                            await queue.put(StreamingInput(prompt=tokens_input(body.continuations[selected]),
                                                           sampling_params=params))
                        elif decision is not None:
                            text += output.text
                            argument_ids.extend(output.token_ids)
                            if output.finish_reason:
                                finish = output.finish_reason
                            if streaming_budget is not None:
                                streaming_budget.feed(text)
            if decision is None or finish != 'stop':
                raise ValueError(f'Incomplete tool call: {finish}')
            arguments = json.loads(text)
            from jsonschema import validate
            validate(arguments, body.tools[decision['index']]['parameters'])
            if body.plan_budget:
                tokenizer = engine.get_tokenizer()
                budget = measure_plan_arguments(arguments, lambda value: tokenizer.encode(value, add_special_tokens=False))
                if budget['exceeded_steps']:
                    raise PlanBudgetExceeded('Subtool argument budget exceeded at steps '+str(budget['exceeded_steps']))
            return {'request_id': request_id, 'call': {'name': decision['name'], 'arguments': arguments},
                    'decision': decision, 'raw': text, 'argument_token_ids': argument_ids,
                    'generated_argument_tokens': len(argument_ids), 'classification_control_records': int(not bypass),
                    'same_engine_session': True, 'seconds': time.perf_counter()-begin,
                    'finish_reason': finish, 'plan_budget': budget,
                    'prefix_cache_mode': 'session' if body.cache_salt else 'request'}
        except Exception as error:
            await engine.abort(request_id)
            diagnostics = generation_diagnostics(text)
            audit('generation_failed', request_id=request_id,
                  selected_index=decision['index'] if decision else None,
                  finish_reason=finish, generated_argument_tokens=len(argument_ids),
                  error_type=type(error).__name__, generation_diagnostics=diagnostics)
            return JSONResponse({'request_id': request_id, 'error': str(error), 'decision': decision,
                                 'generated_argument_tokens': len(argument_ids),
                                 'classification_control_records': int(decision is not None and not bypass),
                                 'generation_diagnostics': diagnostics,
                                 'stream_argument_tokens': streaming_budget.counts if streaming_budget else None,
                                 'plan_budget': budget, 'finish_reason': finish, 'usage_complete': finish == 'stop'},
                                status_code=422 if isinstance(error, PlanBudgetExceeded) else 500)

    app.include_router(router)
