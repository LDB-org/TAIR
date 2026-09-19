import { createEditToolDefinition } from '/tmp/tair-pi-0.85.1/node_modules/@earendil-works/pi-coding-agent/dist/core/tools/edit.js';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';
const cwd = await mkdtemp(join(tmpdir(), 'tair-edit-check-'));
try {
  const tool = createEditToolDefinition(cwd);
  const values = ['plain text', '"port": 8080', 'first\nsecond', String.raw`path\name`, 'tab\tvalue', '中文'];
  const rows = [];
  for (const [i, value] of values.entries()) {
    await writeFile(join(cwd, 'app.py'), value);
    await tool.execute(String(i), {path: 'app.py', edits: [{oldText: value, newText: 'replaced'}]});
    assert.equal(await readFile(join(cwd, 'app.py'), 'utf8'), 'replaced');
    rows.push({value, replaced: true});
  }
  await assert.rejects(tool.execute('empty', {path: 'app.py', edits: [{oldText: '', newText: 'bad'}]}), /empty/i);
  assert.equal(await readFile(join(cwd, 'app.py'), 'utf8'), 'replaced');
  console.log(JSON.stringify({pi_version: '0.85.1', parameters: tool.parameters, rows, empty_span_rejected: true, file_unchanged_on_rejection: true}, null, 2));
} finally { await rm(cwd, {recursive: true}); }
