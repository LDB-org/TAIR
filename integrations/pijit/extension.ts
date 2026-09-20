import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';
import { Type } from 'typebox';
import { executePlan } from './plan_executor.mjs';
import { appendPlanEvent, formatPlanStatus } from './plan_metrics.mjs';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { createReadTool, createEditTool, createWriteTool, createBashTool, createGrepTool, createFindTool, createLsTool } from '@earendil-works/pi-coding-agent';

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
  const toolPlan = process.env.PIJIT_TOOL_PLAN === '1';
  const planOnly = toolPlan || process.env.PIJIT_PLAN_ONLY === '1';
  const innerFactories = [createReadTool, createEditTool, createWriteTool, createBashTool, createGrepTool, createFindTool, createLsTool];
  const innerTools = innerFactories.map(create => create(process.cwd()));
  const innerCatalog = innerTools.map(({ name, description, parameters }: any) => ({ name, description, parameters }));
  const pendingPlans = new Map<string, any>();
  const batched = !planOnly && process.env.PIJIT_BATCH_TOOLS === '1';
  if (planOnly) {
    pi.on('before_agent_start', async () => { pi.setActiveTools(['plan']); });
    pi.on('tool_call', async (event: any) => {
      if (event.toolName !== 'plan') return { block: true, reason: 'Plan-only mode: ordinary tools are disabled.' };
    });
  }
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
  let budgetWarningShown = false;
  let ui: any;
  let totals = { generated: 0, controls: 0, hits: 0, schema: 0, edits: 0, plans: 0, planHits: 0, executed: 0, failed: 0, reusedSuccessful: 0, admitted: 0 };
  function record(result: any, edit = false) {
    totals.generated += result.generated_argument_tokens ?? 0;
    totals.controls += result.classification_control_records ?? 0;
    if (edit) totals.edits++;
    if (result.adaptive_plan || result.generic_plan && result.call?.name === 'plan') { totals.plans++; if (result.cache_hit) totals.planHits++; }
    else if (result.cache_hit) totals.hits++;
    if (result.schema_hit) totals.schema++;
    if (result.plan_execution_success) totals.executed++;
    if (result.plan_execution_failed) totals.failed++;
    if (result.reuse_executed) totals.reusedSuccessful++;
    totals.admitted += result.admission_count ?? 0;
    ui?.setStatus('pijit', toolPlan ? formatPlanStatus(totals) : `pijit · gen ${totals.generated} · cls ${totals.controls} · JIT ${totals.hits}/${totals.edits} · schema ${totals.schema} · plan ${totals.planHits}/${totals.plans}`);
  }
  pi.on('session_start', async (_event: any, ctx: any) => {
    if (planOnly) pi.setActiveTools(['plan']);
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
      input: ['text'], contextWindow: 240000, maxTokens: toolPlan ? 17408 : 2048,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model: any, context: any, options: any) {
      const stream = createAssistantMessageEventStream();
      const message: any = { role: 'assistant', content: [], api: model.api, provider: model.provider,
        model: model.id, timestamp: Date.now(), stopReason: 'pending', usage: usage({}) };
      (async () => {
        stream.push({ type: 'start', partial: message });
        try {
          const result = await bridge({ action: 'chat', context, cwd, session_id: sessionId, ...(toolPlan ? { inner_tools: innerCatalog } : {}) }, options?.signal);
          record(result);
          if (toolPlan && result.plan_budget_supported === false && !budgetWarningShown) {
            budgetWarningShown = true;
            ui?.notify('当前服务仍是旧版：整个 plan 上限 2048；每个子调用 2048 的预算尚未在服务端启用。', 'warning');
          }
          message.usage = usage(result);
          const call = result.call;
          if (toolPlan && call.name === 'plan') pendingPlans.set(result.request_id, result);
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
  if (toolPlan) pi.registerTool({
    name: 'plan', label: 'plan · Pi tools', executionMode: 'sequential',
    description: 'Execute an ordered plan of native Pi tools. Any task or language. '
      + 'Include only operations whose arguments are known now; wait for read/search results before dependent edits. '
      + 'Stops at first failure; results feed the next plan. This is the only public tool.',
    parameters: Type.Object({ steps: Type.Array(Type.Union(innerTools.map((tool: any) =>
      Type.Object({ name: Type.Literal(tool.name), arguments: tool.parameters }))), { minItems: 1, maxItems: 8 }) }),
    async execute(id: string, args: any, signal: AbortSignal, onUpdate: any, ctx: any) {
      const pending = pendingPlans.get(id);
      pendingPlans.delete(id);
      const tools = new Map(innerFactories.map(create => { const tool = create(ctx.cwd); return [tool.name, tool] as const; }));
      const log = (event: any) => {
        try { appendPlanEvent(process.env.PIJIT_STATE_DIR!, ctx.cwd, ctx.sessionManager.getSessionId(), id, event); }
        catch (error: any) { ctx.ui.notify('TAIR execution log write failed: ' + error.message, 'warning'); }
      };
      let results: any[];
      try { results = await executePlan(id, args.steps, tools, signal, onUpdate, log); }
      catch (error) { record({ plan_execution_failed: true }); throw error; }
      let learned: any = { admitted: [], validation: 'tool execution only; not semantic verification' };
      if (pending?.plan_task) {
        try {
          learned = await bridge({ action: 'tool_plan_complete', cwd: ctx.cwd, steps: args.steps,
            task: pending.plan_task, reused_content_ids: pending.reused_content_ids,
            session_id: ctx.sessionManager.getSessionId(), parent_tool_call_id: id }, signal);
        } catch (error: any) {
          learned = { admitted: [], cache_error: error.message, validation: 'tools succeeded; codebook update failed' };
        }
      }
      record({ plan_execution_success: true, reuse_executed: Boolean(pending?.cache_hit), admission_count: learned.admitted.length });
      log({ event: 'learning', admitted_count: learned.admitted.length, reused: Boolean(pending?.cache_hit),
        cache_update_ok: !learned.cache_error && Boolean(pending?.plan_task),
        reason: learned.admission_reason || (learned.cache_error ? 'cache_update_failed' : 'missing_plan_metadata'),
        book_entries_after: learned.book_entries_after });
      return { content: [{ type: 'text', text: JSON.stringify({ results, learning: {
        admitted: learned.admitted, reused: pending?.cache_hit || false, validation: learned.validation,
        cache_error: learned.cache_error } }) }], details: { results, learning: learned } };
    },
  });
  if (!toolPlan && process.env.PIJIT_ADAPTIVE_PLAN === '1') pi.registerTool({
    name: 'plan', label: 'plan · verified reuse', executionMode: 'sequential',
    description: 'Create new Python modules through engine classification and a persistent codebook. '
      + 'Use workspace-relative destination paths and the complete behavior contract, including imports and API details. '
      + 'A configured trusted project validator checks every module before publication and learning. '
      + 'Existing files are never overwritten. Do not pass test commands. '
      + (planOnly ? 'This is the ONLY executable tool. Unsupported tasks must stop with an explanation.'
        : 'For eligible new Python modules prefer plan; use ordinary tools for unsupported tasks.'),
    parameters: Type.Object({ task: Type.String(), contracts: Type.Record(Type.String(), Type.String()) }),
    async execute(id: string, args: any, signal: AbortSignal, _onUpdate: any, ctx: any) {
      const result = await bridge({ ...args, action: 'plan', cwd: ctx.cwd,
        session_id: ctx.sessionManager.getSessionId(), parent_tool_call_id: id }, signal);
      record(result);
      return { content: [{ type: 'text', text: `Created ${result.paths.join(', ')}. `
        + `Validation: ${result.validation}. Reused: ${result.cache_hit}. Recovered: ${result.recovered}.` }],
        details: result, usage: usage(result) };
    },
  });
  if (!planOnly) pi.registerTool({
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
  if (!planOnly && process.env.PIJIT_PRESET_EDITS === '1') pi.registerTool({
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
      const planStats = await bridge({ action: 'plan_stats', cwd: ctx.cwd });
      const plans = planStats.entries;
      if (toolPlan) {
        ctx.ui.notify(formatPlanStatus(totals) + `\nContent entries: ${planStats.tool_plan_entries ?? 0}`
          + `\nModel decisions: ${directory}/metrics.jsonl\nExecution: ${directory}/plan-events.jsonl`
          + '\nreuse counts executed plans using stored content; learn counts newly admitted entries. Execution success is not semantic verification.', 'info');
        return;
      }
      ctx.ui.notify(`pijit: ${count} source-bound entries; this session ${totals.hits}/${totals.edits} edit hits.\n`
        + `Generic content entries ${planStats.tool_plan_entries ?? 0}; verified module entries ${plans}; this session ${totals.planHits}/${totals.plans} plan hits.\n`
        + `Generated tokens ${totals.generated}; classification controls ${totals.controls}.\n`
        + `State: ${directory}\nCompact edits: Python only. Reuse: typed CLI bindings or exact task/source; explicit bindings also allow AST-equivalent snapshots.\n`
        + (process.env.PIJIT_VERIFY_CMD ? 'Configured project verification enabled.' : 'Validation: schema + compile only; semantic correctness unverified.'), 'info');
    },
  });
}
