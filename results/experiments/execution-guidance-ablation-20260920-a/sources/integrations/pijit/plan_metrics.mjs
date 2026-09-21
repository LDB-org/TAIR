import { appendFileSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';

/** Metadata only: never log source, shell arguments, or tool outputs here. */
export function appendPlanEvent(state, cwd, sessionId, planId, event) {
  const key = createHash('sha256').update(resolve(cwd)).digest('hex').slice(0, 20);
  const directory = join(state, 'workspaces', key);
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  appendFileSync(join(directory, 'plan-events.jsonl'), JSON.stringify({
    version: 1, timestamp: new Date().toISOString(), session_id: sessionId,
    plan_id: planId, ...event,
  }) + '\n', { mode: 0o600 });
}

export function formatPlanStatus(totals) {
  return `pijit · gen ${totals.generated} · cls ${totals.controls} · plans ${totals.plans}`
    + ` · ok ${totals.executed} · fail ${totals.failed} · reuse ${totals.reusedSuccessful} · learn ${totals.admitted}`;
}
