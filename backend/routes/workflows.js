'use strict'

const express = require('express')
const fs = require('fs')
const os = require('os')
const path = require('path')
const crypto = require('crypto')

const STATE_DIR = path.resolve(process.env.STATE_DIR || process.env.AI_EMPLOYEE_STATE_DIR || path.join(os.homedir(), '.ai-employee', 'state'))
const WORKFLOWS_FILE = path.join(STATE_DIR, 'workflow_definitions.json')
const WORKFLOW_RUNS_FILE = path.join(STATE_DIR, 'workflow_template_runs.json')

const TEMPLATE_LIBRARY = [
  {
    id: 'lead-to-close',
    name: 'Lead -> Enrich -> Score -> Outreach',
    category: 'sales',
    description: 'Find leads, enrich company context, score fit, and stage personalized outreach for approval.',
    agents: ['lead-hunter-elite', 'qualification-agent', 'sales-closer-pro'],
    skills: ['lead_research', 'lead_qualification', 'outreach_sequence'],
    estimatedCostPerRun: '$0.18',
    risk: 'caution',
    approval_policy: 'approval_required_before_external_send',
    steps: [
      { id: 'discover', label: 'Discover leads', type: 'agent_task' },
      { id: 'enrich', label: 'Enrich and dedupe', type: 'agent_task' },
      { id: 'score', label: 'Score ICP fit', type: 'validation' },
      { id: 'draft', label: 'Draft outreach', type: 'draft_output' },
      { id: 'approve', label: 'Owner approval', type: 'hitl_gate' },
    ],
    outputs: ['lead list', 'fit score', 'outreach draft'],
  },
  {
    id: 'content-publish',
    name: 'Content -> Review -> Schedule -> Post',
    category: 'content',
    description: 'Research a topic, create content, review quality, and stage channel publishing.',
    agents: ['content-generator', 'seo-specialist', 'social-media-manager'],
    skills: ['content_research', 'copywriting', 'editorial_review'],
    estimatedCostPerRun: '$0.24',
    risk: 'caution',
    approval_policy: 'approval_required_before_publish',
    steps: [
      { id: 'research', label: 'Research topic', type: 'retrieval' },
      { id: 'draft', label: 'Draft content', type: 'agent_task' },
      { id: 'review', label: 'Quality and compliance review', type: 'validation' },
      { id: 'schedule', label: 'Schedule draft', type: 'scheduler' },
      { id: 'approve', label: 'Owner approval', type: 'hitl_gate' },
    ],
    outputs: ['content draft', 'SEO notes', 'schedule draft'],
  },
  {
    id: 'competitor-watch',
    name: 'Competitor Change -> Alert + Draft Response',
    category: 'intelligence',
    description: 'Monitor competitor changes and stage strategic responses for internal review.',
    agents: ['web-research-agent', 'competitive-analyst', 'ceo-briefing'],
    skills: ['market_research', 'change_detection', 'executive_summary'],
    estimatedCostPerRun: '$0.09',
    risk: 'safe',
    approval_policy: 'logged_only',
    steps: [
      { id: 'watch', label: 'Collect monitored signals', type: 'retrieval' },
      { id: 'diff', label: 'Detect meaningful change', type: 'analysis' },
      { id: 'brief', label: 'Create executive alert', type: 'synthesis' },
    ],
    outputs: ['change alert', 'recommended response'],
  },
  {
    id: 'brand-kit-launch',
    name: 'Brand Kit -> Launch Workflow',
    category: 'business',
    description: 'Main AI creates a supervised brand kit, launch tasks, finance draft, and content workflow for a running project. AscendForge is only used for approved code or website artifacts.',
    agents: ['main-orchestrator', 'finance-wizard', 'content-generator', 'strategy-engine'],
    skills: ['brand_strategy', 'offer_architecture', 'finance_workflow_model_builder', 'content_calendar'],
    estimatedCostPerRun: '$0.32',
    risk: 'caution',
    approval_policy: 'approval_required_before_file_or_external_action',
    steps: [
      { id: 'strategy', label: 'Positioning and ICP', type: 'planning' },
      { id: 'offers', label: 'Offer and pricing draft', type: 'finance_draft' },
      { id: 'calendar', label: 'Content calendar', type: 'draft_output' },
      { id: 'tasks', label: 'Stage launch tasks', type: 'task_creation' },
      { id: 'code_handoff', label: 'Optional approved code handoff to AscendForge', type: 'hitl_gate' },
    ],
    outputs: ['brand kit', 'finance assumptions', 'launch tasks', 'workflow draft'],
  },
]

function ensureStateDir() {
  fs.mkdirSync(STATE_DIR, { recursive: true })
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

function writeJson(file, data) {
  ensureStateDir()
  fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8')
}

function loadDefinitions() {
  const data = readJson(WORKFLOWS_FILE, [])
  return Array.isArray(data) ? data : []
}

function saveDefinitions(definitions) {
  writeJson(WORKFLOWS_FILE, definitions.slice(0, 1000))
}

function loadRuns() {
  const data = readJson(WORKFLOW_RUNS_FILE, [])
  return Array.isArray(data) ? data : []
}

function saveRuns(runs) {
  writeJson(WORKFLOW_RUNS_FILE, runs.slice(0, 2000))
}

function normalizeDefinition(def = {}) {
  const now = new Date().toISOString()
  const template = TEMPLATE_LIBRARY.find((item) => item.id === def.template_id || item.id === def.template) || null
  return {
    id: def.id || `wfdef-${Date.now()}-${crypto.randomBytes(2).toString('hex')}`,
    name: String(def.name || template?.name || 'Workflow draft').slice(0, 160),
    description: String(def.description || template?.description || '').slice(0, 1000),
    template_id: def.template_id || def.template || template?.id || null,
    category: def.category || template?.category || 'custom',
    status: def.status || 'draft',
    trigger: def.trigger || 'manual',
    agents: Array.isArray(def.agents) ? def.agents : template?.agents || [],
    skills: Array.isArray(def.skills) ? def.skills : template?.skills || [],
    steps: Array.isArray(def.steps) ? def.steps : template?.steps || [],
    outputs: Array.isArray(def.outputs) ? def.outputs : template?.outputs || [],
    risk: def.risk || template?.risk || 'caution',
    approval_policy: def.approval_policy || template?.approval_policy || 'approval_required',
    created_at: def.created_at || now,
    updated_at: def.updated_at || now,
    last_run: def.last_run || null,
    runs_today: def.runs_today || 0,
    success_rate: def.success_rate ?? null,
  }
}

function makeRun(definition, input = {}) {
  const now = new Date().toISOString()
  return {
    id: `wfrun-${Date.now()}-${crypto.randomBytes(2).toString('hex')}`,
    workflow_id: definition.id,
    workflow_name: definition.name,
    status: 'draft_pending_execution',
    state: 'WAITING_APPROVAL',
    input,
    nodes: definition.steps.map((step, index) => ({
      id: `${definition.id}-${step.id || index}`,
      label: step.label || step.name || `Step ${index + 1}`,
      type: step.type || 'step',
      status: index === 0 ? 'ready' : 'pending',
      agent: definition.agents[index % Math.max(1, definition.agents.length)] || 'unassigned',
    })),
    approval_required: definition.approval_policy !== 'logged_only',
    created_at: now,
    updated_at: now,
  }
}

module.exports = function createWorkflowsRouter(requireAuth) {
  const router = express.Router()

  router.get('/', requireAuth, (_req, res) => {
    const definitions = loadDefinitions().map(normalizeDefinition)
    res.json({
      ok: true,
      state: definitions.length ? 'live' : 'empty',
      source: 'node_workflow_store',
      workflows: definitions,
      items: definitions,
      total: definitions.length,
    })
  })

  router.get('/templates', requireAuth, (_req, res) => {
    res.json({
      ok: true,
      state: 'live',
      source: 'native_template_library',
      templates: TEMPLATE_LIBRARY,
      items: TEMPLATE_LIBRARY,
      total: TEMPLATE_LIBRARY.length,
    })
  })

  router.get('/templates/:id', requireAuth, (req, res) => {
    const template = TEMPLATE_LIBRARY.find((item) => item.id === req.params.id)
    if (!template) return res.status(404).json({ ok: false, state: 'empty', error: 'template not found' })
    res.json({ ok: true, state: 'live', source: 'native_template_library', template })
  })

  router.post('/templates/:id/instantiate', requireAuth, (req, res) => {
    const template = TEMPLATE_LIBRARY.find((item) => item.id === req.params.id)
    if (!template) return res.status(404).json({ ok: false, state: 'empty', error: 'template not found' })
    const definitions = loadDefinitions().map(normalizeDefinition)
    const definition = normalizeDefinition({
      ...(req.body || {}),
      id: undefined,
      name: req.body?.name || template.name,
      template_id: template.id,
      status: 'draft',
      created_at: new Date().toISOString(),
    })
    definitions.unshift(definition)
    saveDefinitions(definitions)
    res.status(201).json({ ok: true, state: 'live', source: 'node_workflow_store', workflow: definition })
  })

  router.get('/runs', requireAuth, (_req, res) => {
    const runs = loadRuns()
    res.json({ ok: true, state: runs.length ? 'live' : 'empty', source: 'node_workflow_store', runs, items: runs })
  })

  router.post('/', requireAuth, (req, res) => {
    const definitions = loadDefinitions().map(normalizeDefinition)
    const definition = normalizeDefinition(req.body || {})
    definitions.unshift(definition)
    saveDefinitions(definitions)
    res.status(201).json({ ok: true, state: 'live', source: 'node_workflow_store', workflow: definition })
  })

  router.post('/:id/run', requireAuth, (req, res) => {
    const definitions = loadDefinitions().map(normalizeDefinition)
    const definition = definitions.find((item) => item.id === req.params.id || item.template_id === req.params.id)
      || normalizeDefinition(TEMPLATE_LIBRARY.find((item) => item.id === req.params.id) || {})
    if (!definition.id || definition.name === 'Workflow draft') return res.status(404).json({ ok: false, state: 'empty', error: 'workflow not found' })
    const runs = loadRuns()
    const run = makeRun(definition, req.body || {})
    runs.unshift(run)
    saveRuns(runs)
    const nextDefinitions = definitions.map((item) => item.id === definition.id ? { ...item, last_run: run.created_at, runs_today: (item.runs_today || 0) + 1, updated_at: run.created_at } : item)
    if (nextDefinitions.some((item) => item.id === definition.id)) saveDefinitions(nextDefinitions)
    res.json({ ok: true, state: 'live', source: 'node_workflow_store', workflow: definition, run })
  })

  router.get('/:id/runs', requireAuth, (req, res) => {
    const runs = loadRuns().filter((run) => run.workflow_id === req.params.id || run.workflow_name === req.params.id)
    res.json({ ok: true, state: runs.length ? 'live' : 'empty', source: 'node_workflow_store', runs, items: runs })
  })

  router.delete('/:id', requireAuth, (req, res) => {
    const definitions = loadDefinitions().map(normalizeDefinition)
    const next = definitions.filter((workflow) => workflow.id !== req.params.id)
    if (next.length === definitions.length) return res.status(404).json({ ok: false, error: 'not found' })
    saveDefinitions(next)
    res.json({ ok: true, state: 'live', deleted: req.params.id })
  })

  return router
}
