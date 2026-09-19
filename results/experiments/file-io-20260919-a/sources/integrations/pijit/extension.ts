import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';
import { Type } from 'typebox';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { createReadTool, createEditTool, createWriteTool, createBashTool } from '@earendil-works/pi-coding-agent';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '../..');
const zeroCost = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 };
function usage(result: any) {
  const input = result.input_tokens ?? 0;
  const output = (result.generated_argument_tokens ?? 0) + (result.classification_control_records ?? 0);
  return { input, output, totalTokens: input + output, cacheRead: 0, cacheWrite: 0, cost: { ...zeroCost } };
}
function bridge(payload: any, signal?: AbortSignal): Promise<any> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PIJIT_PYTHON || join(root, '.venv/bin/python'), [join(here, 'bridge.py')],
      { stdio: ['pipe', 'pipe', 'pipe'], signal });
    let stdout = '', stderr = '';
    child.stdout.on('data', chunk => { stdout += chunk; });
    child.stderr.on('data', chunk => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', code => {
      try {
        const result = JSON.parse(stdout);
        if (code || result.error) reject(new Error(result.error || stderr.slice(-2000)));
        else resolve(result);
      } catch (error) { reject(new Error(`pijit bridge failed (${code}): ${stderr.slice(-2000)} ${stdout.slice(-1000)}`)); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(payload));
  });
}

export default function(pi: any) {
  const batched = process.env.PIJIT_BATCH_TOOLS === '1';
  let batchIds: string[] = [];
  const batchSucceeded = new Set<string>();
  if (batched) {
    for (const create of [createReadTool, createEditTool, createWriteTool, createBashTool]) {
      const tool = create(process.cwd());
      pi.registerTool({ ...tool, executionMode: 'sequential',
        execute: (id: string, args: any, signal: AbortSignal, onUpdate: any, ctx: any) =>
          create(ctx.cwd).execute(id, args, signal, onUpdate) });
    }
    pi.on('tool_call', (event: any) => {
      const index = batchIds.indexOf(event.toolCallId);
      if (index > 0 && !batchSucceeded.has(batchIds[index - 1]))
        return { block: true, reason: 'Plan stopped: preceding step failed or did not complete. Replan from tool results.' };
    });
    pi.on('tool_result', (event: any) => {
      if (batchIds.includes(event.toolCallId) && !event.isError) batchSucceeded.add(event.toolCallId);
    });
  }
  let cwd = process.cwd();
  let sessionId: string | undefined;
  let ui: any;
  let totals = { generated: 0, controls: 0, hits: 0, schema: 0, edits: 0 };
  function record(result: any, edit = false) {
    totals.generated += result.generated_argument_tokens ?? 0;
    totals.controls += result.classification_control_records ?? 0;
    if (edit) totals.edits++;
    if (result.cache_hit) totals.hits++;
    if (result.schema_hit) totals.schema++;
    ui?.setStatus('pijit', `pijit · gen ${totals.generated} · cls ${totals.controls} · JIT ${totals.hits}/${totals.edits} · schema ${totals.schema}`);
  }
  pi.on('session_start', async (_event: any, ctx: any) => {
    cwd = ctx.cwd; ui = ctx.ui; sessionId = ctx.sessionManager.getSessionId();
    ctx.ui.setTitle('pijit — TAIR');
    ctx.ui.setHeader((_tui: any, theme: any) => ({
      render: (width: number) => [theme.fg('accent', 'pijit / TAIR - Pi 0.85.1'.slice(0, width))],
      invalidate() {},
    }));
    record({});
  });
  pi.registerProvider('pijit', {
    baseUrl: process.env.PIJIT_URL || 'http://127.0.0.1',
    apiKey: 'ssh-local-transport',
    api: 'pijit-engine',
    models: [{ id: 'deepseek-jit', name: 'pijit / DeepSeek + TAIR', reasoning: false,
      input: ['text'], contextWindow: 240000, maxTokens: 2048,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model: any, context: any, options: any) {
      const stream = createAssistantMessageEventStream();
      const message: any = { role: 'assistant', content: [], api: model.api, provider: model.provider,
        model: model.id, timestamp: Date.now(), stopReason: 'pending', usage: usage({}) };
      (async () => {
        stream.push({ type: 'start', partial: message });
        try {
          const result = await bridge({ action: 'chat', context, cwd, session_id: sessionId }, options?.signal);
          record(result);
          message.usage = usage(result);
          const call = result.call;
          if (call.name === 'reply_user') {
            message.content = [{ type: 'text', text: call.arguments.content }];
            message.stopReason = 'stop';
            stream.push({ type: 'text_start', contentIndex: 0, partial: message });
            stream.push({ type: 'text_delta', contentIndex: 0, delta: call.arguments.content, partial: message });
            stream.push({ type: 'text_end', contentIndex: 0, content: call.arguments.content, partial: message });
          } else {
            const calls = result.calls || [call];
            batchIds = result.calls ? calls.map((_call: any, index: number) => `${result.request_id}-${index}`) : [];
            batchSucceeded.clear();
            message.content = calls.map((item: any, index: number) => ({ type: 'toolCall',
              id: result.calls ? batchIds[index] : result.request_id, name: item.name, arguments: item.arguments }));
            message.stopReason = 'toolUse';
            for (let index = 0; index < calls.length; index++) {
              stream.push({ type: 'toolcall_start', contentIndex: index, partial: message });
              stream.push({ type: 'toolcall_delta', contentIndex: index, delta: JSON.stringify(calls[index].arguments), partial: message });
              stream.push({ type: 'toolcall_end', contentIndex: index, toolCall: message.content[index], partial: message });
            }
          }
          stream.push({ type: 'done', reason: message.stopReason, message });
        } catch (error: any) {
          message.stopReason = options?.signal?.aborted ? 'aborted' : 'error';
          message.errorMessage = error.message;
          stream.push({ type: 'error', reason: message.stopReason, error: message });
        } finally { stream.end(message); }
      })();
      return stream;
    },
  });
  pi.registerTool({
    name: 'compact_edit', label: 'compact_edit · pijit',
    executionMode: batched ? 'sequential' : undefined,
    description: 'Edit an EXISTING Python file with compact source-bound operations and a persistent JIT codebook. '
      + 'Supports existing call keyword/default changes (integer, float, string, boolean), CLI help/required, option aliases, entry guards and catch/return. '
      + 'Read first. Group up to eight related supported changes to the same file in one call; for CLI properties use: Change --option property to VALUE. Quote string values. Provide the edit requirements, not old/new source, test commands or final-answer instructions. Other languages and unsupported changes use edit/write. '
      + 'Successful syntax checks do not prove behavior correctness; run project tests.',
    parameters: Type.Object({ path: Type.String(), task: Type.String() }),
    async execute(_id: string, args: any, signal: AbortSignal, onUpdate: any, ctx: any) {
      onUpdate?.({ content: [{ type: 'text', text: 'pijit: checking source-bound codebook / generating compact edit…' }], details: {} });
      const result = await bridge({ action: 'edit', cwd: ctx.cwd, ...args,
        session_id: ctx.sessionManager.getSessionId(), parent_tool_call_id: _id }, signal);
      record(result, true);
      const summary = `Applied compact edit to ${result.path}.\n`
        + `Validation: ${result.validation}\n${result.diff}`;
      return { content: [{ type: 'text', text: summary }], details: result, usage: usage(result) };
    },
  });
  if (process.env.PIJIT_PRESET_EDITS === '1') pi.registerTool({
    name: 'set_cli_default', label: 'set_cli_default · pijit',
    description: 'Set one existing integer argparse option default in a Python file. Read source first. '
      + 'Supply its option name, observed integer default and new integer value. Requires a unique option, '
      + 'explicit type=int and a simple argparse.ArgumentParser binding. Only the default literal changes; '
      + 'other edits use compact_edit.',
    parameters: Type.Object({ path: Type.String(), option: Type.String(),
      expected_default: Type.Integer(), value: Type.Integer() }),
    async execute(id: string, args: any, signal: AbortSignal, _onUpdate: any, ctx: any) {
      const result = await bridge({ action: 'preset', cwd: ctx.cwd, ...args,
        session_id: ctx.sessionManager.getSessionId(), parent_tool_call_id: id }, signal);
      record(result);
      return { content: [{ type: 'text', text: `Applied ${result.preset_id} to ${result.path}.\n`
        + `Validation: ${result.validation}\n${result.diff}` }], details: result, usage: usage(result) };
    },
  });
  pi.registerCommand('jit', {
    description: 'Show TAIR metrics and current project codebook',
    handler: async (_args: string, ctx: any) => {
      const workspace = createHash('sha256').update(ctx.cwd).digest('hex').slice(0, 20);
      const directory = join(process.env.PIJIT_STATE_DIR!, 'workspaces', workspace);
      const file = join(directory, 'codebook.json');
      const count = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')).length : 0;
      ctx.ui.notify(`pijit: ${count} source-bound entries; this session ${totals.hits}/${totals.edits} edit hits.\n`
        + `Generated tokens ${totals.generated}; classification controls ${totals.controls}.\n`
        + `State: ${directory}\nCompact edits: Python only. Reuse: typed CLI bindings or exact task/source; explicit bindings also allow AST-equivalent snapshots.\n`
        + (process.env.PIJIT_VERIFY_CMD ? 'Configured project verification enabled.' : 'Validation: schema + compile only; semantic correctness unverified.'), 'info');
    },
  });
}
