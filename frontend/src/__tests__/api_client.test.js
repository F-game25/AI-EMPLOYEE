import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// api/client uses import.meta.env — mock it before importing
vi.stubGlobal('import', { meta: { env: { VITE_API_BASE: '' } } })

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

// Isolate sessionStorage between tests
beforeEach(() => sessionStorage.clear())
afterEach(() => vi.resetAllMocks())

// Dynamic import after globals are set
const { default: api } = await import('../api/client.js')

describe('API client', () => {
  it('sends POST with JSON body', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ ok: true, reply: 'hello' }),
    })
    const result = await api.chat.send('hello world')
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/chat',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: 'hello world', model: undefined }),
      })
    )
    expect(result.ok).toBe(true)
  })

  it('attaches Authorization header when JWT is stored', async () => {
    sessionStorage.setItem('ai_jwt', 'test-token-123')
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ ok: true }),
    })
    await api.system.status()
    const [, opts] = mockFetch.mock.calls[0]
    expect(opts.headers['Authorization']).toBe('Bearer test-token-123')
  })

  it('throws with status on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: () => Promise.resolve('{"error":"Unauthorized"}'),
    })
    await expect(api.audit.events()).rejects.toMatchObject({ status: 401 })
  })
})
