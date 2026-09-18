// Execute the actual installed Pi edit implementation, including its matching rules.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
const [piRoot, workspace] = process.argv.slice(2);
const { createEditTool } = await import(pathToFileURL(join(piRoot, 'dist/core/tools/edit.js')).href);
const args = JSON.parse(readFileSync(0, 'utf8'));
if (args.path !== 'port_scanner.py') throw new Error('Unexpected edit path');
const result = await createEditTool(workspace).execute('benchmark-edit', args, AbortSignal.timeout(5000));
console.log(JSON.stringify(result));
