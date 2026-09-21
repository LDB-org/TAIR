// Benchmark settings and accounting only: retain Pi's native provider and tools.
import { appendFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';

export default function(pi: any) {
  const maxTokens = Number(process.env.TAIR_NATIVE_MAX_TOKENS || '2048');
  if (!Number.isSafeInteger(maxTokens) || maxTokens < 1) throw new Error('Invalid TAIR_NATIVE_MAX_TOKENS');
  const cacheSalt = process.env.TAIR_NATIVE_CACHE_SALT || randomUUID();
  let id: string;
  let started = 0;
  const write = (record: any) => appendFileSync(process.env.TAIR_NATIVE_TRACE!, JSON.stringify(record) + '\n');
  pi.on('before_provider_request', (event: any) => {
    id = randomUUID();
    started = performance.now();
    const payload = { ...event.payload, temperature: 0, max_tokens: maxTokens,
      parallel_tool_calls: process.env.TAIR_NATIVE_PARALLEL_TOOLS === '1',
      cache_salt: process.env.TAIR_NATIVE_PREFIX_CACHE === '1' ? cacheSalt : id,
      chat_template_kwargs: { thinking: false, enable_thinking: false } };
    delete payload.max_completion_tokens;
    write({ event: 'request', id, timestamp: Date.now(), payload });
    return payload;
  });
  pi.on('after_provider_response', (event: any) => {
    write({ event: 'http_response', id, status: event.status });
  });
  pi.on('message_end', (event: any) => {
    if (event.message.role !== 'assistant') return;
    write({ event: 'response', id, seconds: (performance.now() - started) / 1000,
      stop_reason: event.message.stopReason, usage: event.message.usage, error: event.message.errorMessage });
  });
}
