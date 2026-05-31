import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProofCenter from '../components/pages/ProofCenter'

function json(data) {
  return { ok: true, headers: { get: () => 'application/json' }, json: async () => data }
}

describe('ProofCenter', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async url => {
      if (String(url).includes('/api/proof/center')) {
        return json({
          ok: true,
          proof_items: [
            {
              id: 'proof-1',
              name: 'Memory context checked',
              type: 'memory_trace',
              status: 'live',
              source: 'turn',
              turn_id: 'turn-1',
              task_id: 'task-1',
              created_at: '2026-05-20T12:00:00.000Z',
            },
          ],
          artifacts: [
            {
              id: 'artifact:result.md',
              name: 'result.md',
              type: 'file',
              status: 'available',
              source: 'artifact_storage',
              url: '/api/artifacts/result.md',
              created_at: '2026-05-20T12:00:00.000Z',
            },
          ],
          turns: [
            {
              turn_id: 'turn-1',
              task_id: 'task-1',
              status: 'completed',
              source: 'agent_controller',
              proof_count: 1,
              artifact_count: 1,
            },
          ],
        })
      }
      return json({})
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders proof items, artifacts, and recent turns', async () => {
    render(<ProofCenter />)

    expect(screen.getByText(/Execution Evidence/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Memory context checked')).toBeInTheDocument())
    expect(screen.getByText('result.md')).toBeInTheDocument()
    expect(screen.getByText('turn-1')).toBeInTheDocument()
  })
})
