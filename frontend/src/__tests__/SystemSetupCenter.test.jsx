import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SystemSetupCenter from '../components/pages/SystemSetupCenter'
import { useSystemStore } from '../store/systemStore'

function json(data) {
  return { ok: true, headers: { get: () => 'application/json' }, json: async () => data }
}

describe('SystemSetupCenter', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async url => {
      const path = String(url)
      if (path.includes('/api/capabilities/status')) {
        return json({
          ok: true,
          checked_at: '2026-05-20T12:00:00.000Z',
          states: ['live', 'dry_run', 'mock', 'fallback', 'not_configured', 'unavailable', 'error'],
          counts: { live: 1, not_configured: 1 },
          next_recommended_action: {
            capability_id: 'python_backend',
            label: 'Python Backend',
            setup_action: 'start_service',
            details: 'Python did not respond.',
          },
          capabilities: [
            {
              id: 'node_backend',
              name: 'node_backend',
              label: 'Node Backend',
              status: 'live',
              category: 'runtime',
              setup_action: 'test',
              details: 'Gateway is running.',
            },
            {
              id: 'python_backend',
              name: 'python_backend',
              label: 'Python Backend',
              status: 'not_configured',
              category: 'runtime',
              setup_action: 'start_service',
              details: 'Python did not respond.',
              missing_env: [],
            },
          ],
        })
      }
      return json({})
    })
    useSystemStore.setState({
      capabilityStatus: {
        ok: false,
        capabilities: [],
        states: [],
        counts: {},
        next_recommended_action: null,
        loading: false,
        error: null,
        lastChecked: 0,
      },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders technical setup status and user readiness', async () => {
    render(<SystemSetupCenter />)

    expect(screen.getByText(/Technical Admin Readiness/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('Python Backend').length).toBeGreaterThan(0))
    expect(screen.getByText(/After technical setup/i)).toBeInTheDocument()
    expect(screen.getByText(/Owner \/ Founder/i)).toBeInTheDocument()
    expect(screen.getByText(/Needs action/i)).toBeInTheDocument()
  })
})
