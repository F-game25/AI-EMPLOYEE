import { useState, useEffect, useCallback, useRef } from 'react'
import api from '../../api/client'
import './VoiceModal.css'

const GENDERS = ['NEUTRAL', 'MASCULINE', 'FEMININE']
const TONES   = ['CALM', 'PROFESSIONAL', 'WARM', 'AUTHORITATIVE']
const PRESETS = [
  { id: 'analyst',  label: 'ANALYST',  gender: 'NEUTRAL',   tone: 'PROFESSIONAL' },
  { id: 'concierge',label: 'CONCIERGE',gender: 'FEMININE',  tone: 'WARM' },
  { id: 'sentinel', label: 'SENTINEL', gender: 'MASCULINE', tone: 'AUTHORITATIVE' },
]

export default function VoiceModal() {
  const [open, setOpen] = useState(false)
  const [tab,  setTab]  = useState('persona')
  const [gender,    setGender]    = useState('NEUTRAL')
  const [tone,      setTone]      = useState('PROFESSIONAL')
  const [provider,  setProvider]  = useState('fish_speech')
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
  const [recording,  setRecording]  = useState(false)
  const [transcript, setTranscript] = useState('')
  const [sending,    setSending]    = useState(false)
  const [aiResponse, setAiResponse] = useState('')
  const [status,     setStatus]     = useState({ connected: false, backend: 'unknown', detail: '' })
  const [saving,     setSaving]     = useState(false)
  const [playback,   setPlayback]   = useState('')
  const [lastArtifact, setLastArtifact] = useState(null)
  const recogRef = useRef(null)
  const audioRef = useRef(null)

  // Listen for the dock to dispatch the open event
  useEffect(() => {
    const openHandler = () => setOpen(true)
    window.addEventListener('nx:voice-open', openHandler)
    return () => window.removeEventListener('nx:voice-open', openHandler)
  }, [])

  // Close on Esc
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const refreshStatus = useCallback(async () => {
    try {
      const data = await api.get('/api/voice/config')
      const cfg = data.config || {}
      const fish = cfg.fishSpeech || {}
      setProvider(cfg.provider || 'fish_speech')
      setFishSettings(prev => ({ ...prev, ...fish, seed: fish.seed ?? '' }))
      const fishStatus = data.fish_speech?.status || 'unknown'
      setStatus({
        connected: true,
        backend: cfg.provider === 'local' ? 'local fallback' : `fish: ${fishStatus}`,
        detail: data.fish_speech?.last_error || data.fish_speech?.endpoint || '',
      })
    } catch (e) {
      setStatus({ connected: false, backend: 'offline', detail: e.message })
    }
  }, [])

  useEffect(() => {
    if (!open) return
    refreshStatus()
  }, [open, refreshStatus])

  const applyPreset = useCallback((p) => {
    setGender(p.gender)
    setTone(p.tone)
  }, [])

  const startRecording = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setTranscript('[Browser speech recognition not available]')
      return
    }
    const r = new SR()
    r.continuous = true
    r.interimResults = true
    r.onresult = (e) => {
      const txt = Array.from(e.results).map(res => res[0].transcript).join('')
      setTranscript(txt)
    }
    r.onend = () => setRecording(false)
    r.start()
    recogRef.current = r
    setRecording(true)
  }, [])

  const stopRecording = useCallback(() => {
    recogRef.current?.stop()
    setRecording(false)
  }, [])

  const speakBrowserFallback = useCallback((text) => {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text.slice(0, 500))
    u.rate = 0.95; u.pitch = 1.0
    window.speechSynthesis.speak(u)
  }, [])

  const playBackendVoice = useCallback(async (text) => {
    setPlayback('synthesizing locally...')
    setLastArtifact(null)
    const token = sessionStorage.getItem('ai_jwt')
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch('/api/voice/synthesize', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        text,
        provider,
        persona: {
          provider,
          gender: gender.toLowerCase(),
          tone: tone.toLowerCase(),
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
      setPlayback(`backend unavailable: ${detail}. Browser fallback used.`)
      speakBrowserFallback(text)
      return false
    }
    const blob = await res.blob()
    const artifactUrl = res.headers.get('X-Voice-Artifact-Url')
    const artifactId = res.headers.get('X-Voice-Artifact-Id')
    if (artifactUrl) setLastArtifact({ id: artifactId, url: artifactUrl })
    if (audioRef.current) {
      audioRef.current.pause()
      URL.revokeObjectURL(audioRef.current.src)
    }
    const audio = new Audio(URL.createObjectURL(blob))
    audioRef.current = audio
    await audio.play()
    setPlayback(artifactUrl ? `played Fish Speech audio, artifact ${artifactUrl}` : 'played backend audio')
    return true
  }, [fishSettings, gender, provider, speakBrowserFallback, tone])

  const testVoice = useCallback(() => {
    const sample = `[professional calm tone] Voice ${tone.toLowerCase()} ${gender.toLowerCase()} ready. This is the local Fish Speech route.`
    playBackendVoice(sample).catch((e) => {
      setPlayback(`backend error: ${e.message}. Browser fallback used.`)
      speakBrowserFallback(sample)
    })
  }, [gender, playBackendVoice, speakBrowserFallback, tone])

  const saveVoiceConfig = useCallback(async () => {
    setSaving(true)
    setPlayback('')
    try {
      const payload = {
        provider,
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
      await api.post('/api/voice/config', payload)
      setPlayback('voice config saved')
      await refreshStatus()
    } catch (e) {
      setPlayback(`save failed: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }, [fishSettings, provider, refreshStatus])

  const updateFish = useCallback((key, value) => {
    setFishSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const handleSendToAI = useCallback(async () => {
    if (!transcript.trim()) return
    setSending(true)
    setAiResponse('')
    try {
      const data = await api.chat.send(transcript, undefined)
      const reply = data.reply || data.message || data.content || 'No response'
      setAiResponse(reply)
      playBackendVoice(reply).catch(() => speakBrowserFallback(reply))
    } catch (e) {
      setAiResponse('Error: ' + e.message)
    } finally {
      setSending(false)
    }
  }, [playBackendVoice, speakBrowserFallback, transcript])

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
          <button className="vm-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
        </header>

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
              <div className="vm-label">GENDER</div>
              <div className="vm-options">
                {GENDERS.map(g => (
                  <button
                    key={g}
                    className={`vm-opt ${gender === g ? 'active' : ''}`}
                    onClick={() => setGender(g)}
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
              <button className="vm-action" onClick={testVoice}>▶ TEST VOICE</button>
              {playback && <div className="vm-status-line">{playback}</div>}
            </div>
          )}

          {tab === 'recording' && (
            <div className="vm-section">
              <div className="vm-label">VOICE INPUT</div>
              <div className={`vm-waveform ${recording ? 'rec' : ''}`}>
                <span /><span /><span /><span /><span />
              </div>
              <div className="vm-actions">
                {!recording ? (
                  <button className="vm-action vm-action--rec" onClick={startRecording}>● START RECORDING</button>
                ) : (
                  <button className="vm-action vm-action--stop" onClick={stopRecording}>■ STOP RECORDING</button>
                )}
                <button
                  className="vm-action vm-action--ghost"
                  onClick={() => { setTranscript(''); setAiResponse('') }}
                  disabled={!transcript}
                >CLEAR</button>
                <button
                  className="vm-action vm-action--send"
                  onClick={handleSendToAI}
                  disabled={!transcript || sending}
                >
                  {sending ? '◌ SENDING…' : '→ SEND TO AI'}
                </button>
              </div>
              <div className="vm-label">TRANSCRIPT</div>
              <div className="vm-transcript">
                {transcript || <span className="vm-empty">Press start and speak — your words will appear here.</span>}
              </div>
              {aiResponse && (
                <div className="vm-ai-response">
                  <div className="vm-label">AI RESPONSE</div>
                  <div className="vm-response-text">{aiResponse}</div>
                  <button className="vm-action vm-action--ghost" onClick={() => playBackendVoice(aiResponse)}>▶ REPLAY</button>
                </div>
              )}
            </div>
          )}

          {tab === 'output' && (
            <div className="vm-section">
              <div className="vm-label">LOCAL SYNTHESIS PROVIDER</div>
              <div className="vm-options">
                <button className={`vm-opt ${provider === 'fish_speech' ? 'active' : ''}`} onClick={() => setProvider('fish_speech')}>
                  FISH S2 LOCAL
                </button>
                <button className={`vm-opt ${provider === 'local' ? 'active' : ''}`} onClick={() => setProvider('local')}>
                  OS FALLBACK
                </button>
              </div>

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
                <button className="vm-action" onClick={testVoice}>▶ SPEAK SAMPLE</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
