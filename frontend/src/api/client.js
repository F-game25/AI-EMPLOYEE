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
    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '60', 10)
      window.dispatchEvent(new CustomEvent('nx:rate-limit', { detail: { seconds: retryAfter } }))
    }
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
    synthesize: (text, persona = {}) => api.post('/api/voice/synthesize', { text, persona, provider: persona.provider }),
    status:     ()              => api.get('/api/voice/status'),
    config:     ()              => api.get('/api/voice/config'),
    saveConfig: (payload)       => api.post('/api/voice/config', payload),
    fishStatus: ()              => api.get('/api/voice/fish-speech/status'),
    bundleStatus: () => api.get('/api/voice/bundle/status'),
    verifyBundle: (payload = {}) => api.post('/api/voice/bundle/verify', payload),
    modelSamples: () => api.get('/api/voice/model/samples'),
    benchmarkModel: (payload = {}) => api.post('/api/voice/model/benchmark', payload),
    createSession: (payload = {}) => api.post('/api/voice/sessions', payload),
    getSession:    (sessionId) => api.get(`/api/voice/sessions/${encodeURIComponent(sessionId)}`),
    sendSessionText: (sessionId, text, context = {}) => api.post(
      `/api/voice/sessions/${encodeURIComponent(sessionId)}/text`,
      { text, context },
    ),
    sendSessionAudio: async (sessionId, wavBlob, opts = {}) => {
      const token = sessionStorage.getItem('ai_jwt')
      const headers = { 'Content-Type': 'audio/wav' }
      if (token) headers.Authorization = `Bearer ${token}`
      const res = await fetch(`${BASE}/api/voice/sessions/${encodeURIComponent(sessionId)}/audio`, {
        method: 'POST',
        headers,
        signal: opts.signal,
        body: wavBlob,
      })
      const contentType = res.headers.get('content-type') || ''
      const payload = contentType.includes('application/json')
        ? await res.json().catch(() => ({}))
        : await res.text().catch(() => '')
      if (!res.ok) {
        const err = new Error(payload?.message || payload?.error || payload || `HTTP ${res.status}`)
        err.status = res.status
        err.payload = payload
        throw err
      }
      return payload
    },
    interruptSession: (sessionId) => api.post(`/api/voice/sessions/${encodeURIComponent(sessionId)}/interrupt`, {}),
    converse: (text, context = {}) => api.post('/api/voice/converse', { text, context }),
    runtime: () => api.get('/api/voice/runtime'),
    runtimeLogs: (limit = 100) => api.get(`/api/voice/runtime/logs?limit=${encodeURIComponent(limit)}`),
    runtimeDoctor: () => api.get('/api/voice/runtime/doctor'),
    runtimeSelfTest: (payload = {}) => api.post('/api/voice/runtime/self-test', payload),
    startRuntime: (payload = {}) => api.post('/api/voice/runtime/start', payload),
    stopRuntime: (payload = {}) => api.post('/api/voice/runtime/stop', payload),
    customVoiceDatasetStatus: () => api.get('/api/voice/custom-voice/dataset/status'),
    saveCustomVoiceDataset: (payload = {}) => api.post('/api/voice/custom-voice/dataset', payload),
    startCustomVoiceTraining: (payload = {}) => api.post('/api/voice/custom-voice/train', payload),
    getCustomVoiceTraining: (jobId) => api.get(`/api/voice/custom-voice/train/${encodeURIComponent(jobId)}`),
    benchmarkCustomVoice: (payload = {}) => api.post('/api/voice/custom-voice/benchmark', payload),
    activateCustomVoice: (payload = {}) => api.post('/api/voice/custom-voice/activate', payload),
    downloadRuntime: async (payload = {}, { onEvent, signal } = {}) => {
      const token = sessionStorage.getItem('ai_jwt')
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const res = await fetch(`${BASE}/api/voice/runtime/download`, {
        method: 'POST',
        headers,
        signal,
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || `HTTP ${res.status}`)
      }
      if (!res.body?.getReader) return null
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let lastEvent = null
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop()
        for (const frame of frames) {
          const dataLines = frame
            .split('\n')
            .filter(line => line.startsWith('data: '))
            .map(line => line.slice(6))
          if (!dataLines.length) continue
          const event = JSON.parse(dataLines.join('\n'))
          lastEvent = event
          onEvent?.(event)
        }
      }
      return lastEvent
    },
    cancelRuntimeDownload: (payload = {}) => api.post('/api/voice/runtime/download/cancel', payload),
    subscribeSessionEvents: async (sessionId, onEvent, opts = {}) => {
      const token = sessionStorage.getItem('ai_jwt')
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const res = await fetch(`${BASE}/api/voice/sessions/${encodeURIComponent(sessionId)}/events`, {
        method: 'GET',
        headers,
        signal: opts.signal,
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || `HTTP ${res.status}`)
      }
      if (!res.body?.getReader) return null
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop()
        for (const frame of frames) {
          const dataLines = frame
            .split('\n')
            .filter(line => line.startsWith('data: '))
            .map(line => line.slice(6))
          if (!dataLines.length) continue
          try {
            onEvent?.(JSON.parse(dataLines.join('\n')))
          } catch { /* ignore malformed server-sent event */ }
        }
      }
      return null
    },
  },

  // ── Ollama ────────────────────────────────────────────────────────────────
  ollama: {
    status: ()                  => api.get('/api/ollama/status'),
    start:  ()                  => api.post('/api/ollama/start', {}),
    recommendation: ()          => api.get('/api/ollama/recommendation'),
    pullRecommended: async ({ onEvent } = {}) => {
      const token = sessionStorage.getItem('ai_jwt')
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const res = await fetch(`${BASE}/api/ollama/pull-recommended`, {
        method: 'POST',
        headers,
        body: JSON.stringify({}),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || `HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let lastEvent = null
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const events = buf.split('\n\n')
        buf = events.pop()
        for (const event of events) {
          if (!event.startsWith('data: ')) continue
          const payload = JSON.parse(event.slice(6))
          lastEvent = payload
          if (onEvent) onEvent(payload)
        }
      }
      return lastEvent
    },
  },

  // ── Product / Ops ─────────────────────────────────────────────────────────
  product: {
    dashboard: ()      => api.get('/api/product/dashboard'),
  },
};

export default api;
