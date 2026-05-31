import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskComposer, { MONEY_PRESETS } from '../components/core/TaskComposer'
import { useTaskStore } from '../store/taskStore'

const apiMock = vi.hoisted(() => ({
  post: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: apiMock,
}))

describe('TaskComposer', () => {
  beforeEach(() => {
    apiMock.post.mockReset()
    useTaskStore.setState({
      chatMessages: [],
      lastAiMessageIndex: -1,
      isTyping: false,
      executionSteps: [],
      executionLogs: [],
      workflowState: { active_run: null, runs: [] },
    })
  })

  it('submits through the canonical task route and stores the turn', async () => {
    apiMock.post.mockResolvedValue({
      turn_id: 'turn-compose',
      task_id: 'task-compose',
      status: 'completed',
      assistant_reply: 'I understood: test\n\nResult: done\n\nProof: local trace',
      proof: [{ type: 'trace', label: 'local trace' }],
      actions: [{ action: 'real_execution_engine', status: 'completed' }],
    })

    render(<TaskComposer />)

    fireEvent.change(screen.getByPlaceholderText('Describe the result you want...'), {
      target: { value: 'summarize current system status' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'RUN' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(
      '/api/tasks/run',
      expect.objectContaining({
        task: expect.stringContaining('summarize current system status'),
      }),
    ))

    await waitFor(() => {
      const messages = useTaskStore.getState().chatMessages
      expect(messages).toHaveLength(2)
      expect(messages[0].role).toBe('user')
      expect(messages[1].turn_id).toBe('turn-compose')
      expect(messages[1].proof[0].label).toBe('local trace')
    })
  })

  it('uses Money Mode presets without executing risky actions directly', async () => {
    apiMock.post.mockResolvedValue({
      turn_id: 'turn-money',
      task_id: 'task-money',
      status: 'waiting_approval',
      assistant_reply: 'I paused before taking external or money-related action.',
      approvals: [{ status: 'required', required_for: ['outreach'] }],
    })

    render(<TaskComposer presets={MONEY_PRESETS} placeholder="Money goal" />)

    fireEvent.click(screen.getByRole('button', { name: 'Draft Offer' }))
    fireEvent.change(screen.getByPlaceholderText('Money goal'), {
      target: { value: 'create a client offer' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'RUN' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    const submitted = apiMock.post.mock.calls[0][1].task
    expect(submitted).toContain('Keep this as a draft until approved')
    expect(submitted).toContain('create a client offer')
  })
})
