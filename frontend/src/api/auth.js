// Single source of truth for the local operator token.
//
// On localhost the backend issues a JWT from GET /api/auth/auto-token with NO
// secret required (the endpoint gates on the raw socket address). Every caller
// — boot menu, boot sequence, app bootstrap, the API client's 401 refresh, and
// the login fallback — funnels through ensureOperatorToken() so a single
// in-flight request is shared. That prevents redundant boot-time fetches from
// tripping the endpoint's 10/min rate limit and falsely stranding the operator
// on the manual-secret screen.

const BASE = import.meta.env.VITE_API_BASE ?? ''
let inFlight = null

export function getStoredToken() {
  return localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || null
}

export function storeToken(token) {
  if (!token) return
  // localStorage survives restarts; sessionStorage is read by useWebSocket.js
  // and the main.jsx fetch interceptor — keep both in sync.
  localStorage.setItem('ai_jwt', token)
  sessionStorage.setItem('ai_jwt', token)
}

export function clearToken() {
  localStorage.removeItem('ai_jwt')
  sessionStorage.removeItem('ai_jwt')
}

// Resolve a usable operator token: reuse the stored one unless `force`, else
// fetch the localhost auto-token. Concurrent callers share one request.
// Resolves to the token string, or null when auto-token is unavailable
// (e.g. accessed from a non-localhost address — then a secret is required).
export function ensureOperatorToken({ force = false, timeoutMs = 5000 } = {}) {
  if (!force) {
    const existing = getStoredToken()
    if (existing) return Promise.resolve(existing)
  }
  if (inFlight) return inFlight
  inFlight = fetch(`${BASE}/api/auth/auto-token`, { signal: AbortSignal.timeout(timeoutMs) })
    .then(r => (r.ok ? r.json() : null))
    .then(d => {
      const token = d?.token || d?.access_token || null
      if (token) {
        storeToken(token)
        try { window.dispatchEvent(new CustomEvent('nx:auth-ready')) } catch { /* best effort */ }
      }
      return token
    })
    .catch(() => null)
    .finally(() => { inFlight = null })
  return inFlight
}
