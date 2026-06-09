import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../../api/client'
import { setVoiceAnalyser } from '../../hooks/useVoiceLipSync'
import { VOICE_PHASES, useVoiceStore } from '../../store/voiceStore'
import './VoiceModal.css'

const GENDERS = ['NEUTRAL', 'MALE', 'FEMALE']
const TONES = ['CALM', 'PROFESSIONAL', 'WARM', 'AUTHORITATIVE']
const EMOTIONS = ['warm_confident', 'calm', 'focused', 'curious', 'concerned', 'firm', 'urgent', 'subtle_excited']
const PRESETS = [
  { id: 'analyst', label: 'ANALYST', gender: 'NEUTRAL', tone: 'PROFESSIONAL' },
  { id: 'concierge', label: 'CONCIERGE', gender: 'FEMALE', tone: 'WARM' },
  { id: 'sentinel', label: 'SENTINEL', gender: 'MALE', tone: 'AUTHORITATIVE' },
]

function voiceStatusLabel(runtime, providerStatus) {
  const voiceCore = runtime?.tts?.voice_core_local
  const voiceLite = runtime?.tts?.voice_lite
  const tts = voiceCore
    ? `default:${voiceCore.state || runtime?.tts?.state || 'unknown'}`
    : voiceLite
    ? `voice_lite:${voiceLite.state || runtime?.tts?.state || 'unknown'}`
    : runtime?.tts?.state || providerStatus || 'unknown'
  const stt = runtime?.stt?.state || 'browser'
  const vad = runtime?.vad?.state || 'unknown'
  return `tts:${tts} / stt:${stt} / vad:${vad}`
}

function detectReplyLanguage(text) {
  const value = ` ${String(text || '').toLowerCase()} `
  const hits = [' de ', ' het ', ' een ', ' niet ', ' hoe ', ' kunnen ', ' systeem ', ' stem ', ' waarom ', ' aanpakken ']
    .filter(word => value.includes(word)).length
  return hits >= 2 ? 'nl' : 'en'
}

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value) || 0))
}

function voiceGenderFromLabel(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'male' || normalized === 'masculine') return 'male'
  if (normalized === 'female' || normalized === 'feminine') return 'female'
  return 'female'
}

function genderLabelFromConfig(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'male' || normalized === 'masculine') return 'MALE'
  if (normalized === 'female' || normalized === 'feminine') return 'FEMALE'
  return 'NEUTRAL'
}

function chooseRecorderMimeType() {
  if (!window.MediaRecorder?.isTypeSupported) return ''
  return [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ].find(type => window.MediaRecorder.isTypeSupported(type)) || ''
}

function linearResample(samples, sourceRate, targetRate) {
  if (sourceRate === targetRate) return samples
  const ratio = sourceRate / targetRate
  const length = Math.max(1, Math.round(samples.length / ratio))
  const output = new Float32Array(length)
  for (let i = 0; i < length; i++) {
    const sourceIndex = i * ratio
    const left = Math.floor(sourceIndex)
    const right = Math.min(samples.length - 1, left + 1)
    const weight = sourceIndex - left
    output[i] = samples[left] * (1 - weight) + samples[right] * weight
  }
  return output
}

function encodePcm16Wav(samples, sampleRate) {
  const bytesPerSample = 2
  const blockAlign = bytesPerSample
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample)
  const view = new DataView(buffer)
  const writeString = (offset, value) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * bytesPerSample, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * bytesPerSample, true)
  let offset = 44
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

async function encodeBlobToWav(blob, targetRate = 16000) {
  if (!blob?.size) throw new Error('Recorded audio is empty.')
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext
  if (!AudioContextCtor) throw new Error('Browser AudioContext is not available for WAV encoding.')
  const decoder = new AudioContextCtor()
  let decoded
  try {
    decoded = await decoder.decodeAudioData(await blob.arrayBuffer())
  } finally {
    try { await decoder.close?.() } catch { /* ignore */ }
  }

  const channels = Math.max(1, decoded.numberOfChannels || 1)
  const mono = new Float32Array(decoded.length)
  for (let channel = 0; channel < channels; channel++) {
    const data = decoded.getChannelData(channel)
    for (let i = 0; i < mono.length; i++) mono[i] += data[i] / channels
  }

  let samples = mono
  let sampleRate = decoded.sampleRate
  const OfflineContext = window.OfflineAudioContext || window.webkitOfflineAudioContext
  if (sampleRate !== targetRate && OfflineContext) {
    const frameCount = Math.max(1, Math.ceil(mono.length * targetRate / sampleRate))
    const offline = new OfflineContext(1, frameCount, targetRate)
    const buffer = offline.createBuffer(1, mono.length, sampleRate)
    buffer.copyToChannel(mono, 0)
    const source = offline.createBufferSource()
    source.buffer = buffer
    source.connect(offline.destination)
    source.start(0)
    const rendered = await offline.startRendering()
    samples = rendered.getChannelData(0)
    sampleRate = targetRate
  } else if (sampleRate !== targetRate) {
    samples = linearResample(mono, sampleRate, targetRate)
    sampleRate = targetRate
  }

  return encodePcm16Wav(samples, sampleRate)
}

export default function VoiceModal() {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('persona')
  const [gender, setGender] = useState('FEMALE')
  const [tone, setTone] = useState('PROFESSIONAL')
  const [userName, setUserName] = useState('Lars')
  const [userRank, setUserRank] = useState('Chief')
  const [provider, setProvider] = useState('voice_core_local')
  const [emotion, setEmotion] = useState('warm_confident')
  const [emotionIntensity, setEmotionIntensity] = useState(0.35)
  const [voiceLanguage, setVoiceLanguage] = useState('auto')
  const [voiceCoreSettings, setVoiceCoreSettings] = useState({
    voice: 'female',
    gender: 'female',
    threads: 4,
    timeoutMs: 30000,
    localFallback: false,
  })
  const [voiceLiteSettings, setVoiceLiteSettings] = useState({
    voice: 'base',
    threads: 4,
    timeoutMs: 30000,
    localFallback: true,
  })
  const [fishSettings, setFishSettings] = useState({
    enabled: true,
    baseUrl: 'http://127.0.0.1:8080',
    referenceId: '',
    temperature: 0.8,
    topP: 0.8,
    repetitionPenalty: 1.1,
    chunkLength: 200,
    maxNewTokens: 1024,
    seed: '',
    localFallback: true,
  })
  const [recording, setRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [sending, setSending] = useState(false)
  const [aiResponse, setAiResponse] = useState('')
  const [status, setStatus] = useState({ connected: false, backend: 'unknown', detail: '' })
  const [saving, setSaving] = useState(false)
  const [playback, setPlayback] = useState('')
  const [lastArtifact, setLastArtifact] = useState(null)
  const [runtimeStatus, setRuntimeStatus] = useState(null)
  const [recordingMode, setRecordingMode] = useState('idle')

  const voiceSessionId = useVoiceStore(state => state.sessionId)
  const voicePhase = useVoiceStore(state => state.phase)
  const voiceRuntime = useVoiceStore(state => state.runtime)
  const providerStatus = useVoiceStore(state => state.providerStatus)
  const voiceLatency = useVoiceStore(state => state.latency)
  const micLevel = useVoiceStore(state => state.micLevel)
  const applyVoiceEvent = useVoiceStore(state => state.applyVoiceEvent)
  const setVoiceSession = useVoiceStore(state => state.setSession)
  const setVoicePhase = useVoiceStore(state => state.setPhase)
  const setVoiceTranscript = useVoiceStore(state => state.setTranscript)
  const setVoiceReply = useVoiceStore(state => state.setReply)
  const setVoiceRuntime = useVoiceStore(state => state.setRuntime)
  const setVoiceAudioLevel = useVoiceStore(state => state.setAudioLevel)
  const setVoiceMicLevel = useVoiceStore(state => state.setMicLevel)
  const setVoiceSpeaking = useVoiceStore(state => state.setSpeaking)
  const setVoiceError = useVoiceStore(state => state.setError)
  const interruptLocal = useVoiceStore(state => state.interruptLocal)

  const recogRef = useRef(null)
  const transcriptRef = useRef('')
  const audioRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const recordChunksRef = useRef([])
  const cancelRecordingRef = useRef(false)
  const playReplyRef = useRef(null)
  const audioCtxRef = useRef(null)
  const audioSourceRef = useRef(null)
  const audioRafRef = useRef(0)
  const micStreamRef = useRef(null)
  const micSourceRef = useRef(null)
  const micRafRef = useRef(0)

  const getAudioContext = useCallback(async () => {
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext
    if (!AudioContextCtor) return null
    if (!audioCtxRef.current) audioCtxRef.current = new AudioContextCtor()
    if (audioCtxRef.current.state === 'suspended') await audioCtxRef.current.resume()
    return audioCtxRef.current
  }, [])

  const stopMicLevel = useCallback(() => {
    if (micRafRef.current) cancelAnimationFrame(micRafRef.current)
    micRafRef.current = 0
    try { micSourceRef.current?.disconnect() } catch { /* ignore */ }
    micSourceRef.current = null
    for (const track of micStreamRef.current?.getTracks?.() || []) track.stop()
    micStreamRef.current = null
    setVoiceMicLevel(0)
  }, [setVoiceMicLevel])

  const startMicLevel = useCallback(async (providedStream = null) => {
    if (!navigator.mediaDevices?.getUserMedia) return
    stopMicLevel()
    try {
      const stream = providedStream || await navigator.mediaDevices.getUserMedia({ audio: true })
      const ctx = await getAudioContext()
      if (!ctx) {
        micStreamRef.current = stream
        return
      }
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 64
      source.connect(analyser)
      micStreamRef.current = stream
      micSourceRef.current = source
      const buf = new Uint8Array(analyser.fftSize)
      const tick = () => {
        analyser.getByteTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) {
          const centered = (buf[i] - 128) / 128
          sum += centered * centered
        }
        setVoiceMicLevel(clamp01(Math.sqrt(sum / buf.length) * 3.5))
        micRafRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch (e) {
      setPlayback(`mic level unavailable: ${e.message}`)
    }
  }, [getAudioContext, setVoiceMicLevel, stopMicLevel])

  const cleanupAudioAnalyser = useCallback(() => {
    if (audioRafRef.current) cancelAnimationFrame(audioRafRef.current)
    audioRafRef.current = 0
    setVoiceAnalyser(null)
    setVoiceAudioLevel(0)
    try { audioSourceRef.current?.disconnect() } catch { /* ignore */ }
    audioSourceRef.current = null
  }, [setVoiceAudioLevel])

  const stopAudioPlayback = useCallback(() => {
    cleanupAudioAnalyser()
    if (audioRef.current) {
      try { audioRef.current.pause() } catch { /* ignore */ }
      if (audioRef.current.src?.startsWith('blob:')) URL.revokeObjectURL(audioRef.current.src)
      audioRef.current = null
    }
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    setVoiceSpeaking(false)
  }, [cleanupAudioAnalyser, setVoiceSpeaking])

  const attachPlaybackAnalyser = useCallback(async (audio) => {
    const ctx = await getAudioContext()
    if (!ctx) return null
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 128
    analyser.smoothingTimeConstant = 0.72
    const source = ctx.createMediaElementSource(audio)
    source.connect(analyser)
    analyser.connect(ctx.destination)
    audioSourceRef.current = source
    setVoiceAnalyser(analyser)

    const buf = new Uint8Array(analyser.frequencyBinCount)
    const tick = () => {
      analyser.getByteFrequencyData(buf)
      let sum = 0
      for (let i = 0; i < buf.length; i++) sum += buf[i]
      setVoiceAudioLevel(clamp01((sum / Math.max(1, buf.length)) / 140))
      audioRafRef.current = requestAnimationFrame(tick)
    }
    tick()
    return analyser
  }, [getAudioContext, setVoiceAudioLevel])

  const ensureSession = useCallback(async () => {
    const current = useVoiceStore.getState().sessionId
    if (current) return current
    const data = await api.voice.createSession({ source: 'voice_modal' })
    if (data.runtime) setVoiceRuntime(data.runtime)
    if (data.session) {
      setVoiceSession(data.session)
      return data.session.id
    }
    throw new Error('Voice session did not start.')
  }, [setVoiceRuntime, setVoiceSession])

  const refreshStatus = useCallback(async () => {
    try {
      const data = await api.voice.config()
      const runtime = await api.voice.runtime().catch(() => data.runtime || null)
      const cfg = data.config || {}
      const identity = cfg.identity || {}
      const fish = cfg.fishSpeech || {}
      const voiceCore = cfg.voiceCore || {}
      const voiceLite = cfg.voiceLite || {}
      const configuredProvider = cfg.provider === 'voice_core_local'
        ? 'voice_core_local'
        : cfg.provider === 'voice_lite'
        ? 'voice_lite_base'
        : (cfg.provider || 'voice_core_local')
      setProvider(configuredProvider)
      setUserName(identity.userName || 'Lars')
      setUserRank(identity.rank || 'Chief')
      setGender(genderLabelFromConfig(voiceCore.gender || voiceCore.voice || identity.voiceGender || 'female'))
      setVoiceLanguage(voiceCore.language || voiceLite.language || 'auto')
      setEmotion(voiceCore.emotion || 'warm_confident')
      setEmotionIntensity(Number(voiceCore.emotionIntensity ?? 0.35))
      setVoiceCoreSettings(prev => ({ ...prev, ...voiceCore }))
      setVoiceLiteSettings(prev => ({ ...prev, ...voiceLite }))
      setFishSettings(prev => ({ ...prev, ...fish, seed: fish.seed ?? '' }))
      if (runtime) {
        setRuntimeStatus(runtime)
        setVoiceRuntime(runtime)
      }
      const voiceCoreState = runtime?.tts?.voice_core_local?.state || 'unknown'
      const voiceLiteState = runtime?.tts?.voice_lite?.state || 'unknown'
      const fishStatus = runtime?.tts?.fish_speech?.state || data.fish_speech?.status || 'unknown'
      setStatus({
        connected: true,
        backend: cfg.provider === 'fish_speech'
          ? `fish: ${fishStatus}`
          : cfg.provider === 'local'
            ? 'browser/os fallback'
            : cfg.provider === 'voice_lite'
              ? `voice lite: ${voiceLiteState}`
              : `default voice: ${voiceCoreState}`,
        detail: runtime?.recommendation?.details || data.fish_speech?.last_error || data.fish_speech?.endpoint || '',
      })
    } catch (e) {
      setStatus({ connected: false, backend: 'offline', detail: e.message })
      setVoiceError(e.message)
    }
  }, [setVoiceError, setVoiceRuntime])

  useEffect(() => {
    const openHandler = () => setOpen(true)
    window.addEventListener('nx:voice-open', openHandler)
    return () => window.removeEventListener('nx:voice-open', openHandler)
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    ;(async () => {
      await refreshStatus()
      if (!cancelled) await ensureSession().catch(e => setVoiceError(e.message))
    })()
    return () => { cancelled = true }
  }, [ensureSession, open, refreshStatus, setVoiceError])

  useEffect(() => {
    if (!open || !voiceSessionId) return undefined
    const controller = new AbortController()
    api.voice.subscribeSessionEvents(voiceSessionId, applyVoiceEvent, { signal: controller.signal })
      .catch(e => {
        if (e.name !== 'AbortError') setVoiceError(`voice event stream failed: ${e.message}`)
      })
    return () => controller.abort()
  }, [applyVoiceEvent, open, setVoiceError, voiceSessionId])

  useEffect(() => () => {
    stopMicLevel()
    stopAudioPlayback()
  }, [stopAudioPlayback, stopMicLevel])

  const applyPreset = useCallback((preset) => {
    setGender(preset.gender)
    setTone(preset.tone)
    const selectedGender = voiceGenderFromLabel(preset.gender)
    setVoiceCoreSettings(prev => ({ ...prev, voice: selectedGender, gender: selectedGender }))
  }, [])

  const startRecording = useCallback(async () => {
    const sessionId = await ensureSession().catch(e => {
      setVoiceError(e.message)
      return null
    })
    if (!sessionId) return

    stopAudioPlayback()
    cancelRecordingRef.current = false
    transcriptRef.current = ''
    setTranscript('')
    setAiResponse('')
    setVoiceTranscript('')
    setVoiceReply('', null)
    setVoicePhase(VOICE_PHASES.LISTENING)
    setPlayback('')

    let runtime = runtimeStatus || null
    try {
      runtime = await api.voice.runtime()
      setRuntimeStatus(runtime)
      setVoiceRuntime(runtime)
    } catch (e) {
      setPlayback(`voice runtime status unavailable: ${e.message}`)
    }

    const backendSttReady = runtime?.stt?.state === 'ready'
    if (backendSttReady && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        })
        await startMicLevel(stream)
        recordChunksRef.current = []
        const mimeType = chooseRecorderMimeType()
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
        recorder.ondataavailable = (event) => {
          if (event.data?.size) recordChunksRef.current.push(event.data)
        }
        recorder.onerror = (event) => {
          const message = event?.error?.message || 'local recorder failed'
          setVoiceError(message)
          setRecording(false)
          setRecordingMode('idle')
          stopMicLevel()
        }
        recorder.onstop = async () => {
          const chunks = recordChunksRef.current
          recordChunksRef.current = []
          mediaRecorderRef.current = null
          setRecording(false)
          setRecordingMode('idle')
          stopMicLevel()
          if (cancelRecordingRef.current) return
          if (!chunks.length) {
            setVoiceError('Recorded audio was empty.')
            return
          }

          setSending(true)
          setPlayback('transcribing local audio...')
          setVoicePhase(VOICE_PHASES.TRANSCRIBING)
          try {
            const recordedBlob = new Blob(chunks, { type: recorder.mimeType || mimeType || 'audio/webm' })
            const wavBlob = await encodeBlobToWav(recordedBlob, 16000)
            const data = await api.voice.sendSessionAudio(sessionId, wavBlob)
            if (data.runtime) {
              setRuntimeStatus(data.runtime)
              setVoiceRuntime(data.runtime)
            }
            const finalTranscript = data.session?.transcript || data.transcript || ''
            const reply = data.reply || data.content || data.session?.reply || ''
            if (finalTranscript) {
              transcriptRef.current = finalTranscript
              setTranscript(finalTranscript)
              setVoiceTranscript(finalTranscript)
            }
            if (reply) {
              setAiResponse(reply)
              setVoiceReply(reply, data.latency_ms ?? data.session?.latency_ms ?? null)
              await playReplyRef.current?.(reply)
            } else {
              setPlayback('local STT completed, but the AI returned no spoken reply')
            }
          } catch (e) {
            if (e.payload?.runtime) {
              setRuntimeStatus(e.payload.runtime)
              setVoiceRuntime(e.payload.runtime)
            }
            setPlayback(`local voice turn failed: ${e.message}`)
            setVoiceError(e.message)
          } finally {
            setSending(false)
          }
        }
        mediaRecorderRef.current = recorder
        setRecordingMode('local_stt')
        setRecording(true)
        recorder.start()
        return
      } catch (e) {
        setPlayback(`local recorder unavailable: ${e.message}. Browser speech fallback used.`)
        stopMicLevel()
      }
    }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setTranscript('[Local STT not ready and browser speech recognition not available]')
      setVoiceError('Local STT is not ready, and browser speech recognition is not available.')
      return
    }
    await startMicLevel()
    const recognition = new SR()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = navigator.language || 'en-US'
    recognition.onresult = (event) => {
      const text = Array.from(event.results).map(result => result[0].transcript).join('').trim()
      transcriptRef.current = text
      setTranscript(text)
      setVoiceTranscript(text)
    }
    recognition.onerror = (event) => {
      const message = event?.error ? `speech recognition: ${event.error}` : 'speech recognition failed'
      setVoiceError(message)
      setRecording(false)
      setRecordingMode('idle')
      stopMicLevel()
    }
    recognition.onend = () => {
      setRecording(false)
      setRecordingMode('idle')
      stopMicLevel()
      if (transcriptRef.current.trim()) setVoicePhase(VOICE_PHASES.TRANSCRIBING)
    }
    recognition.start()
    recogRef.current = recognition
    setRecordingMode('browser_fallback')
    setRecording(true)
  }, [
    ensureSession,
    runtimeStatus,
    setVoiceError,
    setVoicePhase,
    setVoiceReply,
    setVoiceRuntime,
    setVoiceTranscript,
    startMicLevel,
    stopAudioPlayback,
    stopMicLevel,
  ])

  const stopRecording = useCallback(() => {
    cancelRecordingRef.current = false
    const recorder = mediaRecorderRef.current
    if (recorder) {
      try {
        if (recorder.state !== 'inactive') recorder.stop()
      } catch { /* ignore */ }
      return
    }
    try { recogRef.current?.stop() } catch { /* ignore */ }
    recogRef.current = null
    setRecording(false)
    setRecordingMode('idle')
    stopMicLevel()
    if (transcriptRef.current.trim()) setVoicePhase(VOICE_PHASES.TRANSCRIBING)
  }, [setVoicePhase, stopMicLevel])

  const speakBrowserFallback = useCallback((text) => {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const fallbackGender = voiceGenderFromLabel(gender)
    const utterance = new SpeechSynthesisUtterance(text.slice(0, 500))
    utterance.rate = 0.95
    utterance.pitch = fallbackGender === 'male' ? 0.86 : 1.03
    utterance.onstart = () => {
      setVoicePhase(VOICE_PHASES.SPEAKING)
      setVoiceSpeaking(true)
      setPlayback('browser speech fallback active')
    }
    utterance.onend = () => {
      setVoiceSpeaking(false)
      setVoiceAudioLevel(0)
      setVoicePhase(VOICE_PHASES.IDLE)
    }
    utterance.onerror = () => {
      setVoiceSpeaking(false)
      setVoiceAudioLevel(0)
      setVoiceError('browser speech fallback failed')
    }
    window.speechSynthesis.speak(utterance)
  }, [gender, setVoiceAudioLevel, setVoiceError, setVoicePhase, setVoiceSpeaking])

  const playBackendVoice = useCallback(async (text) => {
    stopAudioPlayback()
    setPlayback('synthesizing local voice...')
    setLastArtifact(null)
    setVoicePhase(VOICE_PHASES.THINKING)
    const selectedLanguage = voiceLanguage === 'auto' ? detectReplyLanguage(text) : voiceLanguage
    const selectedVoiceGender = voiceGenderFromLabel(gender)
    const selectedVoice = provider === 'voice_core_local'
      ? selectedVoiceGender
      : provider === 'voice_lite_base'
        ? 'base'
        : voiceLiteSettings.voice

    const token = sessionStorage.getItem('ai_jwt')
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch('/api/voice/synthesize', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        text,
        provider,
        language: selectedLanguage,
        voice: selectedVoice,
        gender: selectedVoiceGender,
        emotion,
        emotion_intensity: Number(emotionIntensity),
        speaking_rate: Number(voiceCoreSettings.speakingRate || 1),
        persona: {
          provider,
          language: selectedLanguage,
          voice: selectedVoice,
          gender: selectedVoiceGender,
          tone: tone.toLowerCase(),
          emotion,
          emotion_intensity: Number(emotionIntensity),
          speaking_rate: Number(voiceCoreSettings.speakingRate || 1),
          voiceCore: {
            ...voiceCoreSettings,
            voice: selectedVoiceGender,
            gender: selectedVoiceGender,
            threads: Number(voiceCoreSettings.threads || 4),
            timeoutMs: Number(voiceCoreSettings.timeoutMs || 30000),
          },
          voiceLite: {
            ...voiceLiteSettings,
            threads: Number(voiceLiteSettings.threads || 4),
            timeoutMs: Number(voiceLiteSettings.timeoutMs || 30000),
          },
          fishSpeech: {
            ...fishSettings,
            seed: fishSettings.seed === '' ? null : Number(fishSettings.seed),
          },
        },
      }),
    })

    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        detail = body.error || body.setup || detail
      } catch { /* ignore */ }
      setPlayback(`${provider === 'fish_speech' ? 'Fish Speech' : provider === 'voice_core_local' ? 'Default Human Voice' : 'Voice Lite'} unavailable: ${detail}. Browser fallback used.`)
      if (provider === 'local' || voiceLiteSettings.localFallback || voiceCoreSettings.localFallback || fishSettings.localFallback) {
        speakBrowserFallback(text)
      }
      return false
    }

    const blob = await res.blob()
    const artifactUrl = res.headers.get('X-Voice-Artifact-Url')
    const artifactId = res.headers.get('X-Voice-Artifact-Id')
    if (artifactUrl) setLastArtifact({ id: artifactId, url: artifactUrl })

    const audio = new Audio(URL.createObjectURL(blob))
    audioRef.current = audio
    audio.onplay = () => {
      setVoicePhase(VOICE_PHASES.SPEAKING)
      setVoiceSpeaking(true)
    }
    audio.onended = () => {
      cleanupAudioAnalyser()
      setVoiceSpeaking(false)
      setVoicePhase(VOICE_PHASES.IDLE)
      setPlayback(artifactUrl ? `played backend audio: ${artifactUrl}` : 'played backend audio')
    }
    audio.onerror = () => {
      cleanupAudioAnalyser()
      setVoiceSpeaking(false)
      setVoiceError('backend audio playback failed')
    }
    await attachPlaybackAnalyser(audio)
    await audio.play()
    return true
  }, [
    attachPlaybackAnalyser,
    cleanupAudioAnalyser,
    fishSettings,
    emotion,
    emotionIntensity,
    gender,
    provider,
    setVoiceError,
    setVoicePhase,
    setVoiceSpeaking,
    speakBrowserFallback,
    stopAudioPlayback,
    tone,
    voiceCoreSettings,
    voiceLanguage,
    voiceLiteSettings,
  ])

  useEffect(() => {
    playReplyRef.current = async (text) => {
      await playBackendVoice(text).catch(() => speakBrowserFallback(text))
    }
  }, [playBackendVoice, speakBrowserFallback])

  const testVoice = useCallback(() => {
    const address = `${userRank.trim() || 'Chief'} ${userName.trim() || 'Lars'}`
    const sample = `${address}, command voice link established. Default human voice ready in ${voiceGenderFromLabel(gender)} mode. I can converse, plan with you, and route approved voice commands through the local system.`
    playBackendVoice(sample).catch((e) => {
      setPlayback(`backend error: ${e.message}. Browser fallback used.`)
      if (provider === 'local' || voiceLiteSettings.localFallback || voiceCoreSettings.localFallback || fishSettings.localFallback) speakBrowserFallback(sample)
    })
  }, [fishSettings.localFallback, gender, playBackendVoice, provider, speakBrowserFallback, userName, userRank, voiceCoreSettings.localFallback, voiceLiteSettings.localFallback])

  const saveVoiceConfig = useCallback(async () => {
    setSaving(true)
    setPlayback('')
    try {
      const selectedVoiceGender = voiceGenderFromLabel(gender)
      const payload = {
        provider: provider.startsWith('voice_lite') ? 'voice_lite' : provider,
        identity: {
          userName: userName.trim() || 'Lars',
          rank: userRank.trim() || 'Chief',
          addressStyle: 'command',
          startupStyle: 'soldier',
        },
        voiceCore: {
          ...voiceCoreSettings,
          enabled: true,
          language: voiceLanguage === 'auto' ? 'en' : voiceLanguage,
          voice: selectedVoiceGender,
          gender: selectedVoiceGender,
          emotion,
          emotionIntensity: Number(emotionIntensity),
          speakingRate: Number(voiceCoreSettings.speakingRate || 1),
          localFallback: Boolean(voiceCoreSettings.localFallback),
          threads: Number(voiceCoreSettings.threads || 4),
          timeoutMs: Number(voiceCoreSettings.timeoutMs || 30000),
        },
        voiceLite: {
          ...voiceLiteSettings,
          enabled: true,
          language: voiceLanguage === 'auto' ? 'en' : voiceLanguage,
          voice: provider === 'voice_lite_base' ? 'base' : 'base',
          localFallback: Boolean(voiceLiteSettings.localFallback),
          threads: Number(voiceLiteSettings.threads || 4),
          timeoutMs: Number(voiceLiteSettings.timeoutMs || 30000),
        },
        fishSpeech: {
          ...fishSettings,
          enabled: Boolean(fishSettings.enabled),
          localFallback: Boolean(fishSettings.localFallback),
          temperature: Number(fishSettings.temperature),
          topP: Number(fishSettings.topP),
          repetitionPenalty: Number(fishSettings.repetitionPenalty),
          chunkLength: Number(fishSettings.chunkLength),
          maxNewTokens: Number(fishSettings.maxNewTokens),
          seed: fishSettings.seed === '' ? null : Number(fishSettings.seed),
        },
      }
      await api.voice.saveConfig(payload)
      setPlayback('voice config saved')
      await refreshStatus()
    } catch (e) {
      setPlayback(`save failed: ${e.message}`)
      setVoiceError(e.message)
    } finally {
      setSaving(false)
    }
  }, [emotion, emotionIntensity, fishSettings, gender, provider, refreshStatus, setVoiceError, userName, userRank, voiceCoreSettings, voiceLanguage, voiceLiteSettings])

  const updateFish = useCallback((key, value) => {
    setFishSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const updateVoiceCore = useCallback((key, value) => {
    setVoiceCoreSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const handleSendToAI = useCallback(async (overrideText) => {
    const text = String(overrideText || transcript || '').trim()
    if (!text || sending) return
    setSending(true)
    setAiResponse('')
    setVoiceTranscript(text)
    setVoicePhase(VOICE_PHASES.TRANSCRIBING)
    try {
      const sessionId = await ensureSession()
      setVoicePhase(VOICE_PHASES.THINKING)
      const data = await api.voice.sendSessionText(sessionId, text)
      const reply = data.reply || data.message || data.content || 'No response'
      setAiResponse(reply)
      setVoiceReply(reply, data.latency_ms ?? null)
      await playBackendVoice(reply).catch(() => speakBrowserFallback(reply))
    } catch (e) {
      setAiResponse('Error: ' + e.message)
      setVoiceError(e.message)
    } finally {
      setSending(false)
    }
  }, [
    ensureSession,
    playBackendVoice,
    sending,
    setVoiceError,
    setVoicePhase,
    setVoiceReply,
    setVoiceTranscript,
    speakBrowserFallback,
    transcript,
  ])

  const interruptVoice = useCallback(async () => {
    cancelRecordingRef.current = true
    try {
      if (mediaRecorderRef.current?.state && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
    } catch { /* ignore */ }
    mediaRecorderRef.current = null
    recordChunksRef.current = []
    try { recogRef.current?.stop() } catch { /* ignore */ }
    recogRef.current = null
    setRecording(false)
    setRecordingMode('idle')
    stopMicLevel()
    stopAudioPlayback()
    interruptLocal()
    setPlayback('interrupted')
    const sessionId = useVoiceStore.getState().sessionId
    if (sessionId) await api.voice.interruptSession(sessionId).catch(() => {})
    setTimeout(() => {
      if (useVoiceStore.getState().phase === VOICE_PHASES.INTERRUPTED) {
        setVoicePhase(VOICE_PHASES.IDLE)
      }
    }, 900)
  }, [interruptLocal, setVoicePhase, stopAudioPlayback, stopMicLevel])

  const clearTurn = useCallback(() => {
    transcriptRef.current = ''
    setTranscript('')
    setAiResponse('')
    setPlayback('')
    setVoiceTranscript('')
    setVoiceReply('', null)
    setVoicePhase(VOICE_PHASES.IDLE)
  }, [setVoicePhase, setVoiceReply, setVoiceTranscript])

  const displayedRuntime = runtimeStatus || voiceRuntime
  const localSttState = displayedRuntime?.stt?.state || 'runtime_missing'
  const localVadState = displayedRuntime?.vad?.state || 'model_missing'
  const voiceCoreState = displayedRuntime?.tts?.voice_core_local?.state || displayedRuntime?.tts?.state || 'unknown'
  const voiceLiteState = displayedRuntime?.tts?.voice_lite?.state || displayedRuntime?.tts?.state || 'unknown'
  const fishState = displayedRuntime?.tts?.fish_speech?.state || 'unknown'
  const voiceCore = displayedRuntime?.tts?.voice_core_local || {}
  const voiceLite = displayedRuntime?.tts?.voice_lite || {}
  const inputModeLabel = recordingMode === 'local_stt'
    ? 'recording local audio for backend Whisper'
    : recordingMode === 'browser_fallback'
      ? 'browser speech fallback active'
      : localSttState === 'ready'
        ? 'local backend STT ready'
        : 'local backend STT unavailable; browser fallback only'

  if (!open) return null

  return (
    <div className="vm-overlay" onClick={() => setOpen(false)}>
      <div className="vm-modal" onClick={e => e.stopPropagation()} role="dialog" aria-label="Voice settings">
        <header className="vm-head">
          <div>
            <div className="vm-title">VOICE & PERSONA</div>
            <div className="vm-sub">
              <span className={`vm-dot ${status.connected ? 'on' : 'off'}`} />
              backend: {status.backend}
            </div>
          </div>
          <button className="vm-close" onClick={() => setOpen(false)} aria-label="Close">x</button>
        </header>

        <div className={`vm-session vm-session--${voicePhase}`}>
          <span>{voicePhase.toUpperCase()}</span>
          <span>{voiceStatusLabel(displayedRuntime, providerStatus)}</span>
          {voiceLatency != null && <span>{voiceLatency}ms</span>}
        </div>

        <nav className="vm-tabs">
          {['persona', 'recording', 'output'].map(t => (
            <button
              key={t}
              className={`vm-tab ${tab === t ? 'active' : ''}`}
              onClick={() => setTab(t)}
            >{t.toUpperCase()}</button>
          ))}
        </nav>

        <div className="vm-body">
          {tab === 'persona' && (
            <div className="vm-section">
              <div className="vm-label">PRESETS</div>
              <div className="vm-presets">
                {PRESETS.map(p => (
                  <button key={p.id} className="vm-preset" onClick={() => applyPreset(p)}>
                    {p.label}
                  </button>
                ))}
              </div>
              <div className="vm-label">ADDRESS</div>
              <div className="vm-grid">
                <label>
                  User name
                  <input value={userName} onChange={e => setUserName(e.target.value)} />
                </label>
                <label>
                  Rank
                  <input value={userRank} onChange={e => setUserRank(e.target.value)} />
                </label>
              </div>
              <div className="vm-label">GENDER</div>
              <div className="vm-options">
                {GENDERS.map(g => (
                  <button
                    key={g}
                    className={`vm-opt ${gender === g ? 'active' : ''}`}
                    onClick={() => {
                      setGender(g)
                      const selectedGender = voiceGenderFromLabel(g)
                      setVoiceCoreSettings(prev => ({ ...prev, voice: selectedGender, gender: selectedGender }))
                    }}
                  >{g}</button>
                ))}
              </div>
              <div className="vm-label">TONE</div>
              <div className="vm-options">
                {TONES.map(t => (
                  <button
                    key={t}
                    className={`vm-opt ${tone === t ? 'active' : ''}`}
                    onClick={() => setTone(t)}
                  >{t}</button>
                ))}
              </div>
              <div className="vm-actions">
                <button className="vm-action" onClick={testVoice}>TEST VOICE</button>
                <button className="vm-action vm-action--ghost" onClick={interruptVoice}>INTERRUPT</button>
              </div>
              {playback && <div className="vm-status-line">{playback}</div>}
            </div>
          )}

          {tab === 'recording' && (
            <div className="vm-section">
              <div className="vm-label">VOICE INPUT</div>
              <div className="vm-runtime-state">
                <span>Input: {inputModeLabel}</span>
                <span>Whisper: {localSttState}</span>
                <span>VAD: {localVadState}</span>
                <span>Default Voice: {voiceCoreState}</span>
                <span>Voice Lite: {voiceLiteState}</span>
                <span>Fish: {fishState}</span>
              </div>
              <div className={`vm-waveform ${recording ? 'rec' : ''}`} style={{ '--vm-level': micLevel }}>
                <span /><span /><span /><span /><span />
              </div>
              <div className="vm-actions">
                {!recording ? (
                  <button className="vm-action vm-action--rec" onClick={startRecording}>
                    {localSttState === 'ready' ? 'START LOCAL PTT' : 'START FALLBACK'}
                  </button>
                ) : (
                  <button className="vm-action vm-action--stop" onClick={stopRecording}>STOP RECORDING</button>
                )}
                <button
                  className="vm-action vm-action--ghost"
                  onClick={clearTurn}
                  disabled={!transcript && !aiResponse}
                >CLEAR</button>
                <button className="vm-action vm-action--ghost" onClick={interruptVoice}>INTERRUPT</button>
                <button
                  className="vm-action vm-action--send"
                  onClick={() => handleSendToAI()}
                  disabled={!transcript || sending}
                >
                  {sending ? 'SENDING...' : 'SEND TEXT'}
                </button>
              </div>
              <div className="vm-label">TRANSCRIPT</div>
              <div className="vm-transcript">
                {transcript || <span className="vm-empty">Press start, speak, then stop. Local STT will answer automatically when ready.</span>}
              </div>
              {aiResponse && (
                <div className="vm-ai-response">
                  <div className="vm-label">AI RESPONSE</div>
                  <div className="vm-response-text">{aiResponse}</div>
                  <button className="vm-action vm-action--ghost" onClick={() => playBackendVoice(aiResponse)}>REPLAY</button>
                </div>
              )}
            </div>
          )}

          {tab === 'output' && (
            <div className="vm-section">
              <div className="vm-label">LOCAL SYNTHESIS PROVIDER</div>
              <div className="vm-options">
                <button className={`vm-opt ${provider === 'voice_core_local' ? 'active' : ''}`} onClick={() => setProvider('voice_core_local')}>
                  DEFAULT HUMAN
                </button>
                <button className={`vm-opt ${provider === 'voice_lite_base' ? 'active' : ''}`} onClick={() => setProvider('voice_lite_base')}>
                  VOICE LITE REPAIR
                </button>
                <button className={`vm-opt ${provider === 'fish_speech' ? 'active' : ''}`} onClick={() => setProvider('fish_speech')}>
                  FISH PREMIUM
                </button>
                <button className={`vm-opt ${provider === 'local' ? 'active' : ''}`} onClick={() => setProvider('local')}>
                  OS FALLBACK
                </button>
              </div>

              <div className="vm-runtime-state">
                <span>Default: {voiceCoreState}</span>
                <span>Human EN: {voiceCore.tts_en_ready ? voiceCore.active_voice?.voice || 'af_heart' : 'missing'}</span>
                <span>Human NL: {voiceCore.tts_nl_ready ? 'piper nl_NL' : 'missing'}</span>
                <span>Voice Lite: {voiceLiteState}</span>
                <span>EN fallback: {voiceLite.base_en_ready ? 'base' : 'missing'}</span>
                <span>NL fallback: {voiceLite.base_nl_ready ? 'base' : 'missing'}</span>
                <span>Fish: {fishState}</span>
              </div>

              <div className="vm-field">
                <label>Voice language</label>
                <select value={voiceLanguage} onChange={e => setVoiceLanguage(e.target.value)}>
                  <option value="auto">Auto detect</option>
                  <option value="en">English</option>
                  <option value="nl">Dutch</option>
                </select>
              </div>

              <div className="vm-grid">
                <label>
                  Emotion
                  <select value={emotion} onChange={e => setEmotion(e.target.value)}>
                    {EMOTIONS.map(item => (
                      <option key={item} value={item}>{item.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Emotion intensity
                  <input type="range" min="0" max="0.7" step="0.05" value={emotionIntensity} onChange={e => setEmotionIntensity(e.target.value)} />
                  <span>{Number(emotionIntensity).toFixed(2)}</span>
                </label>
                <label>
                  Speaking rate
                  <input type="range" min="0.85" max="1.15" step="0.01" value={voiceCoreSettings.speakingRate || 1} onChange={e => updateVoiceCore('speakingRate', e.target.value)} />
                  <span>{Number(voiceCoreSettings.speakingRate || 1).toFixed(2)}</span>
                </label>
                <label>
                  CPU threads
                  <input
                    type="number"
                    min="1"
                    max="8"
                    value={voiceCoreSettings.threads}
                    onChange={e => updateVoiceCore('threads', e.target.value)}
                  />
                </label>
                <label>
                  Timeout ms
                  <input
                    type="number"
                    min="3000"
                    max="60000"
                    value={voiceCoreSettings.timeoutMs}
                    onChange={e => updateVoiceCore('timeoutMs', e.target.value)}
                  />
                </label>
              </div>

              <label className="vm-check">
                <input type="checkbox" checked={Boolean(voiceCoreSettings.localFallback)} onChange={e => updateVoiceCore('localFallback', e.target.checked)} />
                Explicitly use browser fallback when Default Human Voice is unavailable
              </label>

              <div className="vm-field">
                <label>Fish server URL</label>
                <input value={fishSettings.baseUrl || ''} onChange={e => updateFish('baseUrl', e.target.value)} />
              </div>
              <div className="vm-field">
                <label>Reference voice ID</label>
                <input value={fishSettings.referenceId || ''} onChange={e => updateFish('referenceId', e.target.value)} placeholder="my-speaker" />
              </div>

              <div className="vm-grid">
                <label>
                  Temperature
                  <input type="range" min="0.1" max="1" step="0.05" value={fishSettings.temperature} onChange={e => updateFish('temperature', e.target.value)} />
                  <span>{Number(fishSettings.temperature).toFixed(2)}</span>
                </label>
                <label>
                  Top P
                  <input type="range" min="0.1" max="1" step="0.05" value={fishSettings.topP} onChange={e => updateFish('topP', e.target.value)} />
                  <span>{Number(fishSettings.topP).toFixed(2)}</span>
                </label>
                <label>
                  Repetition
                  <input type="range" min="0.9" max="2" step="0.05" value={fishSettings.repetitionPenalty} onChange={e => updateFish('repetitionPenalty', e.target.value)} />
                  <span>{Number(fishSettings.repetitionPenalty).toFixed(2)}</span>
                </label>
                <label>
                  Chunk
                  <input type="number" min="100" max="1000" value={fishSettings.chunkLength} onChange={e => updateFish('chunkLength', e.target.value)} />
                </label>
                <label>
                  Max tokens
                  <input type="number" min="0" max="8192" value={fishSettings.maxNewTokens} onChange={e => updateFish('maxNewTokens', e.target.value)} />
                </label>
                <label>
                  Seed
                  <input type="number" value={fishSettings.seed ?? ''} onChange={e => updateFish('seed', e.target.value)} placeholder="random" />
                </label>
              </div>

              <label className="vm-check">
                <input type="checkbox" checked={Boolean(fishSettings.localFallback)} onChange={e => updateFish('localFallback', e.target.checked)} />
                Keep local OS fallback enabled when Fish is offline
              </label>

              {status.detail && <div className="vm-status-line">{status.detail}</div>}
              {playback && <div className="vm-status-line">{playback}</div>}
              {lastArtifact?.url && (
                <a className="vm-artifact" href={lastArtifact.url} target="_blank" rel="noreferrer">
                  Open last voice artifact
                </a>
              )}

              <div className="vm-actions">
                <button className="vm-action" onClick={saveVoiceConfig} disabled={saving}>{saving ? 'SAVING...' : 'SAVE CONFIG'}</button>
                <button className="vm-action vm-action--ghost" onClick={refreshStatus}>RETRY STATUS</button>
                <button className="vm-action" onClick={testVoice}>SPEAK SAMPLE</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
