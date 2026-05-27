'use strict';

const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { getAscendForgeEngine } = require('../ascendforge/engine');
const { createRouteRateLimit } = require('../middleware/route-rate-limit');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const CONFIG_FILE = path.join(REPO_ROOT, 'runtime', 'config', 'fork_integration_manifest.json');
const SOURCE_TRUST_FILE = path.join(REPO_ROOT, 'runtime', 'config', 'source_trust.json');
const STATE_DIR = path.resolve(process.env.STATE_DIR || process.env.AI_EMPLOYEE_STATE_DIR || path.join(os.homedir(), '.ai-employee', 'state'));
const WALLET_FILE = path.join(STATE_DIR, 'wallet_vault.json');
const WALLET_AUDIT_FILE = path.join(STATE_DIR, 'wallet_audit.jsonl');
const MOBILE_PAIRINGS_FILE = path.join(STATE_DIR, 'mobile_pairings.json');
const BRAND_KITS_FILE = path.join(STATE_DIR, 'brand_kits.json');

const financeRuns = new Map();
const moneyTaskState = new Map();
const heartbeatTasks = [];
const pairedChannels = new Map();
const sessions = new Map();

const BUSINESS_TEMPLATES = [
  {
    id: 'brand-strategy',
    name: 'Brand Strategy',
    category: 'brand',
    description: 'Positioning, ICP, category narrative, differentiation, and brand voice for a running project.',
    outputs: ['positioning', 'icp', 'brand_voice', 'differentiators'],
    risk: 'safe',
  },
  {
    id: 'offer-architecture',
    name: 'Offer Architecture',
    category: 'business',
    description: 'Offer ladder, pricing assumptions, guarantee/risk reversal, and packaging options.',
    outputs: ['offer_ladder', 'pricing_assumptions', 'guarantees', 'upsells'],
    risk: 'caution',
  },
  {
    id: 'content-engine',
    name: 'Content Engine',
    category: 'growth',
    description: 'Content pillars, 30-day calendar, channel plan, and approval-gated publishing workflow.',
    outputs: ['content_pillars', 'calendar', 'channel_plan', 'approval_workflow'],
    risk: 'caution',
  },
  {
    id: 'finance-model',
    name: 'Finance Model Draft',
    category: 'finance',
    description: 'Draft-only assumptions for pricing, unit economics, runway, CAC/LTV, and budget.',
    outputs: ['unit_economics', 'budget', 'pricing_model', 'finance_review'],
    risk: 'caution',
  },
  {
    id: 'launch-workflow',
    name: 'Launch Workflow',
    category: 'operations',
    description: 'Main-AI launch tasks, workflow draft, scheduler suggestions, and optional code handoff points.',
    outputs: ['launch_tasks', 'workflow_draft', 'schedule_plan', 'code_handoff_points'],
    risk: 'caution',
  },
];

function ensureStateDir() {
  fs.mkdirSync(STATE_DIR, { recursive: true });
}

function readJson(file, fallback = {}) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  ensureStateDir();
  fs.writeFileSync(file, JSON.stringify(data, null, 2), { mode: 0o600 });
}

function loadIntegrationManifest() {
  return readJson(CONFIG_FILE, {
    state: 'degraded',
    sources: [],
    engineering_skills: [],
    finance_workflows: [],
    money_mode: { state: 'degraded' },
    autonomy_policy: { state: 'degraded', risk_levels: {} },
    channels: { state: 'disabled' },
    wallet_vault: { state: 'disabled' },
  });
}

function readVendorManifests() {
  const dir = path.join(REPO_ROOT, 'runtime', 'vendor', 'manifests');
  try {
    return fs.readdirSync(dir)
      .filter(name => name.endsWith('.json'))
      .map(name => readJson(path.join(dir, name), { id: name.replace(/\.json$/, ''), state: 'degraded' }));
  } catch {
    return [];
  }
}

function audit(event, details = {}) {
  ensureStateDir();
  const line = JSON.stringify({ ts: new Date().toISOString(), event, details }) + '\n';
  fs.appendFileSync(WALLET_AUDIT_FILE, line, { mode: 0o600 });
}

function requireOwnerApproval(req, res, action) {
  if (req.body?.ownerApproved === true || req.body?.approval === 'owner-approved') return true;
  res.status(403).json({
    ok: false,
    state: 'disabled',
    action,
    error: 'owner approval required',
    approval_required: true,
  });
  return false;
}

function scoreSkill(skill, query) {
  const haystack = [
    skill.id,
    skill.name,
    skill.category,
    ...(skill.trigger_keywords || []),
    ...(skill.verification_gates || []),
  ].join(' ').toLowerCase();
  return query.split(/\s+/).filter(Boolean).reduce((score, word) => score + (haystack.includes(word) ? 1 : 0), 0);
}

function classifyToolRisk(payload, policy) {
  const text = [
    payload.tool,
    payload.action,
    payload.intent,
    payload.command,
    payload.path,
    ...(payload.capabilities || []),
  ].filter(Boolean).join(' ').toLowerCase();

  const forbidden = policy.forbidden_capabilities || [];
  const dangerous = policy.dangerous_capabilities || [];
  const matchedForbidden = forbidden.find(cap => text.includes(String(cap).replace(/_/g, ' ')) || text.includes(String(cap)));
  if (matchedForbidden) return { risk: 'forbidden', matched: matchedForbidden };
  const matchedDangerous = dangerous.find(cap => text.includes(String(cap).replace(/_/g, ' ')) || text.includes(String(cap)));
  if (matchedDangerous) return { risk: 'dangerous', matched: matchedDangerous };
  if (payload.risk && policy.risk_levels?.[payload.risk]) return { risk: payload.risk, matched: 'declared' };
  if (/\b(write|delete|shell|send|publish|pay|wallet|purchase|install|deploy)\b/.test(text)) return { risk: 'dangerous', matched: 'keyword' };
  if (/\b(read|list|inspect|summarize|plan)\b/.test(text)) return { risk: 'safe', matched: 'keyword' };
  return { risk: 'caution', matched: 'default' };
}

function buildMoneyTasks() {
  const now = Date.now();
  return [
    {
      id: 'internal-audit-dashboard',
      title: 'Audit dashboard route readiness and error states',
      source: 'internal-opportunities',
      state: moneyTaskState.get('internal-audit-dashboard')?.state || 'live',
      estimated_hours: 3,
      risk: 'caution',
      created_at: new Date(now - 3600000).toISOString(),
    },
    {
      id: 'finance-model-template',
      title: 'Prepare supervised finance model template',
      source: 'internal-opportunities',
      state: moneyTaskState.get('finance-model-template')?.state || 'live',
      estimated_hours: 4,
      risk: 'dangerous',
      created_at: new Date(now - 7200000).toISOString(),
    },
  ];
}

function quoteForTask(task) {
  const hours = Number(task.estimated_hours || 2);
  const riskMultiplier = task.risk === 'dangerous' ? 1.7 : task.risk === 'caution' ? 1.25 : 1;
  const amount = Math.max(25, Math.round(hours * 45 * riskMultiplier));
  return {
    currency: 'USD',
    amount,
    basis: ['estimated_hours', 'risk', 'approval_required'],
    approval_required: true,
  };
}

function readBrandKits() {
  const data = readJson(BRAND_KITS_FILE, []);
  return Array.isArray(data) ? data : [];
}

function saveBrandKits(kits) {
  writeJson(BRAND_KITS_FILE, kits.slice(0, 500));
}

function selectedTemplates(ids) {
  const selected = new Set(Array.isArray(ids) ? ids : [ids].filter(Boolean));
  const list = BUSINESS_TEMPLATES.filter(item => selected.size === 0 || selected.has(item.id));
  return list.length ? list : BUSINESS_TEMPLATES.slice(0, 1);
}

function createBrandKitDraft(payload = {}, templateId = '') {
  const templates = selectedTemplates(payload.template_ids || templateId);
  const project = String(payload.project || payload.project_name || payload.project_id || 'Current project').slice(0, 160);
  const audience = String(payload.audience || payload.icp || 'target customers').slice(0, 300);
  const goal = String(payload.goal || 'Create an enterprise-ready brand and launch system').slice(0, 500);
  const id = `brand-${Date.now()}-${crypto.randomBytes(3).toString('hex')}`;
  return {
    id,
    project,
    goal,
    selected_template_ids: templates.map(item => item.id),
    status: 'draft_pending_review',
    owner_approval_required_for_execution: true,
    created_by: 'main_ai_orchestrator',
    ascendforge_boundary: 'AscendForge may create approved code, website files, or project artifacts only. Main AI owns workflows, tasks, economy, memory, and business orchestration.',
    brand_strategy: {
      positioning: `${project} helps ${audience} achieve ${goal.toLowerCase()} with measurable, approval-gated AI operations.`,
      icp: audience,
      voice: payload.voice || 'direct, premium, technical, outcome-focused',
      differentiators: ['offline-first AI system', 'supervised execution', 'memory-aware workflows', 'enterprise governance'],
    },
    offers: {
      primary_offer: payload.offer || `${project} implementation package`,
      pricing_assumptions: ['draft only', 'requires owner review', 'validate against market data before use'],
      upsells: ['workflow automation', 'brand content engine', 'security hardening', 'analytics reporting'],
    },
    content_calendar: [
      { week: 1, theme: 'Problem and positioning', deliverables: ['founder post', 'landing-page outline', 'FAQ draft'] },
      { week: 2, theme: 'Proof and workflow', deliverables: ['case-study outline', 'demo script', 'email sequence draft'] },
      { week: 3, theme: 'Offer and conversion', deliverables: ['offer page copy', 'pricing explainer', 'sales follow-up draft'] },
      { week: 4, theme: 'Launch and feedback', deliverables: ['launch checklist', 'feedback survey', 'iteration plan'] },
    ],
    finance_draft: {
      disclaimer: 'Draft-only finance assumptions. Not investment advice, ledger posting, or transaction execution.',
      assumptions: ['validate CAC manually', 'review pricing with owner', 'no external payment action without approval'],
      review_workflows: ['finance_workflow_model_builder', 'finance_workflow_valuation_reviewer'],
    },
    tasks: templates.map((template, index) => ({
      id: `${id}-task-${index + 1}`,
      title: `Prepare ${template.name}`,
      owner: 'main_ai',
      status: 'draft',
      approval_required: true,
      risk: template.risk,
    })),
    workflow_recommendations: [
      { template_id: 'brand-kit-launch', owner: 'main_ai', status: 'draft' },
      { template_id: 'content-publish', owner: 'main_ai', status: 'draft' },
    ],
    created_at: new Date().toISOString(),
  };
}

function encryptSecret(secret, passphrase) {
  const salt = crypto.randomBytes(16);
  const iv = crypto.randomBytes(12);
  const key = crypto.scryptSync(passphrase, salt, 32);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const encrypted = Buffer.concat([cipher.update(secret, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return {
    algorithm: 'aes-256-gcm',
    kdf: 'scrypt',
    salt: salt.toString('base64'),
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
    data: encrypted.toString('base64'),
  };
}

function walletStatus() {
  const wallet = readJson(WALLET_FILE, null);
  if (!wallet) {
    return {
      state: 'disabled',
      configured: false,
      mode: 'owner_controlled_local_vault',
      external_compute_enabled: false,
      balance: { currency: 'USD', available: 0, pending: 0 },
    };
  }
  return {
    state: 'live',
    configured: true,
    mode: wallet.mode,
    address: wallet.address,
    label: wallet.label,
    created_at: wallet.created_at,
    external_compute_enabled: false,
    balance: wallet.balance || { currency: 'USD', available: 0, pending: 0 },
  };
}

function createRouter(requireAuth) {
  const router = express.Router();
  const protect = typeof requireAuth === 'function' ? requireAuth : (_req, _res, next) => next();
  const forge = getAscendForgeEngine();
  router.use(createRouteRateLimit({ keyPrefix: 'fork-integrations', max: 120, windowMs: 60_000 }));

  router.get('/vendor/sources', (_req, res) => {
    const manifest = loadIntegrationManifest();
    res.json({
      ok: true,
      state: manifest.state || 'live',
      mode: manifest.integration_mode,
      sources: manifest.sources || [],
      manifests: readVendorManifests(),
      source_trust: readJson(SOURCE_TRUST_FILE, {}),
    });
  });

  router.get('/skills/library', (_req, res) => {
    const { source_pack: sourcePack, category } = _req.query || {};
    res.json(forge.listSkills({ sourcePack, category }));
  });

  router.get('/skills/library/:id', (req, res) => {
    const skill = forge.getSkill(req.params.id);
    if (!skill) return res.status(404).json({ ok: false, state: 'degraded', error: 'unknown skill' });
    res.json({ ok: true, state: 'live', skill });
  });

  router.get('/skills/packs', (_req, res) => {
    const library = forge.listSkills({});
    const packs = (library.skills || []).reduce((acc, skill) => {
      const id = skill.source_pack || 'core';
      if (!acc[id]) {
        acc[id] = {
          id,
          name: id.replace(/[-_]+/g, ' '),
          state: 'live',
          total_skills: 0,
          categories: new Set(),
          risk_levels: new Set(),
          skills: [],
        };
      }
      acc[id].total_skills += 1;
      if (skill.category) acc[id].categories.add(skill.category);
      if (skill.risk_level) acc[id].risk_levels.add(skill.risk_level);
      acc[id].skills.push({ id: skill.id, name: skill.name, category: skill.category, risk_level: skill.risk_level });
      return acc;
    }, {});
    const items = Object.values(packs).map(pack => ({
      ...pack,
      categories: [...pack.categories],
      risk_levels: [...pack.risk_levels],
      skills: pack.skills.slice(0, 100),
    }));
    res.json({ ok: true, state: items.length ? 'live' : 'empty', source: 'skills_library', packs: items, items });
  });

  router.post('/skills/recommend', (req, res) => {
    res.json(forge.recommendSkills(req.body || {}));
  });

  router.get('/agents/:id/capabilities', protect, (req, res) => {
    const blueprints = forge.listBlueprints();
    const blueprint = blueprints.find(item => item.id === req.params.id);
    if (blueprint) return res.json({ ok: true, state: 'live', source: 'ascend-forge', capabilities: blueprint });
    res.status(404).json({ ok: false, state: 'degraded', error: 'agent capabilities not found' });
  });

  router.get('/agents/:id/skills', protect, (req, res) => {
    const blueprint = forge.listBlueprints().find(item => item.id === req.params.id);
    if (!blueprint) return res.status(404).json({ ok: false, state: 'degraded', error: 'agent skills not found' });
    res.json({
      ok: true,
      state: 'live',
      agent_id: req.params.id,
      skills: (blueprint.selected_skill_ids || []).map(id => forge.getSkill(id)).filter(Boolean),
    });
  });

  router.get('/finance/workflows', (_req, res) => {
    const manifest = loadIntegrationManifest();
    res.json({
      ok: true,
      state: 'live',
      disclaimer: 'Finance workflows create drafts only. They do not provide investment advice, post ledgers, execute trades, or move funds.',
      workflows: manifest.finance_workflows || [],
    });
  });

  router.get('/business/templates', (_req, res) => {
    res.json({
      ok: true,
      state: 'live',
      source: 'native_business_templates',
      templates: BUSINESS_TEMPLATES,
      items: BUSINESS_TEMPLATES,
    });
  });

  router.get('/business/brand-kits', protect, (_req, res) => {
    const kits = readBrandKits();
    res.json({ ok: true, state: kits.length ? 'live' : 'empty', source: 'node_state', brand_kits: kits, items: kits });
  });

  router.post('/business/templates/:id/brand-kit', protect, (req, res) => {
    const template = BUSINESS_TEMPLATES.find(item => item.id === req.params.id);
    if (!template) return res.status(404).json({ ok: false, state: 'empty', error: 'unknown business template' });
    const kit = createBrandKitDraft(req.body || {}, req.params.id);
    const kits = readBrandKits();
    kits.unshift(kit);
    saveBrandKits(kits);
    res.status(201).json({
      ok: true,
      state: 'live',
      source: 'main_ai_orchestrator',
      brand_kit: kit,
      approval_required: true,
    });
  });

  router.post('/finance/workflows/:id/run', protect, (req, res) => {
    const manifest = loadIntegrationManifest();
    const workflow = (manifest.finance_workflows || []).find(item => item.id === req.params.id);
    if (!workflow) return res.status(404).json({ ok: false, state: 'degraded', error: 'unknown finance workflow' });
    const runId = `fin-${Date.now()}-${crypto.randomBytes(3).toString('hex')}`;
    const run = {
      id: runId,
      workflow_id: workflow.id,
      status: 'draft_pending_review',
      approval_required: true,
      created_at: new Date().toISOString(),
      inputs: req.body || {},
      outputs: workflow.outputs,
      disclaimer: 'Draft output only. Human review is required before external use.',
    };
    financeRuns.set(runId, run);
    res.json({ ok: true, state: 'live', run });
  });

  router.post('/finance/workflows/:runId/approve', protect, (req, res) => {
    if (!requireOwnerApproval(req, res, 'approve_finance_workflow')) return;
    const run = financeRuns.get(req.params.runId);
    if (!run) return res.status(404).json({ ok: false, state: 'degraded', error: 'unknown finance workflow run' });
    run.status = 'approved_for_internal_use';
    run.approved_at = new Date().toISOString();
    res.json({ ok: true, state: 'live', run });
  });

  router.get('/money/tasks', (_req, res) => {
    const manifest = loadIntegrationManifest();
    res.json({
      ok: true,
      state: 'live',
      policy: manifest.money_mode,
      tasks: buildMoneyTasks(),
    });
  });

  router.post('/money/tasks/:id/evaluate', protect, (req, res) => {
    const task = buildMoneyTasks().find(item => item.id === req.params.id);
    if (!task) return res.status(404).json({ ok: false, state: 'degraded', error: 'unknown money task' });
    const evaluation = {
      task_id: task.id,
      fit: task.risk === 'dangerous' ? 'review_required' : 'good_fit',
      risk: task.risk,
      next_step: 'quote-draft',
      approval_required: task.risk === 'dangerous',
      notes: req.body?.notes || null,
    };
    moneyTaskState.set(task.id, { ...(moneyTaskState.get(task.id) || {}), evaluation, state: 'evaluated' });
    res.json({ ok: true, state: 'live', evaluation });
  });

  router.post('/money/tasks/:id/quote-draft', protect, (req, res) => {
    const task = buildMoneyTasks().find(item => item.id === req.params.id);
    if (!task) return res.status(404).json({ ok: false, state: 'degraded', error: 'unknown money task' });
    const quote = quoteForTask(task);
    moneyTaskState.set(task.id, { ...(moneyTaskState.get(task.id) || {}), quote, state: 'quote_draft' });
    res.json({ ok: true, state: 'live', quote });
  });

  router.post('/money/tasks/:id/deliver', protect, (req, res) => {
    if (!requireOwnerApproval(req, res, 'deliver_money_task')) return;
    const task = buildMoneyTasks().find(item => item.id === req.params.id);
    if (!task) return res.status(404).json({ ok: false, state: 'degraded', error: 'unknown money task' });
    moneyTaskState.set(task.id, { ...(moneyTaskState.get(task.id) || {}), state: 'approved_for_delivery' });
    res.json({
      ok: true,
      state: 'live',
      delivery: {
        task_id: task.id,
        status: 'approved_for_delivery',
        external_delivery_enabled: false,
        message: 'Deliverable approved internally. External delivery adapters are disabled by default.',
      },
    });
  });

  router.post('/money/feedback', protect, (req, res) => {
    res.json({
      ok: true,
      state: 'live',
      memory_hook: {
        type: 'money_feedback',
        task_id: req.body?.task_id || null,
        stored: false,
        next_step: 'connect to persistent memory ingestion',
      },
    });
  });

  router.get('/autonomy/policy', (_req, res) => {
    const manifest = loadIntegrationManifest();
    res.json({ ok: true, state: 'live', policy: manifest.autonomy_policy });
  });

  router.post('/autonomy/tool-call/evaluate', protect, (req, res) => {
    const manifest = loadIntegrationManifest();
    const policy = manifest.autonomy_policy || {};
    const { risk, matched } = classifyToolRisk(req.body || {}, policy);
    const level = policy.risk_levels?.[risk] || { decision: 'requires_approval', requires_approval: true };
    res.json({
      ok: true,
      state: 'live',
      risk,
      matched,
      decision: level.decision,
      requires_approval: !!level.requires_approval,
      audit_required: risk !== 'safe',
    });
  });

  router.get('/autonomy/heartbeat', (_req, res) => {
    res.json({
      ok: true,
      state: 'live',
      heartbeat: {
        status: 'online',
        queued_tasks: heartbeatTasks.length,
        last_tick: new Date().toISOString(),
      },
    });
  });

  router.post('/autonomy/heartbeat/task', protect, (req, res) => {
    const task = {
      id: `hb-${Date.now()}-${crypto.randomBytes(2).toString('hex')}`,
      goal: String(req.body?.goal || 'policy heartbeat task').slice(0, 500),
      risk: req.body?.risk || 'caution',
      created_at: new Date().toISOString(),
    };
    heartbeatTasks.push(task);
    res.json({ ok: true, state: 'live', task });
  });

  router.get('/channels', (_req, res) => {
    const manifest = loadIntegrationManifest();
    res.json({
      ok: true,
      state: manifest.channels?.state || 'disabled',
      channels: [
        { id: 'local-dashboard', name: 'Local Dashboard', state: 'live', paired: true },
        { id: 'telegram', name: 'Telegram', state: 'disabled', paired: pairedChannels.has('telegram') },
        { id: 'discord', name: 'Discord', state: 'disabled', paired: pairedChannels.has('discord') },
        { id: 'slack', name: 'Slack', state: 'disabled', paired: pairedChannels.has('slack') },
      ],
    });
  });

  router.post('/channels/:id/pair', protect, (req, res) => {
    if (req.params.id !== 'local-dashboard') {
      return res.status(403).json({ ok: false, state: 'disabled', error: 'external channel adapters are disabled by default' });
    }
    pairedChannels.set(req.params.id, { paired_at: new Date().toISOString(), allowlist: ['local-user'] });
    res.json({ ok: true, state: 'live', channel: { id: req.params.id, paired: true } });
  });

  router.post('/channels/:id/send', protect, (req, res) => {
    if (req.params.id !== 'local-dashboard') {
      return res.status(403).json({ ok: false, state: 'disabled', error: 'external channel sending is disabled by default' });
    }
    res.json({ ok: true, state: 'live', delivered: true, channel: req.params.id, message_id: `msg-${Date.now()}` });
  });

  router.get('/sessions', (_req, res) => {
    res.json({ ok: true, state: 'live', sessions: [...sessions.values()] });
  });

  router.post('/sessions/:id/route', protect, (req, res) => {
    const session = {
      id: req.params.id,
      channel: req.body?.channel || 'local-dashboard',
      agent: req.body?.agent || 'ascend-forge',
      updated_at: new Date().toISOString(),
    };
    sessions.set(session.id, session);
    res.json({ ok: true, state: 'live', session });
  });

  router.get('/wallet/status', (_req, res) => {
    const manifest = loadIntegrationManifest();
    res.json({
      ok: true,
      state: walletStatus().state,
      policy: manifest.wallet_vault,
      wallet: walletStatus(),
    });
  });

  router.post('/wallet/create', protect, (req, res) => {
    if (!requireOwnerApproval(req, res, 'create_wallet')) return;
    const passphrase = String(req.body?.passphrase || '');
    if (passphrase.length < 12) {
      return res.status(400).json({ ok: false, state: 'degraded', error: 'passphrase must be at least 12 characters' });
    }
    ensureStateDir();
    if (fs.existsSync(WALLET_FILE)) {
      return res.status(409).json({ ok: false, state: 'live', error: 'wallet already exists', wallet: walletStatus() });
    }
    const keypair = crypto.generateKeyPairSync('ed25519');
    const publicKey = keypair.publicKey.export({ type: 'spki', format: 'pem' });
    const privateKey = keypair.privateKey.export({ type: 'pkcs8', format: 'pem' });
    const address = `aet_${crypto.createHash('sha256').update(publicKey).digest('hex').slice(0, 40)}`;
    const wallet = {
      version: 1,
      mode: 'owner_controlled_local_vault',
      label: String(req.body?.label || 'Owner Vault').slice(0, 80),
      address,
      public_key: publicKey,
      encrypted_private_key: encryptSecret(privateKey, passphrase),
      balance: { currency: 'USD', available: 0, pending: 0 },
      external_compute_enabled: false,
      created_at: new Date().toISOString(),
    };
    fs.writeFileSync(WALLET_FILE, JSON.stringify(wallet, null, 2), { mode: 0o600 });
    audit('wallet_created', { address, label: wallet.label });
    res.json({ ok: true, state: 'live', wallet: walletStatus() });
  });

  router.post('/wallet/claim-request', protect, (req, res) => {
    if (!requireOwnerApproval(req, res, 'claim_funds')) return;
    const wallet = walletStatus();
    if (!wallet.configured) return res.status(409).json({ ok: false, state: 'disabled', error: 'wallet not configured' });
    const request = {
      id: `claim-${Date.now()}-${crypto.randomBytes(2).toString('hex')}`,
      wallet: wallet.address,
      amount: Number(req.body?.amount || 0),
      currency: String(req.body?.currency || 'USD'),
      status: 'approved_for_owner_claim_review',
      external_transfer_enabled: false,
      created_at: new Date().toISOString(),
    };
    audit('claim_requested', request);
    res.json({ ok: true, state: 'live', request });
  });

  router.post('/wallet/compute-purchase/quote', protect, (req, res) => {
    const manifest = loadIntegrationManifest();
    const enabled = manifest.wallet_vault?.purchase_policy?.external_compute_enabled === true;
    if (!enabled) {
      return res.status(403).json({
        ok: false,
        state: 'disabled',
        error: 'external compute purchases are disabled by default',
        approval_required: true,
        policy: manifest.wallet_vault?.purchase_policy,
      });
    }
    if (!requireOwnerApproval(req, res, 'buy_external_compute')) return;
    res.json({
      ok: true,
      state: 'live',
      quote: {
        provider: req.body?.provider,
        estimated_usd: Number(req.body?.estimated_usd || 0),
        status: 'owner_approved_quote_only',
        purchase_executed: false,
      },
    });
  });

  router.get('/mobile/status', (_req, res) => {
    const pairings = readJson(MOBILE_PAIRINGS_FILE, []);
    const list = Array.isArray(pairings) ? pairings : [];
    res.json({
      ok: true,
      state: 'live',
      mobile_access: 'pairing_required',
      server_time: new Date().toISOString(),
      paired_devices: list.filter(item => item.status === 'approved').length,
      pending_requests: list
        .filter(item => item.status === 'pending_owner_approval')
        .map(item => ({
          id: item.id,
          device_id: item.device_id,
          device_name: item.device_name,
          status: item.status,
          created_at: item.created_at,
          expires_at: item.expires_at,
        })),
      approved_devices: list
        .filter(item => item.status === 'approved')
        .map(item => ({
          id: item.id,
          device_id: item.device_id,
          device_name: item.device_name,
          status: item.status,
          approved_at: item.approved_at,
        })),
      security: {
        auth: 'jwt_refresh_rotation',
        storage: 'device_keychain_or_keystore',
        pairing: 'owner_approval_required',
        recommended_transport: 'https_or_trusted_lan',
      },
    });
  });

  router.post('/mobile/pair/request', (req, res) => {
    const deviceId = String(req.body?.device_id || crypto.randomUUID()).slice(0, 120);
    const deviceName = String(req.body?.device_name || 'NEXUS Mobile').slice(0, 120);
    const code = crypto.randomInt(100000, 999999).toString();
    const request = {
      id: `mob-${Date.now()}-${crypto.randomBytes(2).toString('hex')}`,
      device_id: deviceId,
      device_name: deviceName,
      code_hash: crypto.createHash('sha256').update(code).digest('hex'),
      status: 'pending_owner_approval',
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
    };
    const pairings = readJson(MOBILE_PAIRINGS_FILE, []);
    const list = Array.isArray(pairings) ? pairings.filter(item => item.device_id !== deviceId) : [];
    list.unshift(request);
    writeJson(MOBILE_PAIRINGS_FILE, list.slice(0, 100));
    audit('mobile_pair_requested', { id: request.id, device_id: deviceId, device_name: deviceName });
    res.json({
      ok: true,
      state: 'live',
      request_id: request.id,
      pairing_code: code,
      expires_at: request.expires_at,
      approval_required: true,
    });
  });

  router.get('/mobile/pair/:id/status', (req, res) => {
    const pairings = readJson(MOBILE_PAIRINGS_FILE, []);
    const list = Array.isArray(pairings) ? pairings : [];
    const item = list.find(entry => entry.id === req.params.id);
    if (!item) return res.status(404).json({ ok: false, state: 'degraded', error: 'pairing request not found' });
    const expired = item.status === 'pending_owner_approval' && new Date(item.expires_at).getTime() < Date.now();
    if (expired) {
      item.status = 'expired';
      writeJson(MOBILE_PAIRINGS_FILE, list);
    }
    res.json({
      ok: true,
      state: expired ? 'expired' : 'live',
      request_id: item.id,
      status: item.status,
      approved: item.status === 'approved',
      expires_at: item.expires_at,
    });
  });

  router.post('/mobile/pair/:id/approve', protect, (req, res) => {
    if (!requireOwnerApproval(req, res, 'approve_mobile_pairing')) return;
    const pairings = readJson(MOBILE_PAIRINGS_FILE, []);
    const list = Array.isArray(pairings) ? pairings : [];
    const item = list.find(entry => entry.id === req.params.id);
    if (!item) return res.status(404).json({ ok: false, state: 'degraded', error: 'pairing request not found' });
    item.status = 'approved';
    item.approved_at = new Date().toISOString();
    item.mobile_token_hint = crypto.randomBytes(16).toString('hex');
    writeJson(MOBILE_PAIRINGS_FILE, list);
    audit('mobile_pair_approved', { id: item.id, device_id: item.device_id });
    res.json({ ok: true, state: 'live', pairing: { id: item.id, device_id: item.device_id, status: item.status } });
  });

  return router;
}

module.exports = createRouter;
