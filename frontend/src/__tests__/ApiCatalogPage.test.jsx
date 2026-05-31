import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ApiCatalogPage from '../components/pages/ApiCatalogPage'

function json(data) {
  return { ok: true, headers: { get: () => 'application/json' }, json: async () => data }
}

describe('ApiCatalogPage', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async url => {
      if (String(url).includes('/api/admin/api-catalog')) {
        return json({
          ok: true,
          counts: { total: 2, node: 1, python: 1, canonical_or_compatibility: 1 },
          routes: [
            { route: '/api/tasks/run', method: 'POST', auth_required: true, source: 'node', compatibility: 'canonical_or_compatibility', response_contract: 'turn_result_v1', live_status: 'registered' },
            { route: '/api/tasks/run', method: 'POST', auth_required: true, source: 'python', compatibility: 'canonical_agent_controller', response_contract: 'agent_controller_task_result', live_status: 'unavailable' },
          ],
        })
      }
      return json({})
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders API routes with source and contract visibility', async () => {
    render(<ApiCatalogPage />)

    expect(screen.getByText(/Route Inventory/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('turn_result_v1')).toBeInTheDocument())
    expect(screen.getByText('agent_controller_task_result')).toBeInTheDocument()
  })
})
