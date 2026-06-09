'use strict';
/**
 * Persistent Python worker client.
 *
 * Spawns backend/python_worker.py once and keeps it alive.
 * Each call() sends one JSON line, awaits the matching response line.
 * On crash the worker restarts automatically; in-flight promises reject once
 * so callers get an error rather than hanging forever.
 */

const { spawn } = require('child_process');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const readline = require('readline');

const REPO_ROOT   = path.resolve(__dirname, '..');
const WORKER_PATH = path.join(__dirname, 'python_worker.py');
const RUNTIME_DIR = path.join(REPO_ROOT, 'runtime');
const AI_HOME     = path.resolve(
  process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
);

const PYTHON_BIN  = process.env.PYTHON_BIN || 'python3';

// Milliseconds to wait before restarting after a crash.
const RESTART_DELAY_MS = 500;

class PythonWorkerClient {
  constructor() {
    this._proc    = null;
    this._rl      = null;
    this._pending = new Map(); // id → { resolve, reject, timer }
    this._starting = false;
    this._start();
  }

  _start() {
    if (this._starting) return;
    this._starting = true;

    const child = spawn(PYTHON_BIN, [WORKER_PATH], {
      env: { ...process.env, AI_HOME, PYTHONPATH: RUNTIME_DIR },
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const rl = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });

    rl.on('line', (line) => {
      if (!line.trim()) return;
      let msg;
      try { msg = JSON.parse(line); } catch { return; }
      const entry = this._pending.get(msg.id);
      if (!entry) return;
      clearTimeout(entry.timer);
      this._pending.delete(msg.id);
      if (msg.error !== undefined) {
        entry.reject(new Error(msg.error));
      } else {
        entry.resolve(msg.result);
      }
    });

    child.stderr.on('data', (d) => {
      // Surface Python tracebacks to Node stderr for debugging.
      process.stderr.write(`[py-worker] ${d}`);
    });

    child.on('close', (code) => {
      this._proc    = null;
      this._rl      = null;
      this._starting = false;
      // Reject all in-flight calls.
      for (const [id, entry] of this._pending) {
        clearTimeout(entry.timer);
        entry.reject(new Error(`Python worker exited (code ${code})`));
        this._pending.delete(id);
      }
      // Restart unless the process was intentionally killed (code null = SIGKILL/SIGTERM).
      if (code !== null) {
        setTimeout(() => this._start(), RESTART_DELAY_MS);
      }
    });

    child.on('error', (err) => {
      process.stderr.write(`[py-worker] spawn error: ${err.message}\n`);
    });

    this._proc     = child;
    this._rl       = rl;
    this._starting = false;
  }

  /**
   * Call an operation in the persistent Python worker.
   * @param {string} op         - Operation name (e.g. 'orders.list')
   * @param {object} args       - Arguments object
   * @param {number} timeoutMs  - Hard timeout in milliseconds (default 90 s)
   * @returns {Promise<any>}    - Resolves with the result dict from Python
   */
  call(op, args = {}, timeoutMs = 90_000) {
    return new Promise((resolve, reject) => {
      if (!this._proc) {
        // Worker not yet ready — restart was triggered, fail fast.
        return reject(new Error('Python worker not running'));
      }
      const id    = crypto.randomUUID();
      const timer = setTimeout(() => {
        if (this._pending.has(id)) {
          this._pending.delete(id);
          reject(new Error(`Python worker timeout after ${timeoutMs}ms (op=${op})`));
        }
      }, timeoutMs);

      this._pending.set(id, { resolve, reject, timer });
      const line = JSON.stringify({ id, op, args }) + '\n';
      this._proc.stdin.write(line);
    });
  }

  /** Gracefully shut down the worker (called on Node process exit). */
  shutdown() {
    if (this._proc) {
      this._proc.stdin.end();
      this._proc = null;
    }
  }
}

// Singleton — one worker process for the lifetime of the Node server.
let _instance = null;
function getWorker() {
  if (!_instance) _instance = new PythonWorkerClient();
  return _instance;
}

module.exports = { getWorker };
