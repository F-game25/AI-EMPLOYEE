import { render, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../components/Dashboard'
import { useSystemStore } from '../store/systemStore'

const ROUTES = [
  'dashboard', 'nexus', 'cognition', 'agents', 'memory', 'economy',
  'tasks', 'workflows', 'infrastructure', 'deployments',
  'neural-graph', 'knowledge', 'trends', 'research', 'recon',
  'policies', 'permissions', 'sandboxes', 'audit', 'security',
  'integrations', 'models', 'runtime', 'settings',
  'workspace', 'operations', 'intelligence', 'ascend-forge', 'system',
]

function mockFetch() {
  global.fetch = vi.fn(async url => {
    const path = String(url)
    if (path.includes('/api/mode')) return json({ mode: 'BALANCED' })
    if (path.includes('/api/product/dashboard')) return json({ workflow_runs: [], learning: {} })
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
  it.each(ROUTES)('mounts /%s without crashing', async route => {
    const { container } = render(
      <MemoryRouter initialEntries={[`/${route}`]}>
        <Dashboard />
      </MemoryRouter>
    )

    await waitFor(() => expect(container.querySelector('.nx-sidebar')).toBeInTheDocument())
    expect(container.textContent).not.toMatch(/failed to render/i)
  })
})
