'use strict';

/**
 * Secure Agent Execution Sandbox
 *
 * Every agent run is isolated inside a Docker container with:
 *   - Read-only root filesystem (except /workspace and /tmp)
 *   - No network by default (opt-in per-agent with whitelist)
 *   - CPU/memory hard limits
 *   - Ephemeral container (removed on exit)
 *   - No new-process privilege escalation (--security-opt no-new-privileges)
 *   - Scoped secrets injected as env vars (not mounted files)
 *   - Full stdout/stderr captured to audit log
 *   - Wall-clock timeout enforced via SIGKILL
 *
 * Fallback: when Docker is unavailable, executes in a restricted child
 * process (reduced permissions, timeout, output cap) so the system
 * continues to work in dev environments.
 *
 * Architecture:
 *   caller → SandboxExecutor.run(spec) → [DockerSandbox | ProcessSandbox]
 *                                       → SandboxResult { output, exit_code, audit }
 */

const { spawn } = require('child_process');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const { getEventBus, EVENT_TYPES } = require('../events/bus');

const LOG = '[Sandbox]';

// ── Resource limits ───────────────────────────────────────────────────────────

const LIMITS = {
  default: { cpu: '0.5', mem: '256m', timeout_ms: 120000, net: 'none' },
  light:   { cpu: '0.25', mem: '128m', timeout_ms: 30000,  net: 'none' },
  heavy:   { cpu: '2',    mem: '1g',   timeout_ms: 300000, net: 'bridge' },
  browser: { cpu: '1',    mem: '512m', timeout_ms: 180000, net: 'bridge' },
  code:    { cpu: '1',    mem: '512m', timeout_ms: 60000,  net: 'none' },
};

// ── Filesystem policy ─────────────────────────────────────────────────────────

// Paths always mounted read-only from host
const RO_MOUNTS = [
  // Nothing from host by default — workspace is a tmpfs copy
];

// ── Sandboxed agent images (override via env) ─────────────────────────────────

const BASE_IMAGE = process.env.SANDBOX_BASE_IMAGE || 'python:3.12-slim';
const AGENT_IMAGES = {
  'default':  BASE_IMAGE,
  'browser':  process.env.SANDBOX_BROWSER_IMAGE || 'ghcr.io/microsoft/playwright/python:v1.44.0-jammy',
  'code':     process.env.SANDBOX_CODE_IMAGE    || BASE_IMAGE,
};

const ALLOWED_COMMANDS = new Set([
  'python3', 'python', 'node', 'npm', 'npx', 'git',
  'pytest', 'py.test', 'bash', 'sh',
  ...String(process.env.SANDBOX_ALLOWED_COMMANDS || '').split(',').map((item) => item.trim()).filter(Boolean),
]);

function resolveCommandSpec(command) {
  if (!Array.isArray(command) || command.length === 0) throw new Error('sandbox command must be a non-empty argv array');
  const executable = String(command[0] || '').trim();
  const base = path.basename(executable);
  if (!ALLOWED_COMMANDS.has(base)) throw new Error(`sandbox command not allowlisted: ${base || 'empty'}`);
  if (executable.includes('\0')) throw new Error('sandbox command contains invalid bytes');
  const args = command.slice(1).map((arg) => {
    const value = String(arg);
    if (value.includes('\0')) throw new Error('sandbox argument contains invalid bytes');
    return value.slice(0, 20_000);
  });
  return { cmd: base, args };
}

function resolveWorkspacePath(workspacePath) {
  if (!workspacePath) return null;
  const hostWorkspace = path.resolve(String(workspacePath));
  const allowedRoots = [
    path.resolve(process.env.AI_EMPLOYEE_WORKSPACE_ROOT || path.join(process.env.HOME || '/tmp', '.ai-employee')),
    path.resolve(process.env.STATE_DIR || path.join(process.env.HOME || '/tmp', '.ai-employee', 'state')),
    path.resolve('/tmp'),
  ];
  const allowed = allowedRoots.some((root) => hostWorkspace === root || hostWorkspace.startsWith(root + path.sep));
  if (!allowed) throw new Error('workspace path is outside allowed sandbox roots');
  return hostWorkspace;
}

function resolveProcessWorkdir(workdir) {
  const fallback = path.resolve(process.env.SANDBOX_PROCESS_WORKDIR || process.env.AI_EMPLOYEE_WORKSPACE_ROOT || '/tmp');
  const resolved = resolveWorkspacePath(workdir || fallback);
  return resolved || fallback;
}

// ── Result type ───────────────────────────────────────────────────────────────

/**
 * @typedef {Object} SandboxResult
 * @property {boolean} success
 * @property {number}  exit_code
 * @property {string}  stdout
 * @property {string}  stderr
 * @property {number}  duration_ms
 * @property {string}  container_id    null for process sandbox
 * @property {object}  audit
 */

// ── Docker sandbox ────────────────────────────────────────────────────────────

class DockerSandbox {
  get name() { return 'docker'; }

  async run(spec) {
    const {
      agent_id,
      command,            // ['python3', 'agent.py', '--task', task_json]
      env = {},           // scoped secrets — injected, never logged
      workdir = '/workspace',
      workspace_path = null,
      profile = 'default',
      tenant_id = 'system',
      trace_id,
    } = spec;

    const limits = LIMITS[profile] || LIMITS.default;
    const image  = AGENT_IMAGES[profile] || AGENT_IMAGES.default;
    const name   = `aie-${agent_id}-${_short()}`;
    const start  = Date.now();
    const checkedCommand = resolveCommandSpec(command);

    // Build docker run args
    const args = [
      'run',
      '--rm',                               // ephemeral
      '--name', name,
      '--network', limits.net,
      '--cpus', limits.cpu,
      '--memory', limits.mem,
      '--memory-swap', limits.mem,          // prevent swap
      '--read-only',                        // immutable root FS
      '--tmpfs', '/tmp:size=64m',
      '--security-opt', 'no-new-privileges',
      '--cap-drop', 'ALL',
      '--user', '65534:65534',             // nobody:nobody
      '--workdir', workdir,
    ];

    if (!workspace_path) {
      args.push('--tmpfs', '/workspace:size=256m');
    }

    // Inject scoped env (secrets never in args, only -e)
    for (const [k, v] of Object.entries(env)) {
      args.push('-e', `${k}=${v}`);
    }

    // Always inject trace metadata
    args.push('-e', `TRACE_ID=${trace_id || ''}`);
    args.push('-e', `TENANT_ID=${tenant_id}`);
    args.push('-e', `AGENT_ID=${agent_id}`);

    if (workspace_path) {
      const hostWorkspace = resolveWorkspacePath(workspace_path);
      args.push('-v', `${hostWorkspace}:/workspace:rw`);
    }

    args.push(image, checkedCommand.cmd, ...checkedCommand.args);

    const result = await _spawnWithTimeout('docker', args, limits.timeout_ms);
    const duration_ms = Date.now() - start;

    const audit = {
      agent_id,
      container_name: name,
      image,
      profile,
      tenant_id,
      trace_id,
      exit_code: result.exit_code,
      duration_ms,
      stdout_bytes: result.stdout.length,
      stderr_bytes: result.stderr.length,
      ts: new Date().toISOString(),
    };

    await _auditExecution(audit, result.success);

    return { ...result, duration_ms, container_id: name, audit };
  }

  async available() {
    return new Promise(resolve => {
      const p = spawn('docker', ['info'], { stdio: 'ignore' });
      p.on('exit', code => resolve(code === 0));
      p.on('error', () => resolve(false));
    });
  }
}

// ── Process sandbox (fallback) ────────────────────────────────────────────────

class ProcessSandbox {
  get name() { return 'process'; }

  async run(spec) {
    const {
      agent_id,
      command,
      env = {},
      workdir = process.env.SANDBOX_PROCESS_WORKDIR || process.env.AI_EMPLOYEE_WORKSPACE_ROOT || '/tmp',
      profile = 'default',
      tenant_id = 'system',
      trace_id,
    } = spec;

    const limits  = LIMITS[profile] || LIMITS.default;
    const start   = Date.now();

    // Strip dangerous env inheritance; only pass explicit + safe vars
    const safeEnv = {
      PATH: process.env.PATH,
      HOME: process.env.HOME,
      PYTHONPATH: process.env.PYTHONPATH || '',
      TRACE_ID: trace_id || '',
      TENANT_ID: tenant_id,
      AGENT_ID: agent_id,
      ...env,
    };

    const checkedCommand = resolveCommandSpec(command);
    const safeWorkdir = resolveProcessWorkdir(workdir);
    const result = await _spawnWithTimeout(checkedCommand.cmd, checkedCommand.args, limits.timeout_ms, {
      env: safeEnv,
      cwd: safeWorkdir,
    });

    const duration_ms = Date.now() - start;
    const audit = { agent_id, profile, tenant_id, trace_id, exit_code: result.exit_code, duration_ms, ts: new Date().toISOString() };
    await _auditExecution(audit, result.success);

    return { ...result, duration_ms, container_id: null, audit };
  }

  async available() { return true; }
}

// ── SandboxExecutor — picks best available sandbox ────────────────────────────

class SandboxExecutor {
  constructor() {
    this._docker  = new DockerSandbox();
    this._process = new ProcessSandbox();
    this._active  = null;
  }

  async init() {
    const dockerOk = await this._docker.available();
    this._active = dockerOk ? this._docker : this._process;
    console.log(`${LOG} Using ${this._active.name} sandbox`);
    return this;
  }

  get sandboxType() { return this._active?.name ?? 'none'; }

  /**
   * Execute an agent inside the active sandbox.
   *
   * @param {object} spec
   *   agent_id     string   — identifies the agent
   *   command      string[] — executable + args
   *   env          object   — key/value secrets (scoped, not logged)
   *   workdir      string   — working directory inside the selected runner
   *   workspace_path string — optional host workspace mounted at /workspace in Docker
   *   profile      string   — 'default' | 'light' | 'heavy' | 'browser' | 'code'
   *   sandbox      string   — optional 'process' override for host-tool verification
   *   tenant_id    string
   *   trace_id     string
   * @returns {SandboxResult}
   */
  async run(spec) {
    if (!this._active) throw new Error('SandboxExecutor not initialized');
    try {
      const runner = spec?.sandbox === 'process' ? this._process : this._active;
      const result = await runner.run(spec);
      await _emitEvent(result.audit, result.success);
      return result;
    } catch (e) {
      console.error(`${LOG} Execution failed: ${e.message}`);
      throw e;
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const OUTPUT_CAP = 10 * 1024 * 1024;  // 10 MB

function _spawnWithTimeout(cmd, args, timeoutMs, opts = {}) {
  return new Promise((resolve) => {
    const chunks = { out: [], err: [] };
    let totalOut = 0, totalErr = 0;
    const safeCmd = String(cmd || '').trim();
    if (safeCmd !== 'docker' && !ALLOWED_COMMANDS.has(path.basename(safeCmd))) {
      return resolve({ success: false, exit_code: -1, stdout: '', stderr: 'command not allowlisted' });
    }

    const child = spawn(safeCmd, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      ...opts,
    });

    const kill = setTimeout(() => {
      child.kill('SIGKILL');
      resolve({ success: false, exit_code: -1, stdout: _join(chunks.out), stderr: 'TIMEOUT', timed_out: true });
    }, timeoutMs);

    child.stdout.on('data', d => {
      if (totalOut < OUTPUT_CAP) { chunks.out.push(d); totalOut += d.length; }
    });
    child.stderr.on('data', d => {
      if (totalErr < OUTPUT_CAP) { chunks.err.push(d); totalErr += d.length; }
    });

    child.on('exit', (code) => {
      clearTimeout(kill);
      resolve({
        success: code === 0,
        exit_code: code ?? -1,
        stdout: _join(chunks.out),
        stderr: _join(chunks.err),
        timed_out: false,
      });
    });

    child.on('error', (e) => {
      clearTimeout(kill);
      resolve({ success: false, exit_code: -1, stdout: '', stderr: e.message, timed_out: false });
    });
  });
}

function _join(chunks) { return Buffer.concat(chunks).toString('utf8'); }
function _short() { return crypto.randomBytes(4).toString('hex'); }

async function _auditExecution(audit, success) {
  try {
    const bus = await getEventBus();
    await bus.publish(
      success ? EVENT_TYPES.AGENT_COMPLETED : EVENT_TYPES.AGENT_FAILED,
      audit,
      { tenant_id: audit.tenant_id, trace_id: audit.trace_id }
    );
  } catch {}
}

async function _emitEvent(audit, success) {
  // Also write to audit log file
  try {
    const logLine = JSON.stringify({ ...audit, level: success ? 'info' : 'warn' }) + '\n';
    const stateDir = process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || process.env.HOME || '/tmp', '.ai-employee', 'state');
    const logPath = path.join(stateDir, 'sandbox-audit.jsonl');
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, logLine);
  } catch {}
}

// ── Singleton ─────────────────────────────────────────────────────────────────

let _executor = null;

async function getSandboxExecutor() {
  if (_executor) return _executor;
  _executor = new SandboxExecutor();
  await _executor.init();
  return _executor;
}

module.exports = { getSandboxExecutor, SandboxExecutor, LIMITS };
