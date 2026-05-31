'use strict'

const fs = require('fs')
const os = require('os')
const path = require('path')
const crypto = require('crypto')

const REPO_ROOT = path.resolve(__dirname, '..', '..')
const SKILLS_FILE = path.join(REPO_ROOT, 'runtime', 'config', 'skills_library.json')
const FORK_FILE = path.join(REPO_ROOT, 'runtime', 'config', 'fork_integration_manifest.json')
const STATE_DIR = path.resolve(process.env.STATE_DIR || process.env.AI_EMPLOYEE_STATE_DIR || path.join(os.homedir(), '.ai-employee', 'state'))
const BLUEPRINTS_FILE = path.join(STATE_DIR, 'ascendforge_agent_blueprints.json')
const CUSTOM_AGENTS_FILE = path.join(STATE_DIR, 'custom_agents.json')
const AUDIT_FILE = path.join(STATE_DIR, 'ascendforge_audit.jsonl')

const DEFAULT_HOOKS = [
  'before_plan:skill_recommendation',
  'before_action:policy_check',
  'before_write:sandbox_preview',
  'after_result:memory_write',
  'on_failure:rollback_or_escalate',
]

const DEFAULT_APPROVAL_POLICY = {
  file_write: 'approval_required',
  shell_command: 'approval_required',
  dependency_install: 'approval_required',
  external_delivery: 'approval_required',
  wallet_or_compute: 'owner_approval_required',
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return fallback }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, JSON.stringify(data, null, 2))
}

function audit(event, details = {}) {
  ensureDir(STATE_DIR)
  fs.appendFileSync(AUDIT_FILE, JSON.stringify({ ts: new Date().toISOString(), event, details }) + '\n', { mode: 0o600 })
}

function slugify(value) {
  const input = String(value || 'agent').toLowerCase()
  let out = ''
  let pendingDash = false
  for (const ch of input) {
    const code = ch.charCodeAt(0)
    const isAlphaNum = (code >= 97 && code <= 122) || (code >= 48 && code <= 57)
    if (isAlphaNum) {
      if (pendingDash && out) out += '-'
      out += ch
      pendingDash = false
    } else {
      pendingDash = true
    }
    if (out.length >= 80) break
  }
  return out || 'agent'
}

function loadSkillsLibrary() {
  const data = readJson(SKILLS_FILE, { _meta: {}, categories: [], skills: [] })
  const skills = Array.isArray(data.skills) ? data.skills : []
  return { ...data, skills }
}

function loadForkManifest() {
  return readJson(FORK_FILE, { autonomy_policy: {}, canonical_skill_ids: [] })
}

function normalizeQuery(payload = {}) {
  return [
    payload.goal,
    payload.task,
    payload.purpose,
    payload.target_type,
    payload.domain,
    payload.risk,
  ].filter(Boolean).join(' ').toLowerCase()
}

function skillText(skill) {
  return [
    skill.id,
    skill.name,
    skill.category,
    skill.description,
    ...(skill.tags || []),
    ...(skill.aliases || []),
    ...(skill.compatible_agents || []),
    ...(skill.verification_gates || []),
  ].filter(Boolean).join(' ').toLowerCase()
}

function scoreSkill(skill, query, payload = {}) {
  const text = skillText(skill)
  const terms = query.split(/[^a-z0-9_]+/).filter(term => term.length > 2)
  let score = terms.reduce((total, term) => total + (text.includes(term) ? 2 : 0), 0)
  if (skill.compatible_agents?.includes('ascend-forge')) score += 3
  if (skill.source_pack === 'agent-skills') score += 2
  if (String(payload.target_type || '').includes('agent') && /agent|build|code|engineering|workflow/.test(text)) score += 3
  if (/\bfinance|model|valuation|kyc|audit|earnings\b/.test(query) && skill.source_pack === 'financial-services') score += 5
  if (/\bmoney|quote|task|deliver|earning|wallet|compute\b/.test(query) && ['cashclaw', 'wallet-vault'].includes(skill.source_pack)) score += 5
  if (/\bpolicy|risk|approval|sandbox|shell|write|install\b/.test(query) && skill.source_pack === 'automaton') score += 5
  return score
}

class AscendForgeEngine {
  getStatus() {
    const skills = loadSkillsLibrary().skills
    const blueprints = this.listBlueprints()
    return {
      ok: true,
      state: 'live',
      engine: 'thin-core',
      authority_profile: 'supervised_builder',
      skills_total: skills.length,
      fork_skills: skills.filter(skill => skill.source_pack).length,
      blueprints_total: blueprints.length,
      registered_agents: blueprints.filter(item => item.registration_status === 'registered').length,
      routes: ['/api/forge/*', '/api/neural-brain/forge/*'],
    }
  }

  listSkills({ sourcePack, category } = {}) {
    const library = loadSkillsLibrary()
    let skills = library.skills
    if (sourcePack) skills = skills.filter(skill => skill.source_pack === sourcePack)
    if (category) skills = skills.filter(skill => skill.category === category)
    return {
      ok: true,
      state: 'live',
      meta: library._meta || {},
      categories: library.categories || [],
      skills,
    }
  }

  getSkill(id) {
    const skill = loadSkillsLibrary().skills.find(item => item.id === id || item.aliases?.includes(id))
    return skill || null
  }

  recommendSkills(payload = {}) {
    const query = normalizeQuery(payload)
    const limit = Math.max(1, Math.min(Number(payload.limit || 8), 20))
    const library = loadSkillsLibrary()
    const ranked = library.skills
      .map(skill => ({ ...skill, score: scoreSkill(skill, query, payload) }))
      .filter(skill => skill.score > 0 || skill.source_pack === 'agent-skills')
      .sort((a, b) => b.score - a.score || String(a.id).localeCompare(String(b.id)))
      .slice(0, limit)
    const selected = ranked.length ? ranked : library.skills.filter(skill => skill.source_pack === 'agent-skills').slice(0, limit)
    return {
      ok: true,
      state: 'live',
      recommendedSkills: selected,
      workflow: selected.map(skill => skill.name),
      verificationGates: [...new Set(selected.flatMap(skill => skill.verification_gates || []))],
    }
  }

  createBlueprint(payload = {}) {
    const name = String(payload.name || payload.agent_name || 'AscendForge Builder Agent').trim()
    const id = slugify(payload.id || name)
    const targetType = payload.target_type || 'coding_agent'
    const purpose = String(payload.purpose || payload.goal || 'Build and improve AETERNUS systems under supervision.').trim()
    const selectedSkillIds = Array.isArray(payload.selected_skill_ids) && payload.selected_skill_ids.length
      ? payload.selected_skill_ids
      : this.recommendSkills({ goal: purpose, target_type: targetType, limit: 10 }).recommendedSkills.map(skill => skill.id)
    const selectedSkills = selectedSkillIds.map(skillId => this.getSkill(skillId)).filter(Boolean)
    const verification = [...new Set(selectedSkills.flatMap(skill => skill.verification_gates || []))]
    const riskLevel = selectedSkills.some(skill => skill.risk_level === 'dangerous') ? 'dangerous' : 'caution'
    const blueprint = {
      id,
      name,
      purpose,
      target_type: targetType,
      selected_skill_ids: selectedSkillIds,
      selected_skills: selectedSkills.map(skill => ({ id: skill.id, name: skill.name, category: skill.category, risk_level: skill.risk_level })),
      job_description: payload.job_description || `${name} is a supervised ${targetType.replace(/_/g, ' ')} that plans, drafts, verifies, and requests approval before executing risky work.`,
      workflows: payload.workflows || ['spec', 'plan', 'build', 'test', 'review', 'ship'],
      hooks: payload.hooks || DEFAULT_HOOKS,
      authority_profile: 'supervised_builder',
      approval_policy: DEFAULT_APPROVAL_POLICY,
      allowed_actions: ['read', 'plan', 'draft', 'test_request', 'approval_request'],
      blocked_actions: ['autonomous_spend', 'autonomous_external_delivery', 'unapproved_dependency_install', 'unapproved_file_write'],
      model_profile: payload.model_profile || { route: 'local_first_external_optional', default_architecture: 'MoE' },
      memory_writeback_policy: 'write_summary_after_result',
      risk_level: riskLevel,
      verification_commands: payload.verification_commands || ['npm --prefix frontend run build', 'npm --prefix launcher run verify'],
      verification_gates: verification,
      generated_files: [
        { path: `state/agents/${id}.json`, purpose: 'runtime agent contract' },
        { path: `state/agents/${id}.jsonl`, purpose: 'runtime heartbeat/audit stream' },
      ],
      registration_status: 'draft',
      created_by: 'ascend-forge',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    const blueprints = this.listBlueprints().filter(item => item.id !== id)
    blueprints.unshift(blueprint)
    writeJson(BLUEPRINTS_FILE, blueprints.slice(0, 200))
    audit('blueprint_created', { id, skills: selectedSkillIds, risk_level: riskLevel })
    return { ok: true, state: 'live', blueprint }
  }

  listBlueprints() {
    const data = readJson(BLUEPRINTS_FILE, [])
    return Array.isArray(data) ? data : []
  }

  getBlueprint(id) {
    return this.listBlueprints().find(item => item.id === id) || null
  }

  registerBlueprint(id, payload = {}) {
    const blueprint = this.getBlueprint(id)
    if (!blueprint) {
      const err = new Error(`unknown blueprint: ${id}`)
      err.status = 404
      throw err
    }
    if (payload.ownerApproved !== true && payload.approval !== 'owner-approved') {
      const err = new Error('owner approval required')
      err.status = 403
      err.approval_required = true
      throw err
    }
    const now = new Date().toISOString()
    blueprint.registration_status = 'registered'
    blueprint.registered_at = now
    blueprint.updated_at = now
    const blueprints = this.listBlueprints().map(item => item.id === id ? blueprint : item)
    writeJson(BLUEPRINTS_FILE, blueprints)

    const custom = readJson(CUSTOM_AGENTS_FILE, [])
    const list = Array.isArray(custom) ? custom.filter(item => item.id !== id) : []
    list.unshift({
      id,
      name: blueprint.name,
      role: blueprint.target_type,
      description: blueprint.job_description,
      skills: blueprint.selected_skill_ids,
      workflows: blueprint.workflows,
      hooks: blueprint.hooks,
      authority_profile: blueprint.authority_profile,
      approval_policy: blueprint.approval_policy,
      risk_level: blueprint.risk_level,
      model_profile: blueprint.model_profile,
      memory_writeback_policy: blueprint.memory_writeback_policy,
      created_by: 'ascend-forge',
      created_at: blueprint.created_at,
      registered_at: now,
    })
    writeJson(CUSTOM_AGENTS_FILE, list)
    audit('blueprint_registered', { id, skills: blueprint.selected_skill_ids })
    return { ok: true, state: 'live', agent: list[0], blueprint }
  }

  execute(payload = {}) {
    const goal = String(payload.goal || payload.task || '').trim()
    if (!goal) {
      const err = new Error('goal required')
      err.status = 400
      throw err
    }
    const recommendation = this.recommendSkills({ goal, target_type: payload.target_type || 'build_agent', limit: 8 })
    const fork = loadForkManifest()
    return {
      ok: true,
      state: 'live',
      execution_mode: 'supervised_builder',
      status: 'staged_pending_approval',
      goal,
      recommendedSkills: recommendation.recommendedSkills,
      verificationGates: recommendation.verificationGates,
      policy: {
        autonomy: fork.autonomy_policy || {},
        approval_policy: DEFAULT_APPROVAL_POLICY,
      },
      next_step: 'approve generated actions or create an agent blueprint',
    }
  }
}

let instance = null

function getAscendForgeEngine() {
  if (!instance) instance = new AscendForgeEngine()
  return instance
}

module.exports = {
  getAscendForgeEngine,
  DEFAULT_APPROVAL_POLICY,
}
