import { create } from 'zustand'

export const VOICE_PHASES = Object.freeze({
  IDLE: 'idle',
  PRIMED: 'primed',
  LISTENING: 'listening',
  TRANSCRIBING: 'transcribing',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  EXECUTING: 'executing',
  INTERRUPTED: 'interrupted',
  ERROR: 'error',
})

const VALID_PHASES = new Set(Object.values(VOICE_PHASES))

export function normalizeVoicePhase(phase) {
  return VALID_PHASES.has(phase) ? phase : VOICE_PHASES.IDLE
}

export function avatarStateForVoicePhase(phase) {
  switch (normalizeVoicePhase(phase)) {
    case VOICE_PHASES.LISTENING:
      return 'listening'
    case VOICE_PHASES.TRANSCRIBING:
    case VOICE_PHASES.THINKING:
      return 'thinking'
    case VOICE_PHASES.SPEAKING:
      return 'speaking'
    case VOICE_PHASES.EXECUTING:
      return 'executing'
    case VOICE_PHASES.INTERRUPTED:
    case VOICE_PHASES.ERROR:
      return 'alert'
    case VOICE_PHASES.PRIMED:
    case VOICE_PHASES.IDLE:
    default:
      return 'idle'
  }
}

const initialState = {
  sessionId: null,
  phase: VOICE_PHASES.IDLE,
  transcript: '',
  reply: '',
  latency: null,
  error: '',
  audioLevel: 0,
  micLevel: 0,
  isSpeaking: false,
  runtime: null,
  providerStatus: 'unknown',
  lastEventAt: null,
}

export const useVoiceStore = create((set, get) => ({
  ...initialState,

  resetVoice: () => set({ ...initialState }),

  setSession: (session) => set({
    sessionId: session?.id || null,
    phase: normalizeVoicePhase(session?.phase || VOICE_PHASES.PRIMED),
    transcript: session?.transcript || '',
    reply: session?.reply || '',
    latency: session?.latency_ms ?? null,
    error: session?.error || '',
    runtime: session?.runtime || get().runtime,
    providerStatus: session?.runtime?.state || get().providerStatus,
    lastEventAt: Date.now(),
  }),

  setPhase: (phase, extra = {}) => set({
    phase: normalizeVoicePhase(phase),
    error: phase === VOICE_PHASES.ERROR ? (extra.error || get().error) : '',
    lastEventAt: Date.now(),
    ...extra,
  }),

  setTranscript: (transcript) => set({
    transcript: String(transcript || ''),
    lastEventAt: Date.now(),
  }),

  setReply: (reply, latency = null) => set({
    reply: String(reply || ''),
    latency,
    lastEventAt: Date.now(),
  }),

  setRuntime: (runtime) => set({
    runtime: runtime || null,
    providerStatus: runtime?.state || 'unknown',
    lastEventAt: Date.now(),
  }),

  setAudioLevel: (audioLevel) => set({
    audioLevel: Math.max(0, Math.min(1, Number(audioLevel) || 0)),
  }),

  setMicLevel: (micLevel) => set({
    micLevel: Math.max(0, Math.min(1, Number(micLevel) || 0)),
  }),

  setSpeaking: (isSpeaking) => set({
    isSpeaking: Boolean(isSpeaking),
    lastEventAt: Date.now(),
  }),

  setError: (error) => set({
    phase: VOICE_PHASES.ERROR,
    error: String(error || 'Voice error'),
    isSpeaking: false,
    audioLevel: 0,
    lastEventAt: Date.now(),
  }),

  interruptLocal: () => set({
    phase: VOICE_PHASES.INTERRUPTED,
    isSpeaking: false,
    audioLevel: 0,
    micLevel: 0,
    lastEventAt: Date.now(),
  }),

  applyVoiceEvent: (event) => {
    if (!event || typeof event !== 'object') return
    const type = event.type
    if (type === 'session.snapshot' && event.session) {
      get().setSession(event.session)
      return
    }
    if (type === 'session.started' && event.session) {
      get().setSession(event.session)
      if (event.runtime) get().setRuntime(event.runtime)
      return
    }
    if (type === 'voice.runtime') {
      get().setRuntime(event.runtime)
      return
    }
    if (type === 'phase') {
      get().setPhase(event.phase)
      return
    }
    if (type === 'transcript.partial' || type === 'transcript.final') {
      get().setTranscript(event.transcript || '')
      if (type === 'transcript.final') get().setPhase(VOICE_PHASES.THINKING)
      return
    }
    if (type === 'reply.final') {
      get().setReply(event.reply || '', event.latency_ms ?? null)
      return
    }
    if (type === 'interrupt') {
      get().interruptLocal()
      return
    }
    if (type === 'error') {
      get().setError(event.error)
    }
  },
}))

export default useVoiceStore
