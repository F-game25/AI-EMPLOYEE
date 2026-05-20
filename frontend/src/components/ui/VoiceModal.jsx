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
  const [recording,  setRecording]  = useState(false)
  const [transcript, setTranscript] = useState('')
  const [sending,    setSending]    = useState(false)
  const [aiResponse, setAiResponse] = useState('')
  const [status,     setStatus]     = useState({ connected: false, backend: 'unknown' })
  const recogRef = useRef(null)

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

  // Probe backend status when opened
  useEffect(() => {
    if (!open) return
    fetch('/api/voice/personaplex/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setStatus({ connected: true, backend: d.backend || 'personaplex' }))
      .catch(() => setStatus({ connected: false, backend: 'offline' }))
  }, [open])

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

  const speakText = useCallback((text) => {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text.slice(0, 500))
    u.rate = 0.95; u.pitch = 1.0
    window.speechSynthesis.speak(u)
  }, [])

  const testVoice = useCallback(() => {
    speakText(`Voice ${tone.toLowerCase()} ${gender.toLowerCase()} ready.`)
  }, [speakText, tone, gender])

  const handleSendToAI = useCallback(async () => {
    if (!transcript.trim()) return
    setSending(true)
    setAiResponse('')
    try {
      const data = await api.chat.send(transcript, undefined)
      const reply = data.reply || data.message || data.content || 'No response'
      setAiResponse(reply)
      speakText(reply)
    } catch (e) {
      setAiResponse('Error: ' + e.message)
    } finally {
      setSending(false)
    }
  }, [transcript, speakText])

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
                  <button className="vm-action vm-action--ghost" onClick={() => speakText(aiResponse)}>▶ REPLAY</button>
                </div>
              )}
            </div>
          )}

          {tab === 'output' && (
            <div className="vm-section">
              <div className="vm-label">SYNTHESIS</div>
              <p className="vm-help">
                Voice output uses the browser SpeechSynthesis API by default and
                falls back to the PersonaPlex backend when reachable. Settings on
                the Persona tab control voice characteristics.
              </p>
              <button className="vm-action" onClick={testVoice}>▶ SPEAK SAMPLE</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
