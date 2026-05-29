// Centralized API client — all fetch calls go through here.
// Base URL is inferred from window.location so it works with both Vite dev proxy and production.

const BASE = import.meta.env.VITE_API_BASE ?? '';

function getToken() {
  return localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || null
}

function storeToken(token) {
  if (!token) return
  localStorage.setItem('ai_jwt', token)
  sessionStorage.setItem('ai_jwt', token)
}

let _refreshing = false
let _refreshPromise = null

async function refreshToken() {
  if (_refreshing) return _refreshPromise
  _refreshing = true
  _refreshPromise = (async () => {
    try {
      const res = await fetch(`${BASE}/api/auth/auto-token`, { method: 'GET' })
      if (res.ok) {
        const data = await res.json()
        const token = data.token || data.access_token
        if (token) { storeToken(token); return token }
      }
    } catch { /* network error — fall through */ }
    return null
  })().finally(() => { _refreshing = false; _refreshPromise = null })
  return _refreshPromise
}

async function _fetch(method, path, body, opts = {}) {
  const doRequest = (token) => {
    const headers = { 'Content-Type': 'application/json', ...opts.headers }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return fetch(`${BASE}${path}`, {
      method,
      headers,
      signal: opts.signal,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  }

  let res = await doRequest(getToken())

  if (res.status === 401 && !opts._retry) {
    const newToken = await refreshToken()
    if (newToken) {
      res = await doRequest(newToken)
    }
    if (res.status === 401) {
      localStorage.removeItem('ai_jwt')
      sessionStorage.removeItem('ai_jwt')
      window.dispatchEvent(new CustomEvent('nx:auth-expired'))
      const err = new Error('Session expired — please log in again')
      err.status = 401
      throw err
    }
  }

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
  patch:  (path, body, opts) => _fetch('PATCH',  path, body,      opts),
  delete: (path, opts)       => _fetch('DELETE', path, undefined, opts),

  // ── Orders ───────────────────────────────────────────────────────────────
  orders: {
    list:   ()        => api.get('/api/orders'),
    get:    (id)      => api.get(`/api/orders/${id}`),
    create: (body)    => api.post('/api/orders', body),
    delete: (id)      => api.delete(`/api/orders/${id}`),
    status: (id, s)   => api.post(`/api/orders/${id}/status`, { status: s }),
    demo:   (id)      => api.post(`/api/orders/${id}/demo`, {}),
    approve:(id)      => api.post(`/api/orders/${id}/approve`, {}),
    pitch:  (id)      => api.post(`/api/orders/${id}/pitch`, {}),
  },

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
    getProject: (id)         => api.get(`/api/forge/projects/${id}`),
    submit:    (goal, opts)  => api.post('/api/forge/submit', { goal, ...opts }),
    approve:   (id, by)      => api.post(`/api/forge/approve/${id}`, { approved_by: by }),
    reject:    (id, reason)  => api.post(`/api/forge/reject/${id}`, { reason }),
    rollback:  (snapshot_id) => api.post('/api/forge/rollback', { snapshot_id }),
    queue:     ()            => api.get('/api/forge/queue'),
    snapshots: ()            => api.get('/api/forge/snapshots'),
    status:    ()            => api.get('/api/forge/status'),

    // ── Phase 5 — Backlog ────────────────────────────────────────────
    getBacklog:          (pid)       => api.get(`/api/forge/projects/${pid}/backlog`),
    createBacklogItem:   (pid, body) => api.post(`/api/forge/projects/${pid}/backlog`, body),
    updateBacklogItem:   (id, body)  => api.patch(`/api/forge/backlog/${id}`, body),
    deleteBacklogItem:   (id)        => api.delete(`/api/forge/backlog/${id}`),
    runBacklogItem:      (id, body)  => api.post(`/api/forge/backlog/${id}/run`, body),

    // ── Phase 5 — Autopilot ──────────────────────────────────────────
    startAutopilot:      (pid, body) => api.post(`/api/forge/projects/${pid}/autopilot/start`, body || {}),
    stopAutopilot:       (pid)       => api.post(`/api/forge/projects/${pid}/autopilot/stop`, {}),
    autopilotStatus:     (pid)       => api.get(`/api/forge/projects/${pid}/autopilot/status`),

    // ── Phase 5 — Decomposer ─────────────────────────────────────────
    decomposeTask:       (pid, body) => api.post(`/api/forge/projects/${pid}/decompose`, body),

    // ── Phase 5 — Skills ─────────────────────────────────────────────
    getSkills:           ()          => api.get('/api/forge/skills'),
    getSkill:            (id)        => api.get(`/api/forge/skills/${id}`),
    reloadSkills:        ()          => api.post('/api/forge/skills/reload', {}),
    applySkill:          (rid, body) => api.post(`/api/forge/runs/${rid}/apply-skill`, body),

    // ── Phase 5 — Model Router ───────────────────────────────────────
    getModels:           ()          => api.get('/api/forge/models'),
    createModel:         (body)      => api.post('/api/forge/models', body),
    updateModel:         (id, body)  => api.patch(`/api/forge/models/${id}`, body),
    testModelRouter:     (body)      => api.post('/api/forge/model-router/test', body),
    modelRoutingStats:   (pid)       => api.get(`/api/forge/projects/${pid}/model-routing-stats`),

    // ── Phase 5 — Roadmap ────────────────────────────────────────────
    getRoadmap:          (pid)       => api.get(`/api/forge/projects/${pid}/roadmap`),
    generateRoadmap:     (pid)       => api.post(`/api/forge/projects/${pid}/roadmap/generate`, {}),
    updateRoadmap:       (pid, body) => api.patch(`/api/forge/projects/${pid}/roadmap`, body),

    // ── Phase 5 — Suggestions ────────────────────────────────────────
    getSuggestions:      (pid)       => api.get(`/api/forge/projects/${pid}/suggestions`),
    acceptSuggestion:    (id)        => api.post(`/api/forge/suggestions/${id}/accept`, {}),
    rejectSuggestion:    (id)        => api.post(`/api/forge/suggestions/${id}/reject`, {}),
    suggestionToBacklog: (id)        => api.post(`/api/forge/suggestions/${id}/create-backlog-item`, {}),

    // ── Phase 5 — Cycles ─────────────────────────────────────────────
    getCycles:           (pid)       => api.get(`/api/forge/projects/${pid}/cycles`),
    createCycle:         (pid, body) => api.post(`/api/forge/projects/${pid}/cycles`, body),
    getCycle:            (id)        => api.get(`/api/forge/cycles/${id}`),
    pauseCycle:          (id)        => api.post(`/api/forge/cycles/${id}/pause`, {}),
    resumeCycle:         (id)        => api.post(`/api/forge/cycles/${id}/resume`, {}),
    cancelCycle:         (id)        => api.post(`/api/forge/cycles/${id}/cancel`, {}),

    // ── Phase 5 — Memory ─────────────────────────────────────────────
    getMemory:           (pid, cat)  => api.get(`/api/forge/projects/${pid}/memory${cat ? `?category=${cat}` : ''}`),

    // ── Phase 5 — Metrics / Replay / Patches / Approvals ────────────
    getForgeMetrics:     (pid)       => api.get(`/api/forge/projects/${pid}/forge-metrics`),
    getRunReplay:        (rid)       => api.get(`/api/forge/runs/${rid}/replay`),
    getRunPatches:       (rid)       => api.get(`/api/forge/runs/${rid}/patches`),
    getPendingApprovals: (rid)       => api.get(`/api/forge/runs/${rid}/pending-approvals`),
    approveRunAction:    (rid, body) => api.post(`/api/forge/runs/${rid}/approve-action`, body),
    rejectRunAction:     (rid, body) => api.post(`/api/forge/runs/${rid}/reject-action`, body),
    continueRun:         (rid)       => api.post(`/api/forge/runs/${rid}/continue`, {}),
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
    tools:   ()        => api.get('/api/blacklight/tools'),
    search:  (query)   => api.post('/api/blacklight/tools/search', { query }),
    runTool: (payload) => api.post('/api/blacklight/tools/run', payload),
  },

  // ── Recon ────────────────────────────────────────────────────────────────
  recon: {
    tools:    ()        => api.get('/api/recon/tools'),
    search:   (query)  => api.post('/api/recon/tools/search', { query }),
    runTool:  (payload) => api.post('/api/recon/tools/run', payload),
    cases:    ()        => api.get('/api/recon/cases'),
    createCase: (payload) => api.post('/api/recon/cases', payload),
    findings: (caseId)  => api.get(`/api/recon/findings${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ''}`),
    createFinding: (payload) => api.post('/api/recon/findings', payload),
    updateFinding: (id, payload) => api.patch(`/api/recon/findings/${encodeURIComponent(id)}`, payload),
    audit:    ()        => api.get('/api/recon/audit'),
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
    config:     ()              => api.get('/api/voice/config'),
    saveConfig: (payload)       => api.post('/api/voice/config', payload),
    fishStatus: ()              => api.get('/api/voice/fish-speech/status'),
  },

  // ── Product / Ops ─────────────────────────────────────────────────────────
  product: {
    dashboard: ()      => api.get('/api/product/dashboard'),
  },
};

export default api;
