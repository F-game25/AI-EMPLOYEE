'use strict';
/**
 * /api/services — per-service control + compute routing visibility (P9).
 *
 * Status probes (node/python/ollama/neo4j) run in parallel and complete <3s.
 * Routing data comes from the Python worker op `lanes.status`
 * (runtime/core/model_lanes.py + runtime/engine/compute/resource_manager.py).
 * Python restart mirrors start.sh exactly: pid file in $AI_HOME/run, same env,
 * same log file — and refuses (501) when a safe respawn cannot be derived.
 */

const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');
const { getWorker } = require('../py_worker_client');
const ollamaAdmin = require('../services/ollama_admin');

const w = () => getWorker(); // resolved lazily so the module loads before the worker is ready

const PY_PORT   = Number(process.env.PYTHON_BACKEND_PORT || 18790);
const AI_HOME   = process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee');
const RUN_DIR   = process.env.RUN_DIR || path.join(AI_HOME, 'run');
const LOG_DIR   = process.env.LOG_DIR || path.join(AI_HOME, 'logs');
const PY_PID_FILE = path.join(RUN_DIR, 'python-backend.pid');
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PY_SERVER = path.join(REPO_ROOT, 'runtime', 'agents', 'problem-solver-ui', 'server.py');
const NEO4J_HTTP = process.env.NEO4J_HTTP_URL || 'http://127.0.0.1:7474';

// ── probes ───────────────────────────────────────────────────────────────────

async function _fetchOk(url, timeoutMs) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    return res.ok || res.status < 500; // any HTTP answer means the port is alive
  } finally {
    clearTimeout(t);
  }
}

async function probePython() {
  const t0 = Date.now();
  try {
    const up = await _fetchOk(`http://127.0.0.1:${PY_PORT}/health`, 2000);
    return { up, port: PY_PORT, latency_ms: Date.now() - t0 };
  } catch {
    return { up: false, port: PY_PORT, latency_ms: null };
  }
}

async function probeOllama() {
  // Reuse the EXISTING ollama_admin helpers — never reimplement.
  try {
    const running = await ollamaAdmin.isOllamaRunning(2000);
    return { up: running, host: ollamaAdmin.ollamaHost(), detail: running ? 'ready' : 'stopped' };
  } catch (e) {
    return { up: false, host: ollamaAdmin.ollamaHost(), detail: String(e.message || e) };
  }
}

async function probeNeo4j() {
  try {
    const up = await _fetchOk(NEO4J_HTTP, 1500);
    return up ? { up: true, note: NEO4J_HTTP } : { up: null, note: 'not configured' };
  } catch {
    return { up: null, note: 'not configured' };
  }
}

// ── python restart helpers (mirrors start.sh §[2.5/3]) ──────────────────────

function _readPyPid() {
  try {
    const pid = parseInt(fs.readFileSync(PY_PID_FILE, 'utf8').trim(), 10);
    return Number.isInteger(pid) && pid > 1 ? pid : null;
  } catch { return null; }
}

function _pidAlive(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

// /proc/<pid>/cmdline — verify the pid is OUR python backend (guards against
// pid reuse) and recover the exact interpreter that start.sh chose.
function _pidCmdline(pid) {
  try { return fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').split('\0').filter(Boolean); } catch { return null; }
}

function _derivePythonBin(liveCmdline) {
  if (liveCmdline && liveCmdline[0] && fs.existsSync(liveCmdline[0])) return liveCmdline[0];
  if (process.env.PYTHON_BIN && fs.existsSync(process.env.PYTHON_BIN)) return process.env.PYTHON_BIN;
  const venvBin = path.join(AI_HOME, 'python-core', 'bin', 'python3'); // bootstrap.js venv (start.sh preference)
  if (fs.existsSync(venvBin)) return venvBin;
  return null;
}

const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function restartPython() {
  if (!fs.existsSync(PY_SERVER)) {
    return { code: 501, body: { ok: false, error: 'python restart not wired on this install (server.py missing)' } };
  }

  const pid = _readPyPid();
  const cmdline = pid ? _pidCmdline(pid) : null;
  const managed = !!(cmdline && cmdline.join(' ').includes('problem-solver-ui/server.py'));

  // A backend answers on the port but we have no pid we own → refuse a blind kill.
  if (!managed && pid === null) {
    const live = await probePython();
    if (live.up) {
      return { code: 501, body: { ok: false, error: 'python backend is running but not managed via the pid file — restart it via start.sh' } };
    }
  }

  const pythonBin = _derivePythonBin(managed ? cmdline : null);
  if (!pythonBin) {
    return { code: 501, body: { ok: false, error: 'python restart not wired on this install (no python interpreter derivable)' } };
  }

  // Stop the old process — ONLY when /proc confirms it is our server.py.
  if (pid && _pidAlive(pid) && managed) {
    try { process.kill(pid, 'SIGTERM'); } catch { /* already gone */ }
    for (let i = 0; i < 6 && _pidAlive(pid); i++) await _sleep(500);
    if (_pidAlive(pid)) { try { process.kill(pid, 'SIGKILL'); } catch { /* */ } }
  }

  // Respawn exactly like start.sh: same env contract, detached, append-log.
  fs.mkdirSync(RUN_DIR, { recursive: true });
  fs.mkdirSync(LOG_DIR, { recursive: true });
  const logFd = fs.openSync(path.join(LOG_DIR, 'python-backend.log'), 'a');
  const child = spawn(pythonBin, [PY_SERVER], {
    detached: true,
    stdio: ['ignore', logFd, logFd],
    env: {
      ...process.env, // Node was launched by start.sh, so this carries ~/.ai-employee/.env
      PROBLEM_SOLVER_UI_PORT: String(PY_PORT),
      PROBLEM_SOLVER_UI_HOST: '127.0.0.1',
      AI_EMPLOYEE_REPO_DIR: REPO_ROOT,
    },
  });
  child.unref();
  fs.closeSync(logFd);
  fs.writeFileSync(PY_PID_FILE, `${child.pid}\n`);

  // Wait up to 12s for /health — report honestly either way.
  for (let i = 0; i < 24; i++) {
    await _sleep(500);
    const live = await probePython().catch(() => ({ up: false }));
    if (live.up) return { code: 200, body: { ok: true, pid: child.pid, healthy: true, latency_ms: live.latency_ms } };
  }
  return {
    code: 502,
    body: { ok: false, pid: child.pid, healthy: false, error: `python backend respawned (pid ${child.pid}) but /health did not answer within 12s — check ${path.join(LOG_DIR, 'python-backend.log')}` },
  };
}

// ── router ───────────────────────────────────────────────────────────────────

module.exports = function createServicesRouter(requireAuth) {
  const r = express.Router();

  // GET /api/services/status — parallel probes, total <3s
  r.get('/status', requireAuth, async (_req, res) => {
    const [py, ol, neo] = (await Promise.allSettled([probePython(), probeOllama(), probeNeo4j()]))
      .map((p) => (p.status === 'fulfilled' ? p.value : { up: false, error: String(p.reason?.message || p.reason) }));
    res.json({
      ok: true,
      services: {
        node:   { up: true, port: Number(process.env.PORT || 8787), uptime_s: Math.floor(process.uptime()) },
        python: py,
        ollama: ol,
        neo4j:  neo,
      },
    });
  });

  // GET /api/services/routing — tier→model map + paid upgrades + compute budget
  r.get('/routing', requireAuth, async (_req, res) => {
    try {
      const result = await w().call('lanes.status', {}, 15_000);
      res.json(result);
    } catch (err) {
      res.status(503).json({ ok: false, error: 'AI backend offline', detail: String(err.message || err) });
    }
  });

  // POST /api/services/python/restart — safe kill+respawn via pid file, else 501
  r.post('/python/restart', requireAuth, async (_req, res) => {
    try {
      const { code, body } = await restartPython();
      res.status(code).json(body);
    } catch (err) {
      res.status(500).json({ ok: false, error: String(err.message || err) });
    }
  });

  return r;
};
