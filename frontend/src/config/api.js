// Derive the API base from whatever host/port the page was loaded from.
// In development (Vite dev server on :5173) the Vite proxy forwards /api and
// /ws to the backend, so relative paths work transparently.
// In production (built static files served by the backend on :8787) the
// origin is the backend itself, so relative paths also resolve correctly.
// This replaces the old hardcoded 'http://127.0.0.1:8787' which broke when
// the backend was accessed from a different host (LAN, Docker, WSL, etc.).
export const API_URL = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8787'

export const WS_URL = typeof window !== 'undefined'
  ? (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws'
  : 'ws://127.0.0.1:8787/ws'
