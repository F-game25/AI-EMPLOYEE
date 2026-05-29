import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ApprovalInbox from '../components/pages/ApprovalInbox'

function json(data) {
  return { ok: true, headers: { get: () => 'application/json' }, json: async () => data }
}

describe('ApprovalInbox', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url, opts = {}) => {
      const path = String(url)
      if (path.includes('/api/approvals/inbox')) {
        return json({
          ok: true,
          counts: { pending: 1, approved: 0, rejected: 0, total: 1 },
          items: [
            {
              id: 'approval-1',
              source: 'turn_runner',
              status: 'pending',
              requested_action: 'outreach, paid_task',
              risk_level: 'high',
              source_task: 'task-1',
              turn_id: 'turn-1',
              expected_external_effect: 'May send email or deliver paid client work.',
              dry_run_preview: 'Draft the offer but wait for approval.',
              requested_by: 'user:operator',
              requested_at: '2026-05-21T10:00:00.000Z',
              proof: [{ label: 'Execution paused for human approval' }],
            },
          ],
        })
      }
      if (path.includes('/api/approvals/approval-1/approve') && opts.method === 'POST') {
        return json({
          ok: true,
          approval_id: 'approval-1',
          decision: 'approved',
          execution: {
            executed: false,
            details: 'Decision recorded. Canonical turn approvals do not auto-execute external effects yet.',
          },
        })
      }
      return json({})
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders pending approvals and records an approve decision', async () => {
    render(<ApprovalInbox />)

    await waitFor(() => expect(screen.getByText('outreach, paid_task')).toBeInTheDocument())
    expect(screen.getByText(/May send email/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Approve$/i }))
    await waitFor(() => expect(screen.getByText(/Decision recorded/i)).toBeInTheDocument())
  })
})
