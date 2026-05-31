'use strict';

/**
 * Security operations routes — extracted from server.js (pure refactor, zero behavior changes).
 *
 * Routes:
 *   Blacklight (security monitoring): /api/blacklight/*
 *   Recon (safe OSINT + defensive analysis): /api/recon/*
 *   Autonomy daemon: /api/autonomy/*
 *   Evolution: /api/evolution/*
 *   Self-improvement: /api/self-improvement/status
 *   Admin safety: /api/admin/safety-action, /api/admin/safety-audit
 *   Reliability: /api/reliability/*
 *
 * Deps injected via createSecurityOpsRouter(deps):
 *   requireAuth          — Express middleware (JWT guard)
 *   validate             — function(schema, req, res) → body | null
 *   SCHEMAS              — Zod schema map
 *   blacklightTools      — require('./security/blacklight_tools')
 *   subsystems           — require('./subsystems')
 *   recordAuditEvent     — auditService.recordAuditEvent
 *   reliabilityState     — shared mutable object from server.js
 *   addActivity          — function(notes, kind)
 *   runForgePython       — function(payload, timeoutMs?) → Promise
 *   requestPythonJSON    — function(pathname, method, payload, options) → Promise
 *   _blacklightState     — shared mutable object from server.js
 *   _loadBlPolicy        — function() → object
 *   _saveBlPolicy        — function(p)
 *   _saveBlState         — function()
 *   _cache_blacklist     — TTL-cache middleware (30 s)
 *   _rl_blacklight       — rate-limit middleware (5/min per IP)
 *   _readReconJson       — function(file, fallback)
 *   _writeReconJson      — function(file, rows)
 *   _reconTools          — function() → array
 *   _summarizeReconTools — function(tools) → object
 *   _isReconToolAllowed  — function(tool) → bool
 *   _reconTool           — function(tool) → object
 *   _appendReconAudit    — function(action, payload, req)
 *   _RECON_CASES_FILE    — absolute path string
 *   _RECON_FINDINGS_FILE — absolute path string
 *   _RECON_AUDIT_FILE    — absolute path string
 *   ADMIN_SAFETY_ACTIONS — plain object map
 *   PYTHON_BACKEND_PORT  — number/string
 *   crypto               — require('crypto')
 */
module.exports = function createSecurityOpsRouter(deps) {
  const router = require('express').Router();
  const {
    requireAuth,
    validate,
    SCHEMAS,
    blacklightTools,
    subsystems,
    recordAuditEvent,
    reliabilityState,
    addActivity,
    runForgePython,
    requestPythonJSON,
    _blacklightState,
    _loadBlPolicy,
    _saveBlPolicy,
    _saveBlState,
    _cache_blacklist,
    _rl_blacklight,
    _readReconJson,
    _writeReconJson,
    _reconTools,
    _summarizeReconTools,
    _isReconToolAllowed,
    _reconTool,
    _appendReconAudit,
    _RECON_CASES_FILE,
    _RECON_FINDINGS_FILE,
    _RECON_AUDIT_FILE,
    ADMIN_SAFETY_ACTIONS,
    PYTHON_BACKEND_PORT,
    crypto,
  } = deps;

  // ── Self-improvement ─────────────────────────────────────────────────────────

  router.get('/api/self-improvement/status', requireAuth, (req, res) => {
    res.json(subsystems.getSelfImprovementStatus());
  });

  // ── Autonomy daemon ──────────────────────────────────────────────────────────

  router.get('/api/autonomy/status', requireAuth, (req, res) => {
    res.json(subsystems.getAutonomyStatus());
  });

  router.get('/api/autonomy/mode', requireAuth, (req, res) => {
    const auto = subsystems.getAutonomyStatus();
    res.json(auto.mode || { mode: 'OFF', active: false });
  });

  router.post('/api/autonomy/mode', requireAuth, async (req, res) => {
    const _bodyAutonomy = validate(SCHEMAS.autonomyMode, req, res);
    if (!_bodyAutonomy) return;
    const nextMode = _bodyAutonomy.mode.toUpperCase();
    // Proxy to Python backend
    try {
      const data = await new Promise((resolve, reject) => {
        const payload = JSON.stringify({ mode: nextMode });
        const url = `http://127.0.0.1:${PYTHON_BACKEND_PORT}/api/autonomy/mode`;
        const httpLib = require('http');
        const r = httpLib.request(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
          timeout: 3000,
        }, (response) => {
          let body = '';
          response.on('data', (chunk) => { body += chunk; });
          response.on('end', () => {
            try { resolve(JSON.parse(body)); } catch { resolve({ mode: nextMode, active: nextMode !== 'OFF' }); }
          });
        });
        r.on('timeout', () => { r.destroy(); resolve({ mode: nextMode, active: nextMode !== 'OFF' }); });
        r.on('error', () => resolve({ mode: nextMode, active: nextMode !== 'OFF' }));
        r.write(payload);
        r.end();
      });
      addActivity(`[AUTONOMY] Mode → ${nextMode}`, 'system');
      res.json(data);
    } catch {
      res.json({ mode: nextMode, active: nextMode !== 'OFF' });
    }
  });

  router.post('/api/autonomy/emergency-stop', requireAuth, (req, res) => {
    // Proxy emergency stop to Python backend
    const httpLib = require('http');
    const url = `http://127.0.0.1:${PYTHON_BACKEND_PORT}/api/autonomy/emergency-stop`;
    const r = httpLib.request(url, { method: 'POST', timeout: 3000 }, (response) => {
      let body = '';
      response.on('data', (chunk) => { body += chunk; });
      response.on('end', () => {
        try {
          addActivity('[AUTONOMY] ⚠ EMERGENCY STOP executed', 'system');
          res.json(JSON.parse(body));
        } catch { res.json({ status: 'stopped', message: 'Emergency stop sent.' }); }
      });
    });
    r.on('timeout', () => { r.destroy(); res.json({ status: 'stopped', message: 'Emergency stop sent (timeout).' }); });
    r.on('error', () => res.json({ status: 'stopped', message: 'Emergency stop sent (backend unreachable).' }));
    r.end();
  });

  // ── Evolution ────────────────────────────────────────────────────────────────

  router.get('/api/evolution/status', requireAuth, async (req, res) => {
    try {
      const data = await requestPythonJSON('/api/evolution/status', 'GET');
      if (data._http_status && data._http_status >= 400) throw new Error(`py_${data._http_status}`);
      res.json(data);
    } catch {
      res.json({ mode: 'OFF', running: false, available: false });
    }
  });

  router.post('/api/evolution/mode', requireAuth, async (req, res) => {
    const body = validate(SCHEMAS.evolutionMode, req, res);
    if (!body) return;
    const mode = body.mode;
    try {
      const data = await requestPythonJSON('/api/evolution/mode', 'POST', { mode });
      addActivity(`[EVOLUTION] Mode → ${mode}`, 'system');
      res.json(data);
    } catch {
      res.json({ mode, status: { mode, running: false } });
    }
  });

  // ── Admin safety ─────────────────────────────────────────────────────────────

  router.post('/api/admin/safety-action', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.adminSafetyAction, req, res);
    if (!body) return;
    const actionId = String(body.action_id || '');
    const action = ADMIN_SAFETY_ACTIONS[actionId];
    if (!action) return res.status(400).json({ ok: false, error: 'unknown safety action' });

    const reason = String(body.reason || '').trim();
    const confirmation = String(body.confirmation || '').trim();
    if (confirmation !== action.confirmation) {
      return res.status(400).json({ ok: false, error: `confirmation must equal "${action.confirmation}"` });
    }
    if (reason.length < 8) {
      return res.status(400).json({ ok: false, error: 'reason must be at least 8 characters' });
    }

    const actor = req.jwtPayload?.email || req.jwtPayload?.sub || req.jwtPayload?.userId || 'admin';
    const traceId = `safety-${Date.now().toString(36)}`;
    const event = recordAuditEvent({
      actor,
      action: `admin_safety_${actionId}`,
      inputData: {
        action_id: actionId,
        endpoint: action.endpoint,
        reason,
        requested_mode: body.execution_mode || 'staged',
      },
      outputData: {
        ok: true,
        status: 'staged',
        executed: false,
        approval_required: true,
        external_effect: action.external_effect,
      },
      riskScore: 0.95,
      traceId,
      meta: { source: 'settings_safety_center', dry_run_available: true },
    });

    res.json({
      ok: true,
      status: 'staged',
      executed: false,
      approval_required: true,
      audit_id: event.id,
      trace_id: traceId,
      action: {
        id: actionId,
        label: action.label,
        endpoint: action.endpoint,
        expected_external_effect: action.external_effect,
      },
      proof: {
        type: 'audit_record',
        id: event.id,
        source: 'audit_events',
        created_at: event.ts,
      },
    });
  });

  router.post('/api/admin/safety-audit', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.adminSafetyAudit, req, res);
    if (!body) return;
    const label = String(body.label || '').trim();
    const endpoint = String(body.endpoint || 'internal').trim();
    const reason = String(body.reason || '').trim();
    const confirmation = String(body.confirmation || '').trim();
    if (!label) return res.status(400).json({ ok: false, error: 'label required' });
    if (confirmation !== label) return res.status(400).json({ ok: false, error: `confirmation must equal "${label}"` });
    if (reason.length < 8) return res.status(400).json({ ok: false, error: 'reason must be at least 8 characters' });

    const actor = req.jwtPayload?.email || req.jwtPayload?.sub || req.jwtPayload?.userId || 'admin';
    const traceId = `safety-ui-${Date.now().toString(36)}`;
    const event = recordAuditEvent({
      actor,
      action: `admin_safety_ui_${label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}`,
      inputData: { label, endpoint, reason, execution_mode: body.execution_mode || 'ui_confirmed' },
      outputData: { ok: true, status: 'confirmed', executed: body.executed === true },
      riskScore: body.risk === 'critical' ? 0.95 : body.risk === 'high' ? 0.85 : 0.55,
      traceId,
      meta: { source: 'settings_safety_modal' },
    });
    res.json({
      ok: true,
      status: 'recorded',
      audit_id: event.id,
      trace_id: traceId,
      proof: { type: 'audit_record', id: event.id, source: 'audit_events', created_at: event.ts },
    });
  });

  // ── Reliability ──────────────────────────────────────────────────────────────

  router.get('/api/reliability/status', requireAuth, (req, res) => {
    res.json({
      stability_score: reliabilityState.stabilityScore,
      forge_frozen: reliabilityState.forgeFrozen,
      freeze_reason: reliabilityState.freezeReason,
      throttled_agents: reliabilityState.throttledAgents,
      checkpoints_stored: reliabilityState.checkpoints.length,
      last_evaluated: reliabilityState.lastEvaluated,
      updated_at: new Date().toISOString(),
    });
  });

  router.post('/api/reliability/forge/freeze', requireAuth, (req, res) => {
    const _bodyFreeze = validate(SCHEMAS.reliabilityFreeze, req, res);
    if (!_bodyFreeze) return;
    const reason = String(_bodyFreeze.reason || 'manual');
    reliabilityState.forgeFrozen = true;
    reliabilityState.freezeReason = reason;
    recordAuditEvent({ actor: 'operator', action: 'forge_freeze', outputData: { reason }, riskScore: 0.7 });
    res.json({ ok: true, forge_frozen: true, reason });
  });

  router.post('/api/reliability/forge/unfreeze', requireAuth, (req, res) => {
    reliabilityState.forgeFrozen = false;
    reliabilityState.freezeReason = '';
    recordAuditEvent({ actor: 'operator', action: 'forge_unfreeze', outputData: {}, riskScore: 0.5 });
    res.json({ ok: true, forge_frozen: false });
  });

  // ── Recon (safe OSINT + defensive local analysis) ────────────────────────────

  router.get('/api/recon/tools', requireAuth, (req, res) => {
    const category = String((req.query || {}).category || '').trim();
    const mode = String((req.query || {}).mode || '').trim();
    const tools = _reconTools().filter((tool) => {
      if (category && tool.category !== category) return false;
      if (mode && tool.mode !== mode) return false;
      return true;
    });
    res.json({
      ok: true,
      state: tools.length ? 'live' : 'empty',
      tools,
      categories: {
        osint: 'OSINT / Reconnaissance',
        defensive_review: 'Defensive Security Review',
        phishing: 'Phishing Defense',
        special: 'Special Functions',
      },
      summary: _summarizeReconTools(tools),
      policy: {
        offline_first: true,
        network_osint_requires_approval: true,
        removed_capabilities: ['exploitation', 'stress_dos', 'botnet', 'credential_harvesting', 'reverse_shells', 'attack_generation'],
      },
    });
  });

  router.post('/api/recon/tools/search', requireAuth, (req, res) => {
    const _bodyReconSearch = validate(SCHEMAS.reconToolSearch, req, res);
    if (!_bodyReconSearch) return;
    const query = String(_bodyReconSearch.query || '').trim();
    const q = query.toLowerCase();
    const matches = _reconTools()
      .map((tool) => {
        const haystack = `${tool.name} ${tool.id} ${tool.description || ''} ${(tool.keywords || []).join(' ')}`.toLowerCase();
        const score = q ? q.split(/\s+/).filter(Boolean).reduce((sum, part) => sum + (haystack.includes(part) ? 1 : 0), 0) : 0;
        return { ...tool, score };
      })
      .filter((tool) => tool.score > 0)
      .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
      .slice(0, 12);
    _appendReconAudit('recon_tool_search', { query: query.slice(0, 200), matches: matches.map(t => t.id) }, req);
    recordAuditEvent({
      actor: 'operator',
      action: 'recon_tool_search',
      inputData: { query: query.slice(0, 200) },
      outputData: { matches: matches.map(tool => tool.id) },
      riskScore: 0.1,
    });
    res.json({ ok: true, matches });
  });

  router.post('/api/recon/tools/run', requireAuth, async (req, res) => {
    const body = validate(SCHEMAS.reconToolRun, req, res);
    if (!body) return;
    const toolId = String(body.tool_id || body.toolId || '').trim();
    const input = String(body.input || '').slice(0, 20000);
    const tool = blacklightTools.getTool(toolId);
    if (!_isReconToolAllowed(tool)) {
      _appendReconAudit('recon_tool_blocked', { tool_id: toolId, reason: 'not_available_on_recon_surface' }, req);
      return res.status(404).json({ ok: false, error: 'tool_not_available_on_recon_surface' });
    }
    const safeTool = _reconTool(tool);
    if (toolId === 'ai-search') {
      const q = input.toLowerCase();
      const matches = _reconTools().filter(t => `${t.name} ${t.description || ''} ${(t.keywords || []).join(' ')}`.toLowerCase().includes(q)).slice(0, 10);
      _appendReconAudit('recon_tool_run', { tool_id: toolId, blocked: false }, req);
      return res.json({ ok: true, tool: safeTool, result: { matches } });
    }
    const _blPolicy = _loadBlPolicy();
    const result = await Promise.resolve(blacklightTools.runTool(toolId, input, {
      allowNetwork: _blPolicy.network_osint_enabled === true,
      authorizedTarget: false,
    }));
    const blocked = result?.result?.blocked === true || result.ok === false;
    _appendReconAudit(blocked ? 'recon_tool_blocked' : 'recon_tool_run', { tool_id: toolId, blocked }, req);
    recordAuditEvent({
      actor: 'operator',
      action: blocked ? 'recon_tool_blocked' : 'recon_tool_run',
      inputData: { tool_id: toolId, mode: tool.mode },
      outputData: { blocked, result_keys: Object.keys(result.result || {}) },
      riskScore: blocked ? 0.35 : 0.1,
    });
    res.status(blocked ? 403 : 200).json({ ...result, tool: safeTool });
  });

  router.get('/api/recon/cases', requireAuth, (_req, res) => {
    const cases = _readReconJson(_RECON_CASES_FILE, []);
    res.json({ ok: true, state: cases.length ? 'live' : 'empty', cases });
  });

  router.post('/api/recon/cases', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.reconCase, req, res);
    if (!body) return;
    const cases = _readReconJson(_RECON_CASES_FILE, []);
    const item = {
      id: crypto.randomUUID(),
      name: String(body.name || 'Recon case').slice(0, 120),
      target: String(body.target || '').slice(0, 300),
      owner: String(body.owner || 'operator').slice(0, 120),
      authorization: String(body.authorization || '').slice(0, 2000),
      status: 'active',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    cases.unshift(item);
    _writeReconJson(_RECON_CASES_FILE, cases.slice(0, 200));
    _appendReconAudit('recon_case_created', { case_id: item.id, target: item.target }, req);
    res.status(201).json({ ok: true, case: item });
  });

  router.get('/api/recon/findings', requireAuth, (req, res) => {
    const caseId = String((req.query || {}).case_id || '').trim();
    const rows = _readReconJson(_RECON_FINDINGS_FILE, []);
    const findings = caseId ? rows.filter(row => row.case_id === caseId) : rows;
    res.json({ ok: true, state: findings.length ? 'live' : 'empty', findings });
  });

  router.post('/api/recon/findings', requireAuth, (req, res) => {
    const body = validate(SCHEMAS.reconFinding, req, res);
    if (!body) return;
    const findings = _readReconJson(_RECON_FINDINGS_FILE, []);
    const item = {
      id: crypto.randomUUID(),
      case_id: String(body.case_id || '').slice(0, 80),
      title: String(body.title || 'Recon finding').slice(0, 160),
      severity: ['info', 'low', 'medium', 'high'].includes(body.severity) ? body.severity : 'info',
      evidence: body.evidence || {},
      source_tool: String(body.source_tool || '').slice(0, 120),
      status: 'open',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    findings.unshift(item);
    _writeReconJson(_RECON_FINDINGS_FILE, findings.slice(0, 500));
    _appendReconAudit('recon_finding_created', { finding_id: item.id, case_id: item.case_id, source_tool: item.source_tool }, req);
    res.status(201).json({ ok: true, finding: item });
  });

  router.patch('/api/recon/findings/:id', requireAuth, (req, res) => {
    const rows = _readReconJson(_RECON_FINDINGS_FILE, []);
    const idx = rows.findIndex(row => row.id === req.params.id);
    if (idx === -1) return res.status(404).json({ ok: false, error: 'finding_not_found' });
    const current = rows[idx];
    rows[idx] = {
      ...current,
      status: req.body?.status ? String(req.body.status).slice(0, 40) : current.status,
      severity: ['info', 'low', 'medium', 'high'].includes(req.body?.severity) ? req.body.severity : current.severity,
      title: req.body?.title ? String(req.body.title).slice(0, 160) : current.title,
      updated_at: new Date().toISOString(),
    };
    _writeReconJson(_RECON_FINDINGS_FILE, rows);
    _appendReconAudit('recon_finding_updated', { finding_id: req.params.id }, req);
    res.json({ ok: true, finding: rows[idx] });
  });

  router.get('/api/recon/audit', requireAuth, (req, res) => {
    const limit = Math.min(200, parseInt((req.query || {}).limit) || 100);
    const rows = _readReconJson(_RECON_AUDIT_FILE, []).slice(0, limit);
    res.json({ ok: true, state: rows.length ? 'live' : 'empty', audit: rows });
  });

  // ── Blacklight (security monitoring) ─────────────────────────────────────────

  router.get('/api/blacklight/status', requireAuth, _cache_blacklist, (req, res) => {
    res.json({
      active: _blacklightState.active,
      alerts_count: _blacklightState.alerts.length,
      last_scan: _blacklightState.last_scan,
      status: _blacklightState.active ? 'active' : 'inactive',
      tools: blacklightTools.summarizeCatalog(),
    });
  });

  router.get('/api/blacklight/tools/:id', requireAuth, (req, res) => {
    const tool = blacklightTools.getTool(req.params.id);
    if (!tool) return res.status(404).json({ ok: false, error: 'unknown_tool' });
    res.json({ ok: true, tool });
  });

  router.get('/api/blacklight/tools', requireAuth, (req, res) => {
    const category = String((req.query || {}).category || '').trim();
    const mode = String((req.query || {}).mode || '').trim();
    const tools = blacklightTools.TOOL_CATALOG.filter((tool) => {
      if (category && tool.category !== category) return false;
      if (mode && tool.mode !== mode) return false;
      return true;
    });
    res.json({
      ok: true,
      tools,
      categories: blacklightTools.CATEGORIES,
      summary: blacklightTools.summarizeCatalog(),
      policy: {
        offline_first: true,
        network_osint_requires_approval: true,
        blocked_capabilities: ['ddos', 'botnet', 'credential_harvesting', 'reverse_shells', 'active_exploitation'],
      },
    });
  });

  router.get('/api/blacklight/policy', requireAuth, (req, res) => {
    res.json(_loadBlPolicy());
  });

  router.post('/api/blacklight/policy', requireAuth, (req, res) => {
    const _bodyBlPolicy = validate(SCHEMAS.blacklistPolicy, req, res);
    if (!_bodyBlPolicy) return;
    const current = _loadBlPolicy();
    const updated = { ...current, ..._bodyBlPolicy };
    const safe = { network_osint_enabled: !!updated.network_osint_enabled };
    _saveBlPolicy(safe);
    res.json({ ok: true, policy: safe });
  });

  router.post('/api/blacklight/tools/search', requireAuth, (req, res) => {
    const _bodyBlSearch = validate(SCHEMAS.reconToolSearch, req, res);
    if (!_bodyBlSearch) return;
    const query = String(_bodyBlSearch.query || '').trim();
    const matches = blacklightTools.searchTools(query, 12);
    recordAuditEvent({
      actor: 'operator',
      action: 'blacklight_tool_search',
      inputData: { query: query.slice(0, 200) },
      outputData: { matches: matches.map(tool => tool.id) },
      riskScore: 0.15,
    });
    res.json({ ok: true, matches });
  });

  router.post('/api/blacklight/tools/run', requireAuth, _rl_blacklight, async (req, res) => {
    const body = validate(SCHEMAS.reconToolRun, req, res);
    if (!body) return;
    const toolId = String(body.tool_id || body.toolId || '').trim();
    const input = String(body.input || '').slice(0, 20000);
    const tool = blacklightTools.getTool(toolId);
    if (!tool) return res.status(404).json({ ok: false, error: 'unknown_tool' });

    const _blPolicy = _loadBlPolicy();
    const result = await Promise.resolve(blacklightTools.runTool(toolId, input, {
      allowNetwork: _blPolicy.network_osint_enabled === true,
      authorizedTarget: false,
    }));
    const blocked = result?.result?.blocked === true || result.ok === false;
    const riskScore = tool.mode === 'blocked' ? 0.9 : tool.mode === 'passive_network' ? 0.6 : tool.mode === 'defensive_simulation' ? 0.35 : 0.15;
    recordAuditEvent({
      actor: 'operator',
      action: blocked ? 'blacklight_tool_blocked' : 'blacklight_tool_run',
      inputData: { tool_id: toolId, mode: tool.mode },
      outputData: { blocked, result_keys: Object.keys(result.result || {}) },
      riskScore,
    });
    if (blocked) {
      _blacklightState.alerts.unshift({
        ts: new Date().toISOString(),
        type: 'policy_gate',
        tool_id: toolId,
        message: result.result?.reason || 'Blocked by Blacklight policy',
      });
      if (_blacklightState.alerts.length > 100) _blacklightState.alerts.length = 100;
    }
    res.status(blocked ? 403 : 200).json(result);
    try { _saveBlState(); } catch {}
  });

  router.post('/api/blacklight/toggle', requireAuth, (req, res) => {
    _blacklightState.active = !_blacklightState.active;
    recordAuditEvent({ actor: 'operator', action: _blacklightState.active ? 'blacklight_activate' : 'blacklight_deactivate', outputData: {}, riskScore: 0.5 });
    addActivity(`[BLACKLIGHT] ${_blacklightState.active ? 'Activated' : 'Deactivated'}`, 'security');
    _saveBlState();
    res.json({ success: true, ok: true, active: _blacklightState.active, status: { mode: _blacklightState.active ? 'active' : 'inactive' } });
  });

  router.post('/api/blacklight/scan', requireAuth, async (req, res) => {
    const scan = await runForgePython({ operation: 'security_scan' });
    const ts = new Date().toISOString();
    _blacklightState.last_scan = ts;
    if (scan && scan.findings) {
      scan.findings.filter((f) => !f.safe).forEach((f) => {
        _blacklightState.alerts.unshift({ ts, file: f.file, errors: f.errors, type: 'security_violation' });
      });
      if (_blacklightState.alerts.length > 100) _blacklightState.alerts.length = 100;
    }
    addActivity('[BLACKLIGHT] Security scan completed', 'security');
    const findings = scan?.findings || [];
    res.json({ success: true, ok: true, results: findings, scan: scan || { findings: [], summary: 'Python bridge unavailable' } });
  });

  router.get('/api/blacklight/alerts', requireAuth, (req, res) => {
    const limit = Math.min(100, parseInt((req.query || {}).limit) || 50);
    res.json({ alerts: _blacklightState.alerts.slice(0, limit), count: _blacklightState.alerts.length });
  });

  return router;
};
