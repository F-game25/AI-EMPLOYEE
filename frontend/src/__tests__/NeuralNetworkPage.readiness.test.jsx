import { act, fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NeuralNetworkPage from '../components/pages/NeuralNetworkPage'
import { useBrainStore } from '../store/brainStore'
import { useSystemStore } from '../store/systemStore'

vi.mock('../components/three/UnifiedBrain', () => ({
  default: () => <div>UnifiedBrain rendered</div>,
}))

function json(data) {
  return { ok: true, json: async () => data }
}

function setReadiness(overrides = {}) {
  useSystemStore.setState({
    readiness: {
      nodeReady: true,
      pythonReady: false,
      subsystemsReady: false,
      neuralBrainReady: false,
      graphReady: false,
      phase: 'INITIALIZING',
      degraded: true,
      degradedReasons: ['python_backend_not_ready'],
      lastChecked: Date.now(),
      ...overrides,
    },
  })
}

describe('NeuralNetworkPage readiness gating', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useBrainStore.setState({ nodes: [], links: [], stats: {}, updatedAt: null })
    setReadiness()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows initializing state and does not mount the 3D graph before graph readiness', () => {
    global.fetch = vi.fn(async () => json({
      nodeReady: true,
      pythonReady: false,
      neuralBrainReady: false,
      graphReady: false,
      phase: 'INITIALIZING',
      degraded: true,
      degradedReasons: ['python_backend_not_ready'],
    }))

    render(<NeuralNetworkPage />)

    expect(screen.getByText(/NEURAL GRAPH INITIALIZING/i)).toBeInTheDocument()
    expect(screen.queryByText(/UnifiedBrain rendered/i)).not.toBeInTheDocument()
  })

  it('normalizes malformed graph payloads without crashing', async () => {
    setReadiness({
      pythonReady: true,
      subsystemsReady: true,
      neuralBrainReady: true,
      graphReady: true,
      phase: 'READY',
      degraded: false,
      degradedReasons: [],
    })
    global.fetch = vi.fn(async url => {
      const path = String(url)
      if (path.includes('/api/brain/graph')) {
        return json({
          nodes: [{ id: 'n1' }, null, { label: 'missing-id' }],
          connections: [
            { from: 'n1', to: 'missing-id', weight: 0.8 },
            { source: 'n1', target: 'ghost', strength: 0.2 },
          ],
        })
      }
      return json({ nodes: [], links: [] })
    })

    render(<NeuralNetworkPage />)

    await waitFor(() => expect(screen.getByText(/UnifiedBrain rendered/i)).toBeInTheDocument())
    expect(screen.queryByText(/failed to render/i)).not.toBeInTheDocument()
    expect(useBrainStore.getState().nodes.length).toBeGreaterThan(0)
  })

  it('upgrades from initializing state to graph view when readiness becomes true', async () => {
    global.fetch = vi.fn(async url => {
      const path = String(url)
      if (path.includes('/api/brain/graph')) {
        return json({
          nodes: [{ id: 'ready-node', label: 'Ready Node', type: 'memory' }],
          links: [],
          stats: {},
        })
      }
      return json({ nodes: [], links: [] })
    })

    render(<NeuralNetworkPage />)
    expect(screen.getByText(/NEURAL GRAPH INITIALIZING/i)).toBeInTheDocument()

    await act(async () => {
      useSystemStore.setState({
        readiness: {
          nodeReady: true,
          pythonReady: true,
          subsystemsReady: true,
          neuralBrainReady: true,
          graphReady: true,
          phase: 'READY',
          degraded: false,
          degradedReasons: [],
          lastChecked: Date.now(),
        },
      })
    })

    await waitFor(() => expect(screen.getByText(/UnifiedBrain rendered/i)).toBeInTheDocument())
  })

  it('shows memory router observability and runs a retrieval test', async () => {
    setReadiness({
      pythonReady: true,
      subsystemsReady: true,
      neuralBrainReady: true,
      graphReady: true,
      phase: 'READY',
      degraded: false,
      degradedReasons: [],
    })
    global.fetch = vi.fn(async (url, options = {}) => {
      const path = String(url)
      if (path.includes('/api/memory/router/status')) {
        return json({
          state: 'live',
          ready: true,
          lanes: {
            semantic_rag: { state: 'live', ready: true, source: 'local_vector_store', item_count: 3 },
            knowledge_graph: { state: 'live', ready: true, source: 'native_memory_graph', backend: 'native_sqlite_graph', extension_required: false, node_count: 4, edge_count: 2 },
            structured_sql: { state: 'live', ready: true, source: 'local_sqlite', databases: [{ id: 'audit_db', name: 'audit.db', tables: [{ name: 'audit_events' }] }], readonly: true, max_rows: 100 },
            episodic_session: { state: 'live', ready: true, source: 'conversations_index', conversation_count: 2, recent_interactions: 4 },
            procedural_skills: { state: 'live', ready: true, source: 'runtime_config', skill_count: 52, agent_count: 12, workflow_count: 8, packs: ['agent_skills', 'financial_services'] },
          },
        })
      }
      if (path.includes('/api/memory/graph/status')) {
        return json({ state: 'live', ready: true, node_count: 4, edge_count: 2, source: 'native_memory_graph', backend: 'native_sqlite_graph', extension_required: false })
      }
      if (path.includes('/api/memory/sql/status')) {
        return json({ state: 'live', ready: true, readonly: true, max_rows: 100, databases: [{ id: 'audit_db', name: 'audit.db', tables: [{ name: 'audit_events' }] }] })
      }
      if (path.includes('/api/memory/procedural/status')) {
        return json({ state: 'live', ready: true, skill_count: 52, agent_count: 12, workflow_count: 8, packs: ['agent_skills'] })
      }
      if (path.includes('/api/memory/router/query')) {
        expect(options.method).toBe('POST')
        return json({
          trace_id: 'memtrace_test',
          degraded: false,
          confidence: 0.82,
          routes: [{ id: 'semantic_rag', hits: 1, reason: 'fuzzy semantic knowledge requested' }],
          context: { text: '[semantic_rag]\n- Refund policy: enterprise approval required', estimated_tokens: 12 },
          citations: [{ route: 'semantic_rag', title: 'Refund policy', source: 'policy-doc' }],
          diagnostics: [],
        })
      }
      if (path.includes('/api/brain/graph')) return json({ nodes: [], links: [], stats: {} })
      if (path.includes('/api/neural-brain/graph/snapshot')) return json({ nodes: [], links: [], stats: {} })
      return json({ graphReady: true })
    })

    render(<NeuralNetworkPage />)

    fireEvent.click(screen.getByRole('tab', { name: /Memory Router/i }))
    expect(await screen.findByText(/No retrieval test yet/i)).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText(/Ask a memory question/i), {
      target: { value: 'what is the refund policy' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Run Retrieval/i }))

    expect(await screen.findByText(/memtrace_test/i)).toBeInTheDocument()
    expect(screen.getAllByText(/semantic_rag/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Refund policy/i).length).toBeGreaterThan(0)
    expect(screen.queryByText(/failed to render/i)).not.toBeInTheDocument()
  })
})
