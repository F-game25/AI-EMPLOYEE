// Centralized API client — all fetch calls go through here.
// Base URL is inferred from window.location so it works with both Vite dev proxy and production.

import { getStoredToken as getToken, clearToken, ensureOperatorToken } from './auth'

const BASE = import.meta.env.VITE_API_BASE ?? '';

// Force a fresh localhost token after a 401 (the current one expired/was rejected).
const refreshToken = () => ensureOperatorToken({ force: true })

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
      clearToken()
      window.dispatchEvent(new CustomEvent('nx:auth-expired'))
      const err = new Error('Session expired — please log in again')
      err.status = 401
      throw err
    }
  }

  if (!res.ok) {
    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '60', 10)
      window.dispatchEvent(new CustomEvent('nx:rate-limit', { detail: { seconds: retryAfter } }))
    }
    const text = await res.text().catch(() => '');
    let detail = text;
    let parsed = null;
    try { parsed = JSON.parse(text); detail = parsed?.error ?? text; } catch { /* ignore */ }
    const err = new Error(detail || `HTTP ${res.status}`);
    err.status = res.status;
    if (parsed) err.body = parsed;
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

  // ── Computer-Use mode (browser/desktop master switch) ──────────────────────
  computerUse: {
    getMode: ()        => api.get('/api/computer-use/mode'),
    setMode: (enabled) => api.post('/api/computer-use/mode', { enabled }),
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
    runtime:  (query = '')      => api.get(`/api/forge/runtime${typeof query === 'string' ? query : ''}`),
    diagnostics: ()            => api.get('/api/forge/diagnostics'),
    getReports: (pid)          => api.get(`/api/forge/reports${pid ? `?project_id=${encodeURIComponent(pid)}` : ''}`),
    getProject: (id)         => api.get(`/api/forge/projects/${id}`),
    submit:    (goal, opts)  => api.post('/api/forge/submit', typeof goal === 'object' && goal !== null ? goal : { goal, ...opts }),
    approve:   (id, by)      => api.post(`/api/forge/approve/${id}`, typeof by === 'object' && by !== null ? by : { approved_by: by }),
    reject:    (id, reason)  => api.post(`/api/forge/reject/${id}`, typeof reason === 'object' && reason !== null ? reason : { reason }),
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

    // ── Phase 5/6 — Autopilot ────────────────────────────────────────
    startAutopilot:      (pid, body) => api.post(`/api/forge/projects/${pid}/autopilot/start`, body || {}),
    stopAutopilot:       (pid)       => api.post(`/api/forge/projects/${pid}/autopilot/stop`, {}),
    resumeAutopilot:     (pid)       => api.post(`/api/forge/projects/${pid}/autopilot/resume`, {}),
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

    // ── Phase 7 — Learning / Distillation ───────────────────────────
    getLearning:         (pid)       => api.get(`/api/forge/projects/${pid}/learning`),
    getLessons:          (pid, opts) => api.get(`/api/forge/projects/${pid}/learning/lessons${opts?.category ? `?category=${opts.category}` : ''}`),
    promoteLesson:       (lid)       => api.post(`/api/forge/learning/lessons/${lid}/promote-memory`, {}),
    getPreferencePairs:  (pid)       => api.get(`/api/forge/projects/${pid}/preference-pairs`),
    updatePreferencePair:(id, body)  => api.patch(`/api/forge/preference-pairs/${id}`, body),
    getEvalCases:        (pid, opts) => api.get(`/api/forge/projects/${pid}/evaluation-cases${opts?.eval_type ? `?eval_type=${opts.eval_type}` : ''}`),
    getSkillProposals:   (pid, opts) => api.get(`/api/forge/projects/${pid}/skill-proposals${opts?.status ? `?status=${opts.status}` : ''}`),
    approveProposal:     (id)        => api.post(`/api/forge/skill-proposals/${id}/approve`, {}),
    rejectProposal:      (id)        => api.post(`/api/forge/skill-proposals/${id}/reject`, {}),
    applyProposal:       (id)        => api.post(`/api/forge/skill-proposals/${id}/apply`, {}),
    getDatasets:         (pid)       => api.get(`/api/forge/projects/${pid}/learning/datasets`),
    exportDataset:       (pid, body) => api.post(`/api/forge/projects/${pid}/learning/export`, body),
    getRunDistillation:  (rid)       => api.get(`/api/forge/runs/${rid}/distillation`),
    distillRun:          (rid)       => api.post(`/api/forge/runs/${rid}/distill`, {}),

    // ── Phase 8 — Local Model Training ──────────────────────────────
    training: {
      getOverview:        (pid)       => api.get(`/api/forge/projects/${pid}/training`),
      getSummary:         (pid)       => api.get(`/api/forge/projects/${pid}/training-summary`),
      getRuns:            (pid)       => api.get(`/api/forge/projects/${pid}/training-runs`),
      createRun:          (pid, body) => api.post(`/api/forge/projects/${pid}/training-runs`, body),
      getRun:             (trid)      => api.get(`/api/forge/training-runs/${trid}`),
      validateRun:        (trid, body)=> api.post(`/api/forge/training-runs/${trid}/validate`, body || {}),
      startRun:           (trid, body)=> api.post(`/api/forge/training-runs/${trid}/start`, body || {}),
      evaluateRun:        (trid)      => api.post(`/api/forge/training-runs/${trid}/evaluate`, {}),
      getModelVersions:   (pid, opts) => api.get(`/api/forge/projects/${pid}/model-versions${opts?.model_type ? `?model_type=${opts.model_type}` : ''}`),
      promoteVersion:     (id, body)  => api.post(`/api/forge/model-versions/${id}/promote`, body || {}),
      rejectVersion:      (id)        => api.post(`/api/forge/model-versions/${id}/reject`, {}),
      rollbackVersion:    (id)        => api.post(`/api/forge/model-versions/${id}/rollback`, {}),
      helperAdvise:       (pid, body) => api.post(`/api/forge/projects/${pid}/helper-advise`, body),
    },

    // ── Phase 9 — Interconnected Cognitive Core ─────────────────────
    cognitive: {
      getMemoryGraphSummary:      (pid)            => api.get(`/api/forge/projects/${pid}/memory-graph/summary`),
      getMemoryGraphNodes:        (pid, filters)   => api.get(`/api/forge/projects/${pid}/memory-graph/nodes${filters?.node_type || filters?.search ? `?${new URLSearchParams(Object.fromEntries(Object.entries(filters).filter(([, v]) => v))).toString()}` : ''}`),
      getMemoryGraphNode:         (pid, nodeId)    => api.get(`/api/forge/projects/${pid}/memory-graph/nodes/${nodeId}`),
      getMemoryGraphNeighborhood: (pid, nodeId, d) => api.get(`/api/forge/projects/${pid}/memory-graph/nodes/${nodeId}/neighborhood${d ? `?depth=${d}` : ''}`),
      consolidateMemoryGraph:     (pid, payload)   => api.post(`/api/forge/projects/${pid}/memory-graph/consolidate`, payload || {}),
      getProjectContextPackets:   (pid)            => api.get(`/api/forge/projects/${pid}/context-packets`),
      getRunContextPackets:       (rid)            => api.get(`/api/forge/runs/${rid}/context-packets`),
      getAdvisoryEvents:          (pid)            => api.get(`/api/forge/projects/${pid}/advisory-events`),
      getAdvisoryMetrics:         (pid)            => api.get(`/api/forge/projects/${pid}/advisory-metrics`),
      getCognitiveEvents:         (pid)            => api.get(`/api/forge/projects/${pid}/cognitive-events`),
      createCognitiveEvent:       (pid, payload)   => api.post(`/api/forge/projects/${pid}/cognitive-events`, payload),
      consultHelperAdvisory:      (pid, payload)   => api.post(`/api/forge/projects/${pid}/helper-advisory/consult`, payload),
    },

    // ── V5 — Project Runtime ────────────────────────────────────────
	    v5: {
	      startProject:       (body)       => api.post('/api/forge/v5/projects/start', body),
	      getBrief:           (pid)        => api.get(`/api/forge/v5/projects/${pid}/brief`),
	      getResearch:        (pid)        => api.get(`/api/forge/v5/projects/${pid}/research`),
	      getGoals:           (pid)        => api.get(`/api/forge/v5/projects/${pid}/goals`),
      executeGoal:        (pid, gid, body) => api.post(`/api/forge/v5/projects/${pid}/goals/${gid}/execute`, body || {}),
      getQualityGate:     (gid)        => api.get(`/api/forge/v5/goals/${gid}/quality-gate`),
      writeQualityGate:   (gid, body)  => api.post(`/api/forge/v5/goals/${gid}/quality-gate`, body || {}),
      getReport:          (pid)        => api.get(`/api/forge/v5/projects/${pid}/report`),
	      getComputeBackends: ()           => api.get('/api/forge/v5/compute/backends'),
	      getModels:          ()           => api.get('/api/forge/v5/models'),
	    },

	    github: {
	      status:             (pid)        => api.get(`/api/forge/projects/${pid}/github/status`),
	      prepare:            (pid, body)  => api.post(`/api/forge/projects/${pid}/github/prepare`, body || {}),
	      publish:            (pid, body)  => api.post(`/api/forge/projects/${pid}/github/publish`, body || {}),
	    },

	    v7: {
	      getExecutionState:   (pid)            => api.get(`/api/forge/v7/projects/${pid}/execution-state`),
	      getWorkspace:        (wid)            => api.get(`/api/forge/v7/workspaces/${wid}`),
	      proposePatch:        (pid, gid, body) => api.post(`/api/forge/v7/projects/${pid}/goals/${gid}/propose-patch`, body || {}),
	      createSandbox:       (pid, gid, body) => api.post(`/api/forge/v7/projects/${pid}/goals/${gid}/sandbox`, body || {}),
	      applyPatchSandbox:   (wid, body)      => api.post(`/api/forge/v7/workspaces/${wid}/apply-patch`, body || {}),
	      validateWorkspace:   (wid, body)      => api.post(`/api/forge/v7/workspaces/${wid}/validate`, body || {}),
	      requestApply:        (pid, gid, body) => api.post(`/api/forge/v7/projects/${pid}/goals/${gid}/request-apply`, body || {}),
	      approveApply:        (aid, body)      => api.post(`/api/forge/v7/approvals/${aid}/approve`, body || {}),
	      rejectApply:         (aid, body)      => api.post(`/api/forge/v7/approvals/${aid}/reject`, body || {}),
	      applyToWorkspace:    (pid, gid, body) => api.post(`/api/forge/v7/projects/${pid}/goals/${gid}/apply`, body || {}),
	      postValidate:        (pid, gid, body) => api.post(`/api/forge/v7/projects/${pid}/goals/${gid}/post-validate`, body || {}),
	      rollback:            (pid, gid, body) => api.post(`/api/forge/v7/projects/${pid}/goals/${gid}/rollback`, body || {}),
	    },

	    // ── Phase 5 — Metrics / Replay / Patches / Approvals ────────────
    getForgeMetrics:     (pid)       => api.get(`/api/forge/projects/${pid}/forge-metrics`),
    getRun:              (rid)       => api.get(`/api/forge/runs/${rid}`),
    pauseRun:            (rid)       => api.post(`/api/forge/runs/${rid}/pause`, {}),
    resumeRun:           (rid)       => api.post(`/api/forge/runs/${rid}/resume`, {}),
    cancelRun:           (rid)       => api.post(`/api/forge/runs/${rid}/cancel`, {}),
    verifyRun:           (rid, body) => api.post(`/api/forge/runs/${rid}/verify`, body || {}),
    applyRun:            (rid, body) => api.post(`/api/forge/runs/${rid}/apply`, body || {}),
    getRunAudit:         (rid)       => api.get(`/api/forge/runs/${rid}/audit`),
    getRunReport:        (rid)       => api.get(`/api/forge/runs/${rid}/report`),
    getRunReplay:        (rid)       => api.get(`/api/forge/runs/${rid}/replay`),
    getRunPatches:       (rid)       => api.get(`/api/forge/runs/${rid}/patches`),
    getPendingApprovals: (rid)       => api.get(`/api/forge/runs/${rid}/pending-approvals`),
    approveRunAction:    (rid, body) => api.post(`/api/forge/runs/${rid}/approve-action`, body),
    rejectRunAction:     (rid, body) => api.post(`/api/forge/runs/${rid}/reject-action`, body),
    continueRun:         (rid)       => api.post(`/api/forge/runs/${rid}/continue`, {}),

    // ── V5 flat aliases ──────────────────────────────────────────────
    v5StartProject:      (body)       => api.post('/api/forge/v5/projects/start', body),
    v5GetBrief:          (id)         => api.get(`/api/forge/v5/projects/${id}/brief`),
    v5GetResearch:       (id)         => api.get(`/api/forge/v5/projects/${id}/research`),
    v5RunResearch:       (id)         => api.post(`/api/forge/v5/projects/${id}/research`),
    v5GetGoals:          (id)         => api.get(`/api/forge/v5/projects/${id}/goals`),
    v5PlanGoals:         (id)         => api.post(`/api/forge/v5/projects/${id}/goals/plan`),
    v5ExecuteGoal:       (gid, body)  => api.post(`/api/forge/v5/goals/${gid}/execute`, body),
    v5GetQualityGate:    (gid)        => api.get(`/api/forge/v5/goals/${gid}/quality-gate`),
    v5GetReport:         (id)         => api.get(`/api/forge/v5/projects/${id}/report`),
    v5GetCompute:        ()           => api.get('/api/forge/v5/compute/backends'),
    v5GetModels:         ()           => api.get('/api/forge/v5/models'),
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

  // ── CompanyOS (P10 AI company-builder) ─────────────────────────────────────
  company: {
    list:     ()        => api.get('/api/company'),
    get:      (id)      => api.get(`/api/company/${id}`),
    start:    (body)    => api.post('/api/company', body),
    validate: (id)      => api.post(`/api/company/${id}/validate`, {}),
    build:    (id, body) => api.post(`/api/company/${id}/build`, body || {}),
    refine:   (idea)    => api.post('/api/company/refine', { idea }),
  },
};

export default api;
