import { create } from 'zustand'
import api from '../api/client'

// Companion (Companion Gateway, MASTER_PLAN_V3 P4) front-end state.
// Mirrors the voiceStore pattern: create(set, get), explicit actions,
// avatar-state mapping helper, and async sendMessage driving window.NX.

// The avatar engine (avatar-engine.js) only supports these six render states.
// Any richer companion state must collapse onto the nearest supported one.
const ENGINE_STATES = new Set(['idle', 'listening', 'thinking', 'speaking', 'executing', 'alert'])

// Map a (possibly richer) companion avatar state onto an engine-supported one.
//   approval_needed / approval_required / warning / error → 'alert'
//   planning / monitoring / learning                      → 'thinking'
//   unknown                                               → 'idle'
export function avatarStateForCompanion(state) {
  if (ENGINE_STATES.has(state)) return state
  switch (state) {
    case 'approval_needed':
    case 'approval_required':
    case 'warning':
    case 'error':
      return 'alert'
    case 'planning':
    case 'monitoring':
    case 'learning':
      return 'thinking'
    default:
      return 'idle'
  }
}

// Push the mapped state to the avatar engine (no-op if engine not mounted).
function driveAvatar(state) {
  try { window.NX?.setState?.(avatarStateForCompanion(state)) } catch { /* engine absent */ }
}

function makeSessionId() {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return `cmp-${crypto.randomUUID()}`
  } catch { /* fall through */ }
  return `cmp-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export const useCompanionStore = create((set, get) => ({
  messages: [],
  avatarState: 'idle',
  mode: null,
  thinking: false,
  pendingApprovals: [],
  lastActions: [],
  capabilities: [],
  sessionId: makeSessionId(),

  addUserMessage: (text) => set((state) => ({
    messages: [...state.messages, { role: 'user', text: String(text || ''), ts: Date.now() }].slice(-200),
  })),

  addCompanionResponse: (resp) => {
    const reply = resp?.reply ?? ''
    const avatarState = resp?.avatar_state || 'idle'
    const approvals = Array.isArray(resp?.approvals_required) ? resp.approvals_required : []
    const actions = Array.isArray(resp?.actions) ? resp.actions : []
    set((state) => ({
      messages: [...state.messages, {
        role: 'companion',
        text: String(reply),
        ts: Date.now(),
        meta: resp?.meta || null,
      }].slice(-200),
      mode: resp?.mode ?? state.mode,
      avatarState,
      pendingApprovals: [...state.pendingApprovals, ...approvals],
      lastActions: actions,
    }))
    driveAvatar(avatarState)
  },

  setAvatarState: (avatarState) => {
    set({ avatarState })
    driveAvatar(avatarState)
  },

  setThinking: (thinking) => set({ thinking: Boolean(thinking) }),

  setCapabilities: (capabilities) => set({
    capabilities: Array.isArray(capabilities) ? capabilities : [],
  }),

  clearApprovals: () => set({ pendingApprovals: [] }),

  sendMessage: async (text, context = {}) => {
    const clean = String(text || '').trim()
    if (!clean) return
    const { addUserMessage, addCompanionResponse, setThinking } = get()
    addUserMessage(clean)
    setThinking(true)
    set({ avatarState: 'thinking' })
    driveAvatar('thinking')
    try {
      const resp = await api.post('/api/companion/message', {
        text: clean,
        session_id: get().sessionId,
        channel: 'dashboard',
        context,
      })
      addCompanionResponse(resp || {})
    } catch (err) {
      set((state) => ({
        messages: [...state.messages, {
          role: 'companion',
          text: `Companion unavailable: ${err?.message || 'request failed'}`,
          ts: Date.now(),
          meta: { error: true },
        }].slice(-200),
        avatarState: 'error',
      }))
      driveAvatar('error')
    } finally {
      setThinking(false)
    }
  },

  // Voice path: STT transcript → companion gateway (channel='voice') → spoken
  // reply. The full reply is folded into the chat panel exactly like
  // sendMessage; TTS (concise meta.voice_summary) is driven server-side, and
  // speaking/idle avatar states arrive over WS (companion:voice_response_*).
  sendVoiceTranscript: async (transcript, context = {}) => {
    const clean = String(transcript || '').trim()
    if (!clean) return null
    const { addUserMessage, addCompanionResponse, setThinking } = get()
    addUserMessage(clean)
    setThinking(true)
    set({ avatarState: 'thinking' })
    driveAvatar('thinking')
    try {
      const resp = await api.post('/api/companion/voice-message', {
        transcript: clean,
        session_id: get().sessionId,
        context,
        speak: true,
      })
      addCompanionResponse(resp || {})
      return resp
    } catch (err) {
      set((state) => ({
        messages: [...state.messages, {
          role: 'companion',
          text: `Companion voice unavailable: ${err?.message || 'request failed'}`,
          ts: Date.now(),
          meta: { error: true },
        }].slice(-200),
        avatarState: 'error',
      }))
      driveAvatar('error')
      return null
    } finally {
      setThinking(false)
    }
  },
}))

export default useCompanionStore
