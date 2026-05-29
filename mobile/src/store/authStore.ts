import { create } from 'zustand'
import { api, ws, getServerUrl } from '../api/secureClient'

interface User {
  id:        string
  email:     string
  role:      string
  tenant_id: string
}

interface AuthState {
  user:         User | null
  isLoading:    boolean
  error:        string | null
  wsConnected:  boolean
  serverUrl:    string | null

  login:        (email: string, password: string) => Promise<void>
  logout:       () => Promise<void>
  checkAuth:    () => Promise<void>
  setWsState:   (connected: boolean) => void
  clearError:   () => void
}

function resolveUser(payload: { user?: User } | User | null): User | null {
  if (!payload) return null
  if ('id' in payload) return payload
  return payload.user || null
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user:        null,
  isLoading:   false,
  error:       null,
  wsConnected: false,
  serverUrl:   null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const result = await api.login(email, password)
      set({ user: result.user, isLoading: false, error: null })
      ws.connect()
    } catch (e: unknown) {
      set({ isLoading: false, error: (e as { message?: string }).message || 'Login failed' })
    }
  },

  logout: async () => {
    ws.disconnect()
    await api.logout()
    set({ user: null, wsConnected: false })
  },

  checkAuth: async () => {
    set({ isLoading: true })
    try {
      const [authenticated, serverUrl] = await Promise.all([
        api.isAuthenticated(),
        getServerUrl(),
      ])
      if (authenticated) {
        const me = await api.get('/api/auth/me').catch(() => null) as { user?: User } | User | null
        const user = resolveUser(me)
        if (user?.id) {
          set({ isLoading: false, user, serverUrl })
          ws.connect()
          return
        }
      }
      set({ isLoading: false, user: null, serverUrl })
    } catch {
      set({ isLoading: false, user: null })
    }
  },

  setWsState: (connected) => set({ wsConnected: connected }),
  clearError:  () => set({ error: null }),
}))
