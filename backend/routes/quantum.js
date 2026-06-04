'use strict';
/**
 * /api/quantum — Quantum-Inspired Cognitive Engine (QCE) API
 *
 * Provides amplitude-routing, strategy superposition, feedback recording,
 * and calibration stats. Feedback is written directly to state/quantum_feedback.jsonl
 * (no Python required). Proxy endpoints fan out to Python QCE when online.
 */
const path    = require('path');
const fs      = require('fs');
const http    = require('http');
const express = require('express');

// Lazy broadcast helper — avoids circular require; server.js exports broadcastQCEEvent after init.
function _broadcastQCE(type, data) {
  try {
    // Use the broadcaster module directly to avoid circular-require with server.js
    const broadcaster = require('../events/broadcaster');
    broadcaster.broadcast(type, { ...data, ts: Date.now() });
  } catch {}
}

const PYTHON_HOST = '127.0.0.1';
const PYTHON_PORT = process.env.PYTHON_BACKEND_PORT || 18790;
const TIMEOUT_MS  = 5000;
const STATE_DIR   = process.env.STATE_DIR || path.join(__dirname, '../../state');
const FEEDBACK_FILE = path.join(STATE_DIR, 'quantum_feedback.jsonl');

// Ensure state dir exists at module load time.
try { fs.mkdirSync(STATE_DIR, { recursive: true }); } catch (_) {}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

function _httpPost(pyPath, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request(
      {
        hostname: PYTHON_HOST, port: PYTHON_PORT, path: pyPath,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
        timeout: TIMEOUT_MS,
      },
      (res) => {
        let data = '';
        res.on('data', (c) => { data += c; });
        res.on('end', () => {
          try { resolve(JSON.parse(data || '{}')); }
          catch { reject(new Error('invalid JSON from Python')); }
        });
      }
    );
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    req.write(payload);
    req.end();
  });
}

async function proxyPost(pyPath, body, res, fallback) {
  try {
    return res.json(await _httpPost(pyPath, body));
  } catch (_err) {
    return res.json(fallback());
  }
}

// ── JSONL helpers ─────────────────────────────────────────────────────────────

function readFeedbackRecords(n = 50) {
  try {
    const lines = fs.readFileSync(FEEDBACK_FILE, 'utf8').trim().split('\n').filter(Boolean);
    return lines.slice(-n).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  } catch {
    return [];
  }
}

function appendFeedbackRecord(record) {
  fs.appendFileSync(FEEDBACK_FILE, JSON.stringify(record) + '\n', 'utf8');
}

// ── Router ────────────────────────────────────────────────────────────────────

const router = express.Router();

// POST /api/quantum/search — alias for /api/search/context-pack
router.post('/search', async (req, res) => {
  const { query = '', task_type = '', tenant_id = '', max_results = 50 } = req.body || {};
  await proxyPost('/api/search/context-pack',
    { query, task_type, tenant_id, max_results }, res,
    () => ({ candidates: [], confidence: 0, reasoning: '', fallback: true }));
});

// POST /api/quantum/plan — strategy superposition
router.post('/plan', async (req, res) => {
  const { query = '', task_type = '', tenant_id = '' } = req.body || {};
  await proxyPost('/api/search/plan',
    { query, task_type, tenant_id }, res,
    () => ({ strategies: [], fallback: true }));
});

// POST /api/quantum/route — amplitude route to agents/tools/model
router.post('/route', async (req, res) => {
  const { query = '', preferred_agent_id = '', tenant_id = '' } = req.body || {};
  await proxyPost('/api/search/agent-route',
    { query, preferred_agent_id, tenant_id }, res,
    () => ({ agent_id: null, confidence: 0, gate: 'direct', fallback: true }));
});

// POST /api/quantum/feedback — record outcome for a search_id
// Body: { search_id, task_id, outcome: 'success'|'partial'|'failure', agent_id?, tool_id?, confidence? }
// Written directly to state/quantum_feedback.jsonl — no Python required.
// Also forwarded to Python when online (fire-and-forget).
router.post('/feedback', async (req, res) => {
  const {
    search_id = '', task_id = '',
    outcome = 'success',
    agent_id = null, tool_id = null,
    confidence = null,
  } = req.body || {};

  const record = {
    search_id, task_id, outcome, agent_id, tool_id,
    ...(confidence !== null ? { confidence } : {}),
    recorded_at: new Date().toISOString(),
  };

  try {
    appendFeedbackRecord(record);
  } catch (err) {
    return res.status(500).json({ ok: false, error: `Failed to write feedback: ${err.message}` });
  }

  // Broadcast QCE feedback event to all connected WebSocket clients
  _broadcastQCE('qce:feedback_recorded', { task_id, outcome, search_id });

  // Forward to Python — best-effort, don't await for client response.
  _httpPost('/api/quantum/feedback', record).catch(() => {});

  return res.json({ ok: true, record });
});

// GET /api/quantum/history — last N searches with outcomes
// Query param: ?n=50
router.get('/history', (req, res) => {
  const n = Math.min(parseInt(req.query.n, 10) || 50, 500);
  const records = readFeedbackRecords(n);
  return res.json({ records, count: records.length });
});

// GET /api/quantum/stats — calibration stats aggregated from quantum_feedback.jsonl
router.get('/stats', (req, res) => {
  const records = readFeedbackRecords(10000);
  const total = records.length;
  const success_count = records.filter((r) => r.outcome === 'success').length;
  const failure_count = records.filter((r) => r.outcome === 'failure').length;
  const confidences = records.filter((r) => typeof r.confidence === 'number').map((r) => r.confidence);
  const avg_confidence = confidences.length
    ? confidences.reduce((a, b) => a + b, 0) / confidences.length
    : 0;

  const gate_distribution = records.reduce((acc, r) => {
    const g = r.gate || 'direct';
    acc[g] = (acc[g] || 0) + 1;
    return acc;
  }, { direct: 0, sandbox: 0, hitl: 0, reject: 0 });

  return res.json({ total, success_count, failure_count, avg_confidence, gate_distribution });
});

module.exports = router;
