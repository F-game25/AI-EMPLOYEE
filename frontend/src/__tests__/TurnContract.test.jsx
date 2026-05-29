import { beforeEach, describe, expect, it } from 'vitest'
import { useTaskStore } from '../store/taskStore'
import { useSystemStore } from '../store/systemStore'

describe('canonical turn contract store behavior', () => {
  beforeEach(() => {
    useTaskStore.setState({
      chatMessages: [],
      lastAiMessageIndex: -1,
      isTyping: false,
      executionSteps: [],
      executionLogs: [],
      workflowState: { active_run: null, runs: [] },
    })
    useSystemStore.setState({
      capabilityStatus: {
        ok: false,
        capabilities: [],
        states: ['live', 'dry_run', 'mock', 'fallback', 'not_configured', 'unavailable'],
        lastChecked: 0,
        loading: false,
        error: null,
      },
    })
  })

  it('merges duplicate assistant updates by turn_id', () => {
    const first = {
      turn_id: 'turn-1',
      task_id: 'task-1',
      status: 'running',
      assistant_reply: 'Working...',
      actions: [{ action: 'memory_context', status: 'completed' }],
    }
    const final = {
      turn_id: 'turn-1',
      task_id: 'task-1',
      status: 'completed',
      assistant_reply: 'I understood: test\n\nResult: done\n\nProof: file',
      proof: [{ type: 'file', label: 'result.md', path: '/tmp/result.md' }],
      artifacts: [{ name: 'result.md', url: '/api/artifacts/result.md' }],
    }

    useTaskStore.getState().upsertTurnMessage(first)
    useTaskStore.getState().upsertTurnMessage(final)

    const messages = useTaskStore.getState().chatMessages
    expect(messages).toHaveLength(1)
    expect(messages[0].turn_id).toBe('turn-1')
    expect(messages[0].status).toBe('completed')
    expect(messages[0].content).toContain('I understood')
    expect(messages[0].proof[0].label).toBe('result.md')
    expect(messages[0].artifacts[0].url).toBe('/api/artifacts/result.md')
  })

  it('keeps legacy non-turn messages append-only', () => {
    useTaskStore.getState().addChatMessage({ role: 'ai', content: 'one' })
    useTaskStore.getState().addChatMessage({ role: 'ai', content: 'two' })

    const messages = useTaskStore.getState().chatMessages
    expect(messages).toHaveLength(2)
    expect(messages.map(message => message.content)).toEqual(['one', 'two'])
  })

  it('stores capability registry status for dashboard visibility', async () => {
    const originalFetch = globalThis.fetch
    globalThis.fetch = async () => new Response(JSON.stringify({
      ok: true,
      states: ['live', 'dry_run', 'not_configured'],
      capabilities: [
        { name: 'python_backend', status: 'live', required_env: [], missing_env: [] },
        { name: 'anthropic_llm', status: 'not_configured', required_env: ['ANTHROPIC_API_KEY'], missing_env: ['ANTHROPIC_API_KEY'] },
      ],
    }), { status: 200, headers: { 'content-type': 'application/json' } })

    try {
      const capabilities = await useSystemStore.getState().fetchCapabilityStatus()
      const status = useSystemStore.getState().capabilityStatus

      expect(capabilities).toHaveLength(2)
      expect(status.ok).toBe(true)
      expect(status.loading).toBe(false)
      expect(status.capabilities[0].status).toBe('live')
      expect(status.capabilities[1].missing_env).toEqual(['ANTHROPIC_API_KEY'])
    } finally {
      globalThis.fetch = originalFetch
    }
  })
})
