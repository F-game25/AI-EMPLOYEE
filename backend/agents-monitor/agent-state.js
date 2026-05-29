'use strict';

/**
 * Agent State Registry
 *
 * Manages in-memory agent state with file persistence to state/agents.json.
 *
 * Methods:
 * - registerAgent(id, name) — register new agent
 * - updateAgentActivity(id, task, status) — update current task/status
 * - recordCompletion(id, duration) — record task completion
 * - recordError(id, error) — record error
 * - getAgent(id) — fetch single agent state
 * - getAllAgents() — fetch all agents
 * - getAgentsByTenant(tenantId) — fetch agents for specific tenant
 *
 * Emits events:
 * - agent-started
 * - agent-completed
 * - agent-error
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const EventEmitter = require('events');

const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'), 'state'));
const AGENTS_STATE_FILE = path.join(STATE_DIR, 'agents.json');

/**
 * Initialize state directory if it doesn't exist
 */
function ensureStateDir() {
  if (!fs.existsSync(STATE_DIR)) {
    fs.mkdirSync(STATE_DIR, { recursive: true });
  }
}

/**
 * Load agents state from file
 * Returns structure: { agents: [{...}], lastUpdated: ISO timestamp }
 */
function loadAgentState() {
  ensureStateDir();
  if (!fs.existsSync(AGENTS_STATE_FILE)) {
    return { agents: [], lastUpdated: new Date().toISOString(), _tenant_data: {} };
  }
  try {
    const data = JSON.parse(fs.readFileSync(AGENTS_STATE_FILE, 'utf8'));
    return data || { agents: [], lastUpdated: new Date().toISOString(), _tenant_data: {} };
  } catch (err) {
    console.error('[AGENT-STATE] Error loading agent state:', err.message);
    return { agents: [], lastUpdated: new Date().toISOString(), _tenant_data: {} };
  }
}

/**
 * Save agents state to file with file locking
 */
function saveAgentState(state) {
  ensureStateDir();
  try {
    fs.writeFileSync(AGENTS_STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
  } catch (err) {
    console.error('[AGENT-STATE] Error saving agent state:', err.message);
    throw err;
  }
}

/**
 * AgentStateRegistry — manages agent state lifecycle
 */
class AgentStateRegistry extends EventEmitter {
  constructor() {
    super();
    this.state = loadAgentState();
  }

  /**
   * Register a new agent
   * @param {string} id - Agent ID
   * @param {string} name - Agent display name
   * @param {string} tenantId - Tenant ID
   */
  registerAgent(id, name, tenantId = 'default') {
    ensureStateDir();
    this.state = loadAgentState(); // Reload from disk for consistency

    // Initialize tenant data structure if needed
    if (!this.state._tenant_data) {
      this.state._tenant_data = {};
    }
    if (!this.state._tenant_data[tenantId]) {
      this.state._tenant_data[tenantId] = { agents: [] };
    }

    // Check if agent already exists
    const agents = this.state._tenant_data[tenantId].agents;
    const existingIdx = agents.findIndex(a => a.id === id);

    const agent = {
      id,
      name,
      status: 'idle',
      currentTask: null,
      stats: {
        tasksCompleted: 0,
        tasksFailed: 0,
        totalDuration_ms: 0,
        averageLatency_ms: 0,
        lastActivity: new Date().toISOString(),
      },
      recentErrors: [],
      registeredAt: new Date().toISOString(),
    };

    if (existingIdx >= 0) {
      // Merge with existing (preserve stats)
      agents[existingIdx] = { ...agents[existingIdx], ...agent };
    } else {
      agents.push(agent);
    }

    this.state.lastUpdated = new Date().toISOString();
    saveAgentState(this.state);

    this.emit('agent-registered', { agentId: id, name, tenantId });
    return agent;
  }

  /**
   * Update agent activity (current task + status)
   * @param {string} id - Agent ID
   * @param {object} task - Task object {taskId, description, startTime}
   * @param {string} status - Status: idle|busy|error
   * @param {string} tenantId - Tenant ID
   */
  updateAgentActivity(id, task, status, tenantId = 'default') {
    ensureStateDir();
    this.state = loadAgentState();

    if (!this.state._tenant_data) {
      this.state._tenant_data = {};
    }
    if (!this.state._tenant_data[tenantId]) {
      this.state._tenant_data[tenantId] = { agents: [] };
    }

    const agents = this.state._tenant_data[tenantId].agents;
    const agent = agents.find(a => a.id === id);

    if (!agent) {
      console.warn(`[AGENT-STATE] Agent ${id} not registered (registering now)`);
      return this.registerAgent(id, id, tenantId);
    }

    agent.status = status;
    agent.currentTask = task;
    agent.stats.lastActivity = new Date().toISOString();

    this.state.lastUpdated = new Date().toISOString();
    saveAgentState(this.state);

    this.emit('agent-activity', { agentId: id, status, task, tenantId });
    return agent;
  }

  /**
   * Record task completion
   * @param {string} id - Agent ID
   * @param {number} duration - Duration in milliseconds
   * @param {string} tenantId - Tenant ID
   */
  recordCompletion(id, duration, tenantId = 'default') {
    ensureStateDir();
    this.state = loadAgentState();

    if (!this.state._tenant_data?.[tenantId]) {
      console.warn(`[AGENT-STATE] Tenant ${tenantId} not found`);
      return null;
    }

    const agents = this.state._tenant_data[tenantId].agents;
    const agent = agents.find(a => a.id === id);

    if (!agent) {
      console.warn(`[AGENT-STATE] Agent ${id} not found in tenant ${tenantId}`);
      return null;
    }

    agent.status = 'idle';
    agent.currentTask = null;
    agent.stats.tasksCompleted++;
    agent.stats.totalDuration_ms += duration || 0;
    agent.stats.averageLatency_ms = Math.round(
      agent.stats.totalDuration_ms / agent.stats.tasksCompleted
    );
    agent.stats.lastActivity = new Date().toISOString();

    // Keep only last 10 errors
    if (agent.recentErrors.length >= 10) {
      agent.recentErrors = agent.recentErrors.slice(-9);
    }

    this.state.lastUpdated = new Date().toISOString();
    saveAgentState(this.state);

    this.emit('agent-completed', { agentId: id, duration, stats: agent.stats, tenantId });
    return agent;
  }

  /**
   * Record error
   * @param {string} id - Agent ID
   * @param {string|object} error - Error message or Error object
   * @param {string} tenantId - Tenant ID
   */
  recordError(id, error, tenantId = 'default') {
    ensureStateDir();
    this.state = loadAgentState();

    if (!this.state._tenant_data?.[tenantId]) {
      console.warn(`[AGENT-STATE] Tenant ${tenantId} not found`);
      return null;
    }

    const agents = this.state._tenant_data[tenantId].agents;
    const agent = agents.find(a => a.id === id);

    if (!agent) {
      console.warn(`[AGENT-STATE] Agent ${id} not found in tenant ${tenantId}`);
      return null;
    }

    agent.status = 'error';
    agent.stats.tasksFailed++;
    agent.stats.lastActivity = new Date().toISOString();

    const errorRecord = {
      timestamp: new Date().toISOString(),
      error: typeof error === 'string' ? error : error?.message || String(error),
      context: {
        currentTask: agent.currentTask,
        stackTrace: error?.stack || null,
      },
    };

    agent.recentErrors.push(errorRecord);
    // Keep only last 10 errors
    if (agent.recentErrors.length > 10) {
      agent.recentErrors = agent.recentErrors.slice(-10);
    }

    this.state.lastUpdated = new Date().toISOString();
    saveAgentState(this.state);

    this.emit('agent-error', { agentId: id, error: errorRecord, tenantId });
    return agent;
  }

  /**
   * Get single agent state
   * @param {string} id - Agent ID
   * @param {string} tenantId - Tenant ID
   */
  getAgent(id, tenantId = 'default') {
    ensureStateDir();
    this.state = loadAgentState();

    if (!this.state._tenant_data?.[tenantId]) {
      return null;
    }

    const agents = this.state._tenant_data[tenantId].agents;
    return agents.find(a => a.id === id) || null;
  }

  /**
   * Get all agents for a tenant
   * @param {string} tenantId - Tenant ID
   */
  getAgentsByTenant(tenantId = 'default') {
    ensureStateDir();
    this.state = loadAgentState();

    if (!this.state._tenant_data?.[tenantId]) {
      return [];
    }

    return this.state._tenant_data[tenantId].agents || [];
  }

  /**
   * Get all agents across all tenants (admin use only)
   */
  getAllAgents() {
    ensureStateDir();
    this.state = loadAgentState();

    const all = [];
    if (this.state._tenant_data) {
      Object.values(this.state._tenant_data).forEach(tenantData => {
        if (tenantData.agents) {
          all.push(...tenantData.agents);
        }
      });
    }
    return all;
  }

  /**
   * Reset agent state (for testing or cleanup)
   */
  reset() {
    this.state = { agents: [], lastUpdated: new Date().toISOString(), _tenant_data: {} };
    saveAgentState(this.state);
  }
}

module.exports = {
  AgentStateRegistry,
  loadAgentState,
  saveAgentState,
};
