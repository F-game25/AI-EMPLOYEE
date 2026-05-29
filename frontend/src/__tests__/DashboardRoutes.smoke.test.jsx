import { render, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../components/Dashboard'
import { useSystemStore } from '../store/systemStore'

const ROUTE_GROUPS = {
  core: ['dashboard', 'nexus', 'cognition', 'agents', 'memory', 'economy'],
  operations: ['tasks', 'workflows', 'infrastructure', 'deployments', 'workspace', 'operations'],
  intelligence: ['neural-graph', 'knowledge', 'trends', 'research', 'recon', 'intelligence', 'ascend-forge'],
  security: ['policies', 'permissions', 'sandboxes', 'audit', 'security', 'approvals', 'proof'],
  system: ['setup', 'integrations', 'models', 'runtime', 'api-catalog', 'user-views', 'perspectives', 'settings', 'system'],
}

const ALL_ROUTES = [
  'dashboard', 'nexus', 'cognition', 'agents', 'memory', 'economy',
  'tasks', 'workflows', 'infrastructure', 'deployments',
  'neural-graph', 'knowledge', 'trends', 'research', 'recon',
  'policies', 'permissions', 'sandboxes', 'audit', 'security', 'approvals', 'proof',
  'setup', 'integrations', 'models', 'runtime', 'api-catalog', 'user-views', 'perspectives', 'settings',
  'workspace', 'operations', 'intelligence', 'ascend-forge', 'system',
]

function selectedRoutes() {
  const explicit = process.env.DASHBOARD_ROUTES
  if (explicit) return explicit.split(',').map(route => route.trim()).filter(Boolean)
  const group = process.env.DASHBOARD_ROUTE_GROUP
  if (group) return ROUTE_GROUPS[group] || []
  return ALL_ROUTES
}

function mockFetch() {
  global.fetch = vi.fn(async url => {
    const path = String(url)
    if (path.includes('/api/mode')) return json({ mode: 'BALANCED' })
    if (path.includes('/api/product/dashboard')) return json({ workflow_runs: [], learning: {} })
    if (path.includes('/api/capabilities/status')) return json({
      ok: true,
      states: ['live', 'dry_run', 'mock', 'fallback', 'not_configured', 'unavailable', 'error'],
      counts: { live: 1, not_configured: 1 },
      capabilities: [
        { id: 'node_backend', name: 'node_backend', label: 'Node Backend', status: 'live', category: 'runtime', setup_action: 'test' },
        { id: 'python_backend', name: 'python_backend', label: 'Python Backend', status: 'not_configured', category: 'runtime', setup_action: 'start_service' },
      ],
    })
    if (path.includes('/api/proof/center')) return json({
      ok: true,
      proof_items: [],
      artifacts: [],
      turns: [],
      counts: {},
    })
    if (path.includes('/api/approvals/inbox')) return json({
      ok: true,
      counts: { pending: 0, approved: 0, rejected: 0, total: 0 },
      items: [],
    })
    if (path.includes('/api/admin/api-catalog')) return json({
      ok: true,
      counts: { total: 1, node: 1, python: 0 },
      routes: [
        { route: '/api/tasks/run', method: 'POST', auth_required: true, source: 'node', compatibility: 'canonical_or_compatibility', response_contract: 'turn_result_v1', live_status: 'registered' },
      ],
    })
    if (path.includes('/api/readiness')) return json({
      nodeReady: true,
      pythonReady: false,
      subsystemsReady: false,
      neuralBrainReady: false,
      graphReady: false,
      phase: 'INITIALIZING',
      degraded: true,
      degradedReasons: ['python_backend_not_ready'],
    })
    if (path.includes('/api/agents/list')) return json({ agents: [] })
    if (path.includes('/api/neural-brain/threads')) return json({ threads: [] })
    if (path.includes('/api/neural-brain/memory/status')) return json({ ok: false })
    if (path.includes('/api/neural-brain/graph/snapshot')) return json({ nodes: [], links: [] })
    if (path.includes('/api/blacklight/tools')) return json({ tools: [], categories: {}, summary: {} })
    if (path.includes('/api/recon/tools')) return json({ tools: [], categories: {}, summary: {}, policy: {} })
    if (path.includes('/api/recon/cases')) return json({ cases: [] })
    if (path.includes('/api/recon/findings')) return json({ findings: [] })
    if (path.includes('/api/recon/audit')) return json({ audit: [] })
    return json({})
  })
}

function json(data) {
  return { ok: true, headers: { get: () => 'application/json' }, json: async () => data }
}

beforeEach(() => {
  mockFetch()
  window.matchMedia = window.matchMedia || vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  useSystemStore.setState({
    activeSection: 'dashboard',
    wsConnected: true,
    systemStatus: { cpu: 12, memory: 24, mode: 'BALANCED', uptime: 1234 },
    systemHealth: { cpu_percent: 12, memory_percent: 24, gpu_percent: 6, status: 'ok' },
    backendStatus: { node_ok: true, ws_connected: true, python_ok: true, llm_ok: true, last_seen: Date.now() },
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Dashboard routes', () => {
  const routes = selectedRoutes()

  it('has routes selected for smoke coverage', () => {
    expect(routes.length).toBeGreaterThan(0)
  })

  it.each(routes)('mounts /%s without crashing', async route => {
    const { container } = render(
      <MemoryRouter initialEntries={[`/${route}`]}>
        <Dashboard />
      </MemoryRouter>
    )

    await waitFor(() => expect(container.querySelector('.nx-sidebar')).toBeInTheDocument())
    expect(container.textContent).not.toMatch(/failed to render/i)
  })
})
