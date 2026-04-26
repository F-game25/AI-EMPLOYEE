// Centralized API client — all fetch calls go through here.
// Base URL is inferred from window.location so it works with both Vite dev proxy and production.

const BASE = import.meta.env.VITE_API_BASE ?? '';

async function _fetch(method, path, body, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };

  // Attach JWT if stored
  const token = sessionStorage.getItem('ai_jwt');
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    signal: opts.signal,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try { detail = JSON.parse(text)?.error ?? text; } catch { /* ignore */ }
    const err = new Error(detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }

  const contentType = res.headers.get('content-type') || '';
  return contentType.includes('application/json') ? res.json() : res.text();
}

const api = {
  get:    (path, opts)       => _fetch('GET',    path, undefined, opts),
  post:   (path, body, opts) => _fetch('POST',   path, body,      opts),
  put:    (path, body, opts) => _fetch('PUT',    path, body,      opts),
  delete: (path, opts)       => _fetch('DELETE', path, undefined, opts),

  // ── Auth ──────────────────────────────────────────────────────────────────
  auth: {
    token: (secret)  => api.post('/api/auth/token', { secret }),
  },

  // ── Chat ─────────────────────────────────────────────────────────────────
  chat: {
    send:   (message, model) => api.post('/api/chat', { message, model }),
  },

  // ── Tasks ─────────────────────────────────────────────────────────────────
  tasks: {
    run:    (task, user_id) => api.post('/api/tasks/run', { task, user_id }),
    list:   ()              => api.get('/api/tasks'),
  },

  // ── Mode ──────────────────────────────────────────────────────────────────
  mode: {
    set:    (mode)  => api.post('/api/mode', { mode }),
    get:    ()      => api.get('/api/mode'),
  },

  // ── Agents ────────────────────────────────────────────────────────────────
  agents: {
    list:   ()              => api.get('/api/agents'),
    status: (id)            => api.get(`/api/agents/${id}`),
  },

  // ── Brain ─────────────────────────────────────────────────────────────────
  brain: {
    status:   ()             => api.get('/api/brain/status'),
    insights: ()             => api.get('/api/brain/insights'),
    learn:    (payload)      => api.post('/api/brain/learn', payload),
  },

  // ── Forge ─────────────────────────────────────────────────────────────────
  forge: {
    submit:    (goal, opts)  => api.post('/api/forge/submit', { goal, ...opts }),
    approve:   (id, by)      => api.post(`/api/forge/approve/${id}`, { approved_by: by }),
    reject:    (id, reason)  => api.post(`/api/forge/reject/${id}`, { reason }),
    rollback:  (snapshot_id) => api.post('/api/forge/rollback', { snapshot_id }),
    queue:     ()            => api.get('/api/forge/queue'),
    snapshots: ()            => api.get('/api/forge/snapshots'),
    status:    ()            => api.get('/api/forge/status'),
  },

  // ── System ────────────────────────────────────────────────────────────────
  system: {
    halt:    (reason)  => api.post('/api/system/halt', { reason }),
    restart: ()        => api.post('/api/system/restart', {}),
    status:  ()        => api.get('/api/system/status'),
    health:  ()        => api.get('/health'),
    version: ()        => api.get('/version'),
  },

  // ── Blacklight ────────────────────────────────────────────────────────────
  blacklight: {
    status:  ()        => api.get('/api/blacklight/status'),
    toggle:  ()        => api.post('/api/blacklight/toggle', {}),
    scan:    ()        => api.post('/api/blacklight/scan', {}),
    alerts:  ()        => api.get('/api/blacklight/alerts'),
  },

  // ── Fairness ──────────────────────────────────────────────────────────────
  fairness: {
    status:  ()        => api.get('/api/fairness/status'),
    check:   (payload) => api.post('/api/fairness/check', payload),
    audit:   ()        => api.get('/api/fairness/audit'),
  },

  // ── Audit ─────────────────────────────────────────────────────────────────
  audit: {
    events:  (limit)   => api.get(`/api/audit/events${limit ? `?limit=${limit}` : ''}`),
    stats:   ()        => api.get('/api/audit/stats'),
  },

  // ── Voice ─────────────────────────────────────────────────────────────────
  voice: {
    synthesize: (text, persona) => api.post('/api/voice/synthesize', { text, persona }),
    status:     ()              => api.get('/api/voice/status'),
  },

  // ── Product / Ops ─────────────────────────────────────────────────────────
  product: {
    dashboard: ()      => api.get('/api/product/dashboard'),
  },
};

export default api;
