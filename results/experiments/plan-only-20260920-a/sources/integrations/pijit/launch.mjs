#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdirSync, readFileSync, realpathSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';
import { setTimeout as delay } from 'node:timers/promises';

const here = dirname(fileURLToPath(import.meta.url));
const cliArgs = process.argv.slice(2).filter(arg => arg !== '--plan-only');
const planOnly = process.argv.includes('--plan-only') || process.env.PIJIT_PLAN_ONLY === '1';
if (planOnly) {
  let validator;
  try { validator = JSON.parse(process.env.PIJIT_PLAN_VERIFY_ARGV || '[]'); } catch {}
  if (!Array.isArray(validator) || !validator.length || validator.some(arg => typeof arg !== 'string' || !arg.trim())) {
    console.error('pijit: --plan-only requires PIJIT_PLAN_VERIFY_ARGV, a trusted validator argv array. No ordinary-tool fallback.');
    process.exit(1);
  }
}

const which = spawnSync('which', ['pi'], { encoding: 'utf8' });
if (which.status) throw new Error('Pi is not installed. Install @earendil-works/pi-coding-agent@0.85.1 first.');
const cli = realpathSync(which.stdout.trim());
const piRoot = dirname(dirname(dirname(cli)));
const version = JSON.parse(readFileSync(join(piRoot, 'package.json'), 'utf8')).version;
if (version !== '0.85.1') console.error(`pijit: Pi ${version}; this integration was tested with 0.85.1.`);
const state = process.env.PIJIT_STATE_DIR || join(homedir(), '.pijit');
mkdirSync(state, { recursive: true, mode: 0o700 });
let tunnel;
let child;
let exitCode = 0;
try {
  let url = process.env.PIJIT_URL;
  if (!url && !cliArgs.some(arg => ['--help', '-h', '--version', '-v'].includes(arg))) {
    const server = createServer();
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const port = server.address().port;
    await new Promise(resolve => server.close(resolve));
    let tunnelError = '';
    tunnel = spawn('ssh', ['-N', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
      '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
      '-L', `127.0.0.1:${port}:127.0.0.1:8000`, process.env.PIJIT_SSH_HOST || 'rs-yuesheng-gpu-vps'],
      { stdio: ['ignore', 'ignore', 'pipe'], detached: true });
    tunnel.stderr.on('data', data => { tunnelError += data; });
    tunnel.on('error', error => { tunnelError += error.message; });
    url = `http://127.0.0.1:${port}`;
    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (tunnel.exitCode !== null) throw new Error(`SSH tunnel failed: ${tunnelError}`);
      try {
        const response = await fetch(url + '/health', { signal: AbortSignal.timeout(1000) });
        if (response.ok) { ready = true; break; }
      } catch {}
      await delay(200);
    }
    if (!ready) throw new Error(`DeepSeek did not become reachable: ${tunnelError}`);
  }
  const env = { ...process.env, PIJIT_STATE_DIR: state, PI_CODING_AGENT_DIR: join(state, 'agent'),
    PIJIT_URL: url || 'http://127.0.0.1:8000', PI_OFFLINE: '1',
    ...(planOnly ? { PIJIT_PLAN_ONLY: '1', PIJIT_ADAPTIVE_PLAN: '1', PIJIT_NATIVE_PLANNER: '1', PIJIT_PLAN_DISABLE_REUSE: '0' } : {}) };
  const args = [cli, '--no-extensions', '-e', join(here, 'extension.ts'), '--provider', 'pijit',
    '--model', 'deepseek-jit', '--thinking', 'off', ...(planOnly ? ['--no-tools'] : []), ...cliArgs];
  child = spawn(process.execPath, args, { stdio: 'inherit', env });
  const stop = () => { child?.kill('SIGTERM'); tunnel?.kill('SIGTERM'); };
  process.on('SIGTERM', stop);
  process.on('SIGINT', () => {}); // Pi handles terminal Ctrl+C itself.
  exitCode = await new Promise((resolve, reject) => { child.on('exit', code => resolve(code ?? 1)); child.on('error', reject); });
} catch (error) {
  console.error(`pijit: ${error.message}`);
  exitCode = 1;
} finally {
  tunnel?.kill('SIGTERM');
}
process.exitCode = exitCode;
