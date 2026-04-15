import { useState, useEffect, useCallback } from 'react'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

const PROFILE_LABELS = {
  default_futuristic: 'Default Futuristic',
  minimal_assistant: 'Minimal Assistant',
  system_core: 'System Core',
  stealth_mode: 'Stealth Mode',
}

const TONE_LABELS = {
  futuristic: 'Futuristic',
  neutral: 'Neutral',
  calm: 'Calm',
  sharp: 'Sharp',
}

const VERBOSITY_LABELS = {
  0: 'Silent',
  1: 'Critical Only',
  2: 'Important Events',
  3: 'Normal',
  4: 'Verbose',
}

const EVENT_LABELS = {
  system_boot: 'Boot Greeting',
  task_created: 'Task Assigned',
  task_completed: 'Task Completed',
  error_detected: 'Errors',
  ai_learning_update: 'AI Learning Updates',
}

function SectionCard({ title, children }) {
  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
      <h3 style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 'var(--space-4)' }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

function ToggleSwitch({ value, onChange, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'var(--space-2) 0' }}>
      <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{label}</span>
      <button
        onClick={() => onChange(!value)}
        style={{
          width: '44px',
          height: '24px',
          borderRadius: '12px',
          border: 'none',
          background: value ? 'var(--gold)' : 'var(--border-subtle)',
          position: 'relative',
          cursor: 'pointer',
          transition: 'background 200ms',
          flexShrink: 0,
        }}
        aria-checked={value}
        role="switch"
      >
        <span style={{
          position: 'absolute',
          top: '3px',
          left: value ? '22px' : '3px',
          width: '18px',
          height: '18px',
          borderRadius: '50%',
          background: 'var(--bg-base)',
          transition: 'left 200ms',
        }} />
      </button>
    </div>
  )
}

function Slider({ label, value, min, max, step = 0.05, format, onChange }) {
  const display = format ? format(value) : value
  return (
    <div style={{ marginBottom: 'var(--space-3)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-1)' }}>
        <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ fontSize: '13px', color: 'var(--gold)', fontVariantNumeric: 'tabular-nums' }}>{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--gold)' }}
      />
    </div>
  )
}

export default function VoicePage() {
  const [cfg, setCfg] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [tones, setTones] = useState([])
  const [saving, setSaving] = useState(false)
  const [testStatus, setTestStatus] = useState('')
  const [saveStatus, setSaveStatus] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        const res = await fetch(`${BASE}/api/voice/config`, { signal: controller.signal })
        const data = await res.json()
        setCfg(data.config || {})
        setProfiles(data.profiles || [])
        setTones(data.tones || [])
      } catch (_e) {
        // keep current state
      }
    }
    load()
    return () => controller.abort()
  }, [])

  const patch = useCallback(async (update) => {
    const next = { ...cfg, ...update }
    if (update.events) next.events = { ...cfg.events, ...update.events }
    setCfg(next)
    setSaving(true)
    setSaveStatus('')
    try {
      const res = await fetch(`${BASE}/api/voice/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      })
      const data = await res.json()
      if (data.ok) {
        setCfg(data.config || next)
        setSaveStatus('Saved.')
      } else {
        setSaveStatus('Error saving.')
      }
    } catch (_e) {
      setSaveStatus('Error saving.')
    }
    setSaving(false)
    setTimeout(() => setSaveStatus(''), 2000)
  }, [cfg])

  const testVoice = useCallback(async () => {
    setTestStatus('Testing...')
    try {
      const res = await fetch(`${BASE}/api/voice/test`, { method: 'POST' })
      const data = await res.json()
      setTestStatus(data.ok ? data.message || 'Done.' : data.message || 'Disabled.')
    } catch (_e) {
      setTestStatus('Error.')
    }
    setTimeout(() => setTestStatus(''), 3000)
  }, [])

  if (!cfg) {
    return (
      <div className="page-enter">
        <PageHeader title="Voice" subtitle="Futuristic TTS engine configuration" />
        <div style={{ color: 'var(--text-muted)', fontSize: '13px', padding: 'var(--space-4)' }}>Loading…</div>
      </div>
    )
  }

  return (
    <div className="page-enter">
      <PageHeader title="Voice" subtitle="Futuristic TTS engine · offline · event-driven" />

      {/* Status bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span className={`status-dot ${cfg.enabled ? 'status-dot--active status-dot--pulse' : 'status-dot--idle'}`} />
          <span style={{ fontSize: '13px', color: cfg.enabled ? 'var(--success)' : 'var(--text-muted)' }}>
            {cfg.enabled ? 'Voice Active' : 'Voice Disabled'}
          </span>
          {saveStatus && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'var(--space-2)' }}>
              {saveStatus}
            </span>
          )}
        </div>
        <button
          onClick={testVoice}
          style={{
            padding: 'var(--space-2) var(--space-4)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--gold)',
            background: 'rgba(212,175,55,0.06)',
            color: 'var(--gold)',
            fontSize: '13px',
            fontWeight: 500,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          {testStatus || '▶ Test Voice'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-4)' }}>

        {/* Master switch + profile */}
        <SectionCard title="Voice Engine">
          <ToggleSwitch
            label="Enable Voice"
            value={cfg.enabled}
            onChange={(v) => patch({ enabled: v })}
          />

          <div style={{ marginTop: 'var(--space-3)' }}>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>
              Voice Profile
            </div>
            <select
              value={cfg.profile || 'default_futuristic'}
              onChange={(e) => patch({ profile: e.target.value })}
              disabled={saving}
              style={{
                width: '100%',
                padding: 'var(--space-2) var(--space-3)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                fontSize: '13px',
                fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              {profiles.map((p) => (
                <option key={p} value={p}>{PROFILE_LABELS[p] || p}</option>
              ))}
            </select>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
              {cfg.profile === 'default_futuristic' && 'Precise, robotic, futuristic — default.'}
              {cfg.profile === 'minimal_assistant' && 'Soft, measured, minimal interruptions.'}
              {cfg.profile === 'system_core' && 'Deep, authoritative, low-pitch core voice.'}
              {cfg.profile === 'stealth_mode' && 'Very quiet. Minimal speech.'}
            </div>
          </div>
        </SectionCard>

        {/* Verbosity */}
        <SectionCard title="Verbosity">
          <Slider
            label="Level"
            value={cfg.verbosity ?? 3}
            min={0}
            max={4}
            step={1}
            format={(v) => `${v} — ${VERBOSITY_LABELS[v] || 'Normal'}`}
            onChange={(v) => patch({ verbosity: v })}
          />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '4px', marginTop: 'var(--space-2)' }}>
            {[0, 1, 2, 3, 4].map((lvl) => (
              <div
                key={lvl}
                onClick={() => patch({ verbosity: lvl })}
                style={{
                  padding: '6px 4px',
                  borderRadius: 'var(--radius-sm)',
                  border: `1px solid ${(cfg.verbosity ?? 3) === lvl ? 'var(--gold)' : 'var(--border-subtle)'}`,
                  background: (cfg.verbosity ?? 3) === lvl ? 'rgba(212,175,55,0.08)' : 'transparent',
                  color: (cfg.verbosity ?? 3) === lvl ? 'var(--gold)' : 'var(--text-muted)',
                  fontSize: '11px',
                  textAlign: 'center',
                  cursor: 'pointer',
                }}
              >
                {lvl}
              </div>
            ))}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
            {VERBOSITY_LABELS[cfg.verbosity ?? 3]}
          </div>
        </SectionCard>

        {/* Event toggles */}
        <SectionCard title="Events">
          {Object.entries(EVENT_LABELS).map(([key, label]) => (
            <ToggleSwitch
              key={key}
              label={label}
              value={cfg.events?.[key] !== false}
              onChange={(v) => patch({ events: { [key]: v } })}
            />
          ))}
        </SectionCard>

        {/* Voice customization */}
        <SectionCard title="Customization">
          <Slider
            label="Pitch"
            value={cfg.pitch ?? 1.0}
            min={0.5}
            max={2.0}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(v) => patch({ pitch: v })}
          />
          <Slider
            label="Speed"
            value={cfg.speed ?? 1.0}
            min={0.5}
            max={2.0}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(v) => patch({ speed: v })}
          />
          <Slider
            label="Volume"
            value={cfg.volume ?? 0.9}
            min={0}
            max={1}
            step={0.05}
            format={(v) => `${Math.round(v * 100)}%`}
            onChange={(v) => patch({ volume: v })}
          />

          <div style={{ marginTop: 'var(--space-3)' }}>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>
              Tone
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--space-2)' }}>
              {tones.map((t) => (
                <button
                  key={t}
                  onClick={() => patch({ tone: t })}
                  style={{
                    padding: 'var(--space-2)',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${cfg.tone === t ? 'var(--gold)' : 'var(--border-subtle)'}`,
                    background: cfg.tone === t ? 'rgba(212,175,55,0.08)' : 'transparent',
                    color: cfg.tone === t ? 'var(--gold)' : 'var(--text-secondary)',
                    fontSize: '13px',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  {TONE_LABELS[t] || t}
                </button>
              ))}
            </div>
          </div>
        </SectionCard>

      </div>
    </div>
  )
}
