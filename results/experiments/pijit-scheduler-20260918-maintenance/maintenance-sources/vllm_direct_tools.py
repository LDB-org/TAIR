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
        max_tokens: int = Field(default=192, ge=1, le=2048)

    router = APIRouter()

    @router.post('/v1/openjev/toolcall')
    async def toolcall(body: ToolRequest, request: Request):
        from vllm.engine.protocol import StreamingInput
        from vllm.inputs import tokens_input
        from vllm.sampling_params import SamplingParams, StructuredOutputsParams, RequestOutputKind
        engine = request.app.state.engine_client
        n = len(body.candidate_ids)
        if not body.prompt_ids or not 1 <= n <= 16 or len(body.tools) != n or len(body.continuations) != n:
            return JSONResponse({'error': 'Inconsistent candidate table'}, status_code=400)
        if len(set(body.candidate_ids)) != n or any(not c for c in body.continuations):
            return JSONResponse({'error': 'Invalid candidates or empty continuation'}, status_code=400)
        vocab = engine.model_config.get_vocab_size()
        if any(t < 0 or t >= vocab for seq in [body.prompt_ids, body.candidate_ids, *body.continuations] for t in seq):
            return JSONResponse({'error': 'Token outside vocabulary'}, status_code=400)
        request_id = 'openjev-'+uuid.uuid4().hex
        classify_params = SamplingParams(temperature=0, max_tokens=1,
            logprob_token_ids=body.candidate_ids, logprobs=n,
            output_kind=RequestOutputKind.DELTA, extra_args={'openjev_direct_classify': True})
        queue = asyncio.Queue()

        async def inputs():
            yield StreamingInput(prompt=tokens_input(body.prompt_ids, cache_salt=request_id), sampling_params=classify_params)
            continuation = await queue.get()
            yield continuation

        begin = time.perf_counter()
        decision = None
        text = ''
        argument_ids = []
        finish = None
        try:
            async with asyncio.timeout(180):
                async for result in engine.generate(inputs(), classify_params, request_id):
                    for output in result.outputs:
                        if decision is None and output.token_ids:
                            control = output.token_ids[0]
                            selected = body.candidate_ids.index(control)
                            tool = body.tools[selected]
                            scores = output.logprobs[0]
                            decision = {'index': selected, 'name': tool['name'], 'control_id': control,
                                'logprobs': [scores[t].logprob for t in body.candidate_ids],
                                'timing': classification_timing(getattr(result, 'metrics', None)),
                                'classification_seconds': time.perf_counter()-begin}
                            params = SamplingParams(temperature=0, max_tokens=body.max_tokens,
                                structured_outputs=StructuredOutputsParams(json=tool['parameters']),
                                output_kind=RequestOutputKind.DELTA)
                            await queue.put(StreamingInput(prompt=tokens_input(body.continuations[selected]),
                                                           sampling_params=params))
                        elif decision is not None:
                            text += output.text
                            argument_ids.extend(output.token_ids)
                            if output.finish_reason:
                                finish = output.finish_reason
            if decision is None or finish != 'stop':
                raise ValueError(f'Incomplete tool call: {finish}')
            arguments = json.loads(text)
            from jsonschema import validate
            validate(arguments, body.tools[decision['index']]['parameters'])
            return {'request_id': request_id, 'call': {'name': decision['name'], 'arguments': arguments},
                    'decision': decision, 'raw': text, 'argument_token_ids': argument_ids,
                    'generated_argument_tokens': len(argument_ids), 'classification_control_records': 1,
                    'same_engine_session': True, 'seconds': time.perf_counter()-begin,
                    'finish_reason': finish}
        except Exception as error:
            await engine.abort(request_id)
            return JSONResponse({'request_id': request_id, 'error': str(error)}, status_code=500)

    app.include_router(router)
