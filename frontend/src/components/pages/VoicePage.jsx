import { useState, useEffect, useCallback, useRef } from 'react'
import { useAppStore } from '../../store/appStore'
import api from '../../api/client'
import Panel from '../nexus-ui/Panel'
import KPITile from '../nexus-ui/KPITile'
import HexButton from '../nexus-ui/HexButton'
import StatusPill from '../nexus-ui/StatusPill'
import { SectionLabel, LiveBadge } from '../nexus-ui/SectionLabel'
import Sparkline from '../nexus-ui/Sparkline'
import './VoicePage.css'

const TONES = ['authoritative', 'warm', 'cheerful', 'calm', 'professional', 'casual', 'empathetic', 'robotic']
const ACCENTS = ['American', 'British', 'Indian']
const LANGUAGES = ['English', 'Spanish', 'French']

const PRESETS = [
  { name: 'Executive', gender: 'male', tone: 'authoritative', pitch: 0.9, speed: 0.9, articulation: 0.85, friendliness: 0.4 },
  { name: 'Warm Advisor', gender: 'female', tone: 'warm', pitch: 1.1, speed: 1.0, articulation: 0.65, friendliness: 0.9 },
  { name: 'Calm Guide', gender: 'neutral', tone: 'calm', pitch: 1.0, speed: 0.9, articulation: 0.7, friendliness: 0.7 },
  { name: 'Energetic', gender: 'female', tone: 'cheerful', pitch: 1.3, speed: 1.2, articulation: 0.75, friendliness: 0.95 },
  { name: 'Analyst', gender: 'male', tone: 'professional', pitch: 1.0, speed: 1.1, articulation: 0.9, friendliness: 0.5 },
  { name: 'Casual', gender: 'neutral', tone: 'casual', pitch: 1.05, speed: 1.15, articulation: 0.6, friendliness: 0.85 },
]

const BARS = [12, 18, 28, 42, 55, 38, 62, 71, 58, 44, 32, 25, 38, 48, 60, 72, 65, 50, 38, 28, 18, 12, 8, 14]

/** Custom Slider component (unique to VoicePage, not in nexus-ui) */
function Slider({ label, value, min, max, step = 0.01, color, onChange, format }) {
  return (
    <div className="vp-slider">
      <div className="vp-slider__header">
        <span className="vp-slider__label">{label}</span>
        <span className="vp-slider__value" style={{ color }}>{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="vp-slider__input"
        style={{ '--slider-color': color || 'var(--nx-gold)' }}
      />
    </div>
  )
}

export default function VoicePage() {
  const [tab, setTab] = useState('studio')
  const [testText, setTestText] = useState('Hello, I am your AI Employee. How can I assist you today?')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [backendStatus, setBackendStatus] = useState(null)
  const [active, setActive] = useState(false)

  // Persona params
  const [gender, setGender] = useState('neutral')
  const [tone, setTone] = useState('professional')
  const [pitch, setPitch] = useState(1.0)
  const [speed, setSpeed] = useState(1.0)
  const [articulation, setArticulation] = useState(0.7)
  const [friendliness, setFriendliness] = useState(0.6)

  // Voice recording state
  const [recording, setRecording] = useState(false)
  const [transcription, setTranscription] = useState('')
  const [selectedMicrophone, setSelectedMicrophone] = useState(null)
  const [selectedSpeaker, setSelectedSpeaker] = useState(null)
  const [volume, setVolume] = useState(50)
  const [speechRate, setSpeechRate] = useState(1.0)
  const [voicePitch, setVoicePitch] = useState(0)
  const [accent, setAccent] = useState('American')
  const [language, setLanguage] = useState('English')
  const [microphoneList, setMicrophoneList] = useState([])
  const [speakerList, setSpeakerList] = useState([])

  // Recognition quality metrics
  const [accuracy, setAccuracy] = useState(0.95)
  const [confidence, setConfidence] = useState(0.92)
  const [latency, setLatency] = useState(145)
  const [activeSpeakers, setActiveSpeakers] = useState(1)

  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)

  const persona = { gender, tone, pitch, speed, articulation, friendliness }

  // Initialize backend status and enumerate devices
  useEffect(() => {
    const init = async () => {
      try {
        const status = await api.get('/api/voice/personaplex/status')
        setBackendStatus(status)
      } catch (e) {
        setBackendStatus({ available: false })
      }

      // Enumerate audio devices
      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        const mics = devices.filter(d => d.kind === 'audioinput')
        const speakers = devices.filter(d => d.kind === 'audiooutput')
        setMicrophoneList(mics)
        setSpeakerList(speakers)
        if (mics.length > 0) setSelectedMicrophone(mics[0].deviceId)
        if (speakers.length > 0) setSelectedSpeaker(speakers[0].deviceId)
      } catch (e) {
        console.error('Failed to enumerate devices:', e)
      }
    }
    init()
  }, [])

  // Setup WebAudio for waveform visualization
  useEffect(() => {
    if (!recording) return

    const setupAudio = async () => {
      try {
        const constraints = { audio: { deviceId: selectedMicrophone ? { exact: selectedMicrophone } : undefined } }
        const stream = await navigator.mediaDevices.getUserMedia(constraints)
        const ctx = new (window.AudioContext || window.webkitAudioContext)()
        audioContextRef.current = ctx

        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        analyserRef.current = analyser

        const source = ctx.createMediaStreamSource(stream)
        source.connect(analyser)

        // Animate waveform
        const animate = () => {
          if (!analyserRef.current) return
          requestAnimationFrame(animate)
        }
        animate()
      } catch (e) {
        console.error('Audio setup failed:', e)
        setRecording(false)
      }
    }
    setupAudio()

    return () => {
      if (audioContextRef.current) {
        audioContextRef.current.close()
      }
    }
  }, [recording, selectedMicrophone])

  const applyPreset = useCallback((p) => {
    setGender(p.gender)
    setTone(p.tone)
    setPitch(p.pitch)
    setSpeed(p.speed)
    setArticulation(p.articulation)
    setFriendliness(p.friendliness)
    setTab('studio')
  }, [])

  const handleTest = useCallback(async () => {
    if (!testText.trim()) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.voice.synthesize(testText.trim(), persona)
      setTestResult({ ok: true, message: res.message || 'Synthesized successfully', chars: testText.length })
    } catch (e) {
      setTestResult({ ok: false, message: e.message || 'Synthesis failed' })
    } finally {
      setTesting(false)
    }
  }, [testText, persona])

  const handleStartRecording = useCallback(() => {
    setRecording(true)
    setTranscription('')
  }, [])

  const handleStopRecording = useCallback(() => {
    setRecording(false)
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
  }, [])

  const handleClearTranscript = useCallback(() => {
    setTranscription('')
  }, [])

  const handleExportTranscript = useCallback(() => {
    const element = document.createElement('a')
    const file = new Blob([transcription], { type: 'text/plain' })
    element.href = URL.createObjectURL(file)
    element.download = `transcript-${Date.now()}.txt`
    document.body.appendChild(element)
    element.click()
    document.body.removeChild(element)
  }, [transcription])

  // Simulate accuracy/quality metrics changes
  useEffect(() => {
    if (!recording) return
    const interval = setInterval(() => {
      setAccuracy(0.85 + Math.random() * 0.14)
      setConfidence(0.80 + Math.random() * 0.19)
      setLatency(120 + Math.random() * 80)
    }, 1000)
    return () => clearInterval(interval)
  }, [recording])

  const tabBtn = (id, label) => (
    <button
      onClick={() => setTab(id)}
      className={`vp-tab-btn ${tab === id ? 'vp-tab-btn--active' : ''}`}
    >
      {label}
    </button>
  )

  return (
    <div className="vp-grid">
      {/* KPI Strip */}
      <div className="vp-kpis">
        <KPITile
          label="Studio Status"
          value={backendStatus?.available ? 'ONLINE' : 'OFFLINE'}
          sub="Nvidia PersonaPlex"
          iconTone={backendStatus?.available ? 'success' : 'alert'}
          accent={backendStatus?.available}
        />
        <KPITile
          label="Recognition Accuracy"
          value={`${Math.round(accuracy * 100)}%`}
          sub="Real-time baseline"
          iconTone="gold"
          trend={[0.85, 0.88, 0.91, 0.89, 0.92, 0.95]}
        />
        <KPITile
          label="Active Speakers"
          value={activeSpeakers}
          sub="Current session"
          iconTone="cool"
        />
      </div>

      {/* Tab bar */}
      <div className="vp-tab-bar">
        {tabBtn('studio', 'PERSONA STUDIO')}
        {tabBtn('presets', 'PRESETS')}
      </div>

      {/* Studio Tab */}
      {tab === 'studio' && (
        <div className="vp-cols">
          {/* Left: Persona Configuration */}
          <Panel title="Persona Configuration" className="vp-panel">
            <div className="vp-panel-section">
              <SectionLabel tone="muted" size="sm">GENDER</SectionLabel>
              <div className="vp-button-group">
                {['male', 'female', 'neutral'].map((g) => (
                  <button
                    key={g}
                    onClick={() => setGender(g)}
                    className={`vp-option-btn ${gender === g ? 'vp-option-btn--active' : ''}`}
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>

            <div className="vp-panel-section">
              <SectionLabel tone="muted" size="sm">TONE</SectionLabel>
              <div className="vp-tone-grid">
                {TONES.map((t) => (
                  <button
                    key={t}
                    onClick={() => setTone(t)}
                    className={`vp-tone-btn ${tone === t ? 'vp-tone-btn--active' : ''}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div className="vp-panel-section">
              <Slider
                label="PITCH"
                value={pitch}
                min={0.5}
                max={2.0}
                step={0.05}
                color="var(--nx-gold)"
                onChange={setPitch}
                format={(v) => `${v.toFixed(2)}×`}
              />
              <Slider
                label="SPEED"
                value={speed}
                min={0.5}
                max={2.0}
                step={0.05}
                color="var(--nx-cyan)"
                onChange={setSpeed}
                format={(v) => `${v.toFixed(2)}×`}
              />
              <Slider
                label="ARTICULATION"
                value={articulation}
                min={0}
                max={1}
                step={0.05}
                color="#a855f7"
                onChange={setArticulation}
                format={(v) => `${Math.round(v * 100)}%`}
              />
              <Slider
                label="FRIENDLINESS"
                value={friendliness}
                min={0}
                max={1}
                step={0.05}
                color="#f97316"
                onChange={setFriendliness}
                format={(v) => `${Math.round(v * 100)}%`}
              />
            </div>

            {/* Current persona summary */}
            <div className="vp-persona-summary">
              <div className="vp-persona-summary__header">CURRENT PERSONA</div>
              {Object.entries(persona).map(([k, v]) => (
                <div key={k} className="vp-persona-summary__row">
                  <span>{k}</span>
                  <span>{typeof v === 'number' && k !== 'pitch' && k !== 'speed' ? v.toFixed(2) : String(v)}</span>
                </div>
              ))}
            </div>
          </Panel>

          {/* Right: Controls & Status */}
          <div className="vp-right-col">
            {/* Test Voice Panel */}
            <Panel
              title="Test Voice"
              actions={<StatusPill label={backendStatus?.available ? 'API READY' : 'OFFLINE'} tone={backendStatus?.available ? 'cool' : 'idle'} />}
              className="vp-panel"
            >
              {/* Waveform visualizer */}
              <div className={`vp-waveform ${active ? 'vp-waveform--active' : ''}`} onClick={() => setActive((a) => !a)}>
                {BARS.map((h, i) => (
                  <div
                    key={i}
                    className="vp-waveform__bar"
                    style={{
                      '--bar-height': active ? `${h}%` : `${h * 0.2}%`,
                      '--bar-delay': `${i * 0.01}s`,
                    }}
                  />
                ))}
              </div>

              <textarea
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
                rows={4}
                placeholder="Enter text to synthesize..."
                className="vp-textarea"
              />

              <HexButton
                full
                onClick={handleTest}
                disabled={testing || !testText.trim()}
                loading={testing}
              >
                {testing ? 'SYNTHESIZING...' : 'TEST VOICE'}
              </HexButton>

              {testResult && (
                <div className={`vp-result ${testResult.ok ? 'vp-result--ok' : 'vp-result--error'}`}>
                  {testResult.ok ? '✓ ' : '✗ '}{testResult.message}
                </div>
              )}
            </Panel>

            {/* Backend Status Panel */}
            <Panel title="Backend Status" className="vp-panel vp-panel--flex">
              {backendStatus ? (
                <>
                  <div className="vp-status-row">
                    <span>Available</span>
                    <StatusPill
                      label={backendStatus.available ? 'YES' : 'NO'}
                      tone={backendStatus.available ? 'success' : 'alert'}
                      dot={false}
                    />
                  </div>
                  <div className="vp-status-row">
                    <span>Model</span>
                    <span className="vp-mono">{backendStatus.model || 'N/A'}</span>
                  </div>
                  <div className="vp-status-row">
                    <span>Tones</span>
                    <span className="vp-mono">{backendStatus.tones?.length || TONES.length} styles</span>
                  </div>
                  <div className="vp-status-row">
                    <span>Genders</span>
                    <span className="vp-mono">{backendStatus.genders?.join(', ') || 'male, female, neutral'}</span>
                  </div>
                  {!backendStatus.available && (
                    <div className="vp-error-box">
                      <StatusPill label="NVIDIA KEY REQUIRED" tone="idle" size="sm" dot={false} />
                    </div>
                  )}
                </>
              ) : (
                <div className="vp-loading">Checking backend...</div>
              )}
            </Panel>
          </div>
        </div>
      )}

      {/* Presets Tab */}
      {tab === 'presets' && (
        <div className="vp-presets-grid">
          {PRESETS.map((p) => (
            <div key={p.name} className="vp-preset-card">
              <div className="vp-preset-card__header">
                <span className="vp-preset-card__name">{p.name}</span>
                <StatusPill label={p.gender.toUpperCase()} tone="cool" size="sm" dot={false} />
              </div>
              <div className="vp-preset-card__tone">{p.tone}</div>
              <div className="vp-preset-card__metrics">
                {[
                  ['Pitch', p.pitch / 2],
                  ['Speed', p.speed / 2],
                  ['Articulation', p.articulation],
                  ['Friendliness', p.friendliness],
                ].map(([lbl, val]) => (
                  <div key={lbl} className="vp-preset-card__metric">
                    <div className="vp-preset-card__metric-label">{lbl}</div>
                    <div className="vp-preset-card__sparkline">
                      <Sparkline data={[val * 0.5, val * 0.7, val, val * 0.85, val * 0.95]} width={80} height={16} />
                    </div>
                  </div>
                ))}
              </div>
              <HexButton full size="sm" onClick={() => applyPreset(p)}>
                SELECT PRESET
              </HexButton>
            </div>
          ))}
        </div>
      )}

      {/* Voice Recording & Recognition Section (Studio Tab Only) */}
      {tab === 'studio' && (
        <div className="vp-voice-section">
          <Panel title="Voice Recording & Recognition" className="vp-panel">
            {/* Studio Control */}
            <div className="vp-panel-section">
              <SectionLabel tone="gold">STUDIO CONTROL</SectionLabel>

              <div className="vp-control-group">
                <label className="vp-select-label">
                  Microphone
                  <select
                    value={selectedMicrophone || ''}
                    onChange={(e) => setSelectedMicrophone(e.target.value)}
                    className="vp-select"
                  >
                    {microphoneList.map((mic) => (
                      <option key={mic.deviceId} value={mic.deviceId}>
                        {mic.label || `Input ${mic.deviceId.slice(0, 5)}`}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="vp-select-label">
                  Speaker
                  <select
                    value={selectedSpeaker || ''}
                    onChange={(e) => setSelectedSpeaker(e.target.value)}
                    className="vp-select"
                  >
                    {speakerList.map((speaker) => (
                      <option key={speaker.deviceId} value={speaker.deviceId}>
                        {speaker.label || `Output ${speaker.deviceId.slice(0, 5)}`}
                      </option>
                    ))}
                  </select>
                </label>

                <Slider
                  label="VOLUME"
                  value={volume}
                  min={0}
                  max={100}
                  step={1}
                  color="var(--nx-cyan)"
                  onChange={setVolume}
                  format={(v) => `${Math.round(v)}%`}
                />

                <HexButton
                  full
                  variant="primary"
                  onClick={() => setActive(!active)}
                  tone="cool"
                >
                  TEST AUDIO
                </HexButton>
              </div>
            </div>

            {/* Voice Settings */}
            <div className="vp-panel-section">
              <SectionLabel tone="gold">VOICE SETTINGS</SectionLabel>

              <Slider
                label="SPEECH RATE"
                value={speechRate}
                min={0.5}
                max={2.0}
                step={0.1}
                color="var(--nx-gold)"
                onChange={setSpeechRate}
                format={(v) => `${v.toFixed(1)}×`}
              />

              <Slider
                label="PITCH"
                value={voicePitch}
                min={-2}
                max={2}
                step={0.1}
                color="var(--nx-gold)"
                onChange={setVoicePitch}
                format={(v) => v > 0 ? `+${v.toFixed(1)}` : `${v.toFixed(1)}`}
              />

              <label className="vp-select-label">
                Accent
                <select value={accent} onChange={(e) => setAccent(e.target.value)} className="vp-select">
                  {ACCENTS.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </label>

              <label className="vp-select-label">
                Language
                <select value={language} onChange={(e) => setLanguage(e.target.value)} className="vp-select">
                  {LANGUAGES.map((lang) => (
                    <option key={lang} value={lang}>
                      {lang}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {/* Active Session */}
            <div className="vp-panel-section">
              <SectionLabel tone="gold" badge={recording ? <LiveBadge label="RECORDING" /> : <LiveBadge variant="idle" label="IDLE" />}>
                ACTIVE SESSION
              </SectionLabel>

              <div className="vp-transcription-display">
                {transcription || <span className="vp-transcription-placeholder">No transcription yet. Start recording to see real-time text.</span>}
              </div>
            </div>

            {/* Recognition Quality */}
            <div className="vp-panel-section">
              <SectionLabel tone="gold">RECOGNITION QUALITY</SectionLabel>

              <div className="vp-quality-metrics">
                <div className="vp-quality-metric">
                  <span className="vp-quality-metric__label">Accuracy</span>
                  <div className="vp-quality-metric__bar">
                    <div
                      className="vp-quality-metric__fill"
                      style={{ width: `${accuracy * 100}%`, background: 'var(--nx-gold)' }}
                    />
                  </div>
                  <span className="vp-quality-metric__value">{Math.round(accuracy * 100)}%</span>
                </div>

                <div className="vp-quality-metric">
                  <span className="vp-quality-metric__label">Confidence</span>
                  <StatusPill label={`${Math.round(confidence * 100)}%`} tone={confidence > 0.9 ? 'success' : confidence > 0.7 ? 'cool' : 'warn'} dot={false} />
                </div>

                <div className="vp-quality-metric">
                  <span className="vp-quality-metric__label">Latency</span>
                  <span className="vp-quality-metric__value vp-mono">{Math.round(latency)}ms</span>
                </div>
              </div>
            </div>

            {/* Control Buttons */}
            <div className="vp-control-buttons">
              <HexButton
                full
                variant={recording ? 'danger' : 'primary'}
                onClick={recording ? handleStopRecording : handleStartRecording}
                icon={recording ? '⏹' : '⏺'}
              >
                {recording ? 'STOP RECORDING' : 'START RECORDING'}
              </HexButton>

              <HexButton full variant="ghost" onClick={handleClearTranscript} disabled={!transcription}>
                CLEAR TRANSCRIPT
              </HexButton>

              <HexButton full variant="ghost" onClick={handleExportTranscript} disabled={!transcription}>
                EXPORT TRANSCRIPT
              </HexButton>
            </div>
          </Panel>
        </div>
      )}
    </div>
  )
}
