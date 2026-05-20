'use strict';

/**
 * Python → Node WS metrics bridge.
 *
 * Subscribes to the Python FastAPI SSE endpoint at /events on the Python
 * AI backend (default port 18790) and re-emits each event as a WebSocket
 * broadcast using the canonical dashboard contract:
 *
 *   metrics_tick     → metrics:tick
 *   cognition_tick   → cognition:tick
 *   economy_tick     → economy:tick
 *   operations_tick  → operations:tick
 *   tasks_pipeline   → tasks:pipeline
 *   objective_current→ objective:current
 *   agents_list      → agents:list
 *   chat_message     → chat:message
 *
 * Anything else is passed through unchanged so future event types Just Work.
 * Reconnects with exponential backoff (1s → 2s → 4s → max 30s).
 */

const http = require('http');

const PY_HOST = process.env.PYTHON_BACKEND_HOST || '127.0.0.1';
const PY_PORT = process.env.PYTHON_BACKEND_PORT || 18790;
const SSE_PATH = process.env.PYTHON_EVENTS_PATH || '/events';

// Map Python event_type → WS topic + payload shaper (default: pass through).
const TYPE_MAP = {
  metrics_tick: (p) => ({
    topic: 'metrics:tick',
    payload: {
      cpu: p.cpu ?? p.cpu_percent ?? 0,
      gpu: p.gpu ?? p.gpu_percent ?? 0,
      ram: p.ram ?? p.memory_percent ?? 0,
      gpu_temp: p.gpu_temp ?? 0,
      net_mbps: p.net_mbps ?? 0,
      latency_ms: p.latency_ms ?? p.api_latency_ms ?? 0,
      throughput_tps: p.throughput_tps ?? p.brain_decisions_per_sec ?? 0,
      error_rate: p.error_rate ?? p.errors_per_minute ?? 0,
    },
  }),
  cognition_tick: (p) => ({
    topic: 'cognition:tick',
    payload: {
      reasoning_chains: p.reasoning_chains ?? 0,
      tokens_per_sec: p.tokens_per_sec ?? 0,
      context_depth: p.context_depth ?? 0,
      memory_writes: p.memory_writes ?? 0,
    },
  }),
  economy_tick: (p) => ({
    topic: 'economy:tick',
    payload: {
      revenue_today: p.revenue_today ?? 0,
      pipelines_active: p.pipelines_active ?? 0,
      roi_pct: p.roi_pct ?? 0,
      token_cost: p.token_cost ?? 0,
    },
  }),
  operations_tick: (p) => ({
    topic: 'operations:tick',
    payload: {
      active_tasks: p.active_tasks ?? 0,
      queued_tasks: p.queued_tasks ?? 0,
      success_rate: p.success_rate ?? 0,
      avg_exec_time: p.avg_exec_time ?? 0,
    },
  }),
  tasks_pipeline: (p) => ({
    topic: 'tasks:pipeline',
    payload: {
      incoming: p.incoming ?? 0,
      planning: p.planning ?? 0,
      executing: p.executing ?? 0,
      validating: p.validating ?? 0,
      completed: p.completed ?? 0,
    },
  }),
  objective_current: (p) => ({
    topic: 'objective:current',
    payload: {
      title: p.title || '',
      priority: p.priority || '',
      deadline: p.deadline || '',
      progress: p.progress ?? 0,
    },
  }),
  agents_list: (p) => ({ topic: 'agents:list', payload: { agents: p.agents || [] } }),
  chat_message: (p) => ({ topic: 'chat:message', payload: { role: p.role || 'assistant', text: p.text || '', ts: p.ts || Date.now() } }),
};

function startPythonMetricsBridge({ broadcast, log } = {}) {
  if (typeof broadcast !== 'function') throw new Error('broadcast fn required');
  const logger = log || console;
  let backoff = 1000;
  const MAX_BACKOFF = 30000;
  let stopped = false;

  let _evtCount = 0;
  function handleEvent(evt) {
    if (!evt || typeof evt !== 'object') return;
    const type = evt.event_type || evt.type;
    const payload = evt.payload || evt.data || evt;
    const mapper = type && TYPE_MAP[type];
    _evtCount++;
    if (_evtCount <= 3 || _evtCount % 60 === 0) {
      logger.info(`[PyBridge] event #${_evtCount} type=${type} → ${mapper ? 'mapped' : 'passthrough'}`);
    }
    if (mapper) {
      const { topic, payload: shaped } = mapper(payload);
      broadcast(topic, shaped);
    } else if (type) {
      // Pass-through for unknown types — converts underscores → colons.
      broadcast(type.replace(/_/g, ':'), payload);
    }
  }

  function connect() {
    if (stopped) return;
    const url = `http://${PY_HOST}:${PY_PORT}${SSE_PATH}`;
    const req = http.get(url, { headers: { Accept: 'text/event-stream' } }, (res) => {
      if (res.statusCode !== 200) {
        logger.warn(`[PyBridge] SSE ${url} returned ${res.statusCode} — retry in ${backoff}ms`);
        res.resume();
        scheduleReconnect();
        return;
      }
      logger.info(`[PyBridge] Connected to Python SSE at ${url}`);
      backoff = 1000;
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        buf += chunk;
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, i);
          buf = buf.slice(i + 2);
          const dataLine = block.split('\n').find((l) => l.startsWith('data:'));
          if (!dataLine) continue;
          const raw = dataLine.slice(5).trim();
          if (!raw) continue;
          try { handleEvent(JSON.parse(raw)); }
          catch (e) { /* malformed payload — skip silently to avoid log spam */ }
        }
      });
      res.on('end', () => {
        logger.warn('[PyBridge] SSE stream ended — reconnecting');
        scheduleReconnect();
      });
      res.on('error', (e) => {
        logger.warn(`[PyBridge] SSE error: ${e.message}`);
        scheduleReconnect();
      });
    });
    req.on('error', (e) => {
      // Common during boot before Python is up — only log first occurrence per backoff cycle.
      if (backoff <= 2000) logger.info(`[PyBridge] Python SSE not reachable (${e.code || e.message}) — retrying`);
      scheduleReconnect();
    });
    req.setTimeout(0); // never time out on the keep-alive
  }

  function scheduleReconnect() {
    if (stopped) return;
    setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, MAX_BACKOFF);
  }

  connect();
  return () => { stopped = true; };
}

module.exports = { startPythonMetricsBridge };
