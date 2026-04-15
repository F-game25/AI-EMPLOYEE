import { useState, useEffect, useCallback } from 'react'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

// ── Label maps ────────────────────────────────────────────────────────────────

const SYSTEM_PROFILE_LABELS = {
  default_futuristic: 'Default Futuristic',
  minimal_assistant:  'Minimal Assistant',
  system_core:        'System Core',
  stealth_mode:       'Stealth Mode',
}

const CUSTOMER_PROFILE_LABELS = {
  customer_default:       'Default',
  customer_friendly:      'Friendly',
  customer_professional:  'Professional',
  customer_fast_response: 'Fast Response',
}

const TONE_LABELS = {
  futuristic:   'Futuristic',
  neutral:      'Neutral',
  calm:         'Calm',
  sharp:        'Sharp',
  warm:         'Warm',
  professional: 'Professional',
}

const VERBOSITY_LABELS = {
  0: 'Silent',
  1: 'Critical Only',
  2: 'Important Events',
  3: 'Normal',
  4: 'Verbose',
}

const SYSTEM_EVENT_LABELS = {
  system_boot:        'Boot Greeting',
  task_created:       'Task Assigned',
  task_completed:     'Task Completed',
  error_detected:     'Errors',
  ai_learning_update: 'AI Learning Updates',
}

const CUSTOMER_EVENT_LABELS = {
  incoming_support:  'Incoming Support Request',
  outbound_call:     'Outbound Calls',
  followup_reminder: 'Follow-up Reminders',
}

// ── Reusable sub-components ───────────────────────────────────────────────────

function SectionCard({ title, children, accent }) {
  return (
    <div
      className="ds-card"
      style={{
        padding: 'var(--space-4)',
        marginBottom: 'var(--space-4)',
        borderTop: accent ? `2px solid ${accent}` : undefined,
      }}
    >
      <h3 style={{
        fontSize: '13px',
        fontWeight: 500,
        color: 'var(--text-muted)',
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        marginBottom: 'var(--space-4)',
      }}>
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
          width: '44px', height: '24px', borderRadius: '12px', border: 'none',
          background: value ? 'var(--gold)' : 'var(--border-subtle)',
          position: 'relative', cursor: 'pointer', transition: 'background 200ms', flexShrink: 0,
        }}
        aria-checked={value}
        role="switch"
      >
        <span style={{
          position: 'absolute', top: '3px', left: value ? '22px' : '3px',
          width: '18px', height: '18px', borderRadius: '50%',
          background: 'var(--bg-base)', transition: 'left 200ms',
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
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--gold)' }}
      />
    </div>
  )
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-5)' }}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          style={{
            padding: 'var(--space-2) var(--space-4)',
            borderRadius: 'var(--radius-md)',
            border: `1px solid ${active === tab.id ? 'var(--gold)' : 'var(--border-subtle)'}`,
            background: active === tab.id ? 'rgba(212,175,55,0.08)' : 'transparent',
            color: active === tab.id ? 'var(--gold)' : 'var(--text-secondary)',
            fontSize: '13px',
            fontWeight: 500,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

// ── System voice tab ──────────────────────────────────────────────────────────

function SystemVoiceTab({ cfg, profiles, tones, saving, patch }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-4)' }}>

      <SectionCard title="Voice Engine">
        <ToggleSwitch label="Enable Voice" value={cfg.enabled} onChange={(v) => patch({ enabled: v })} />
        <div style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>
            Voice Profile
          </div>
          <select
            value={cfg.profile || 'default_futuristic'}
            onChange={(e) => patch({ profile: e.target.value })}
            disabled={saving}
            style={{
              width: '100%', padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)',
              background: 'var(--bg-elevated)', color: 'var(--text-primary)',
              fontSize: '13px', fontFamily: 'inherit', cursor: 'pointer',
            }}
          >
            {profiles.map((p) => (
              <option key={p} value={p}>{SYSTEM_PROFILE_LABELS[p] || p}</option>
            ))}
          </select>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            {cfg.profile === 'default_futuristic' && 'Precise, robotic, futuristic — default.'}
            {cfg.profile === 'minimal_assistant'  && 'Soft, measured, minimal interruptions.'}
            {cfg.profile === 'system_core'         && 'Deep, authoritative, low-pitch core voice.'}
            {cfg.profile === 'stealth_mode'        && 'Very quiet. Minimal speech.'}
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Verbosity">
        <Slider
          label="Level"
          value={cfg.verbosity ?? 3}
          min={0} max={4} step={1}
          format={(v) => `${v} — ${VERBOSITY_LABELS[v] || 'Normal'}`}
          onChange={(v) => patch({ verbosity: v })}
        />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '4px', marginTop: 'var(--space-2)' }}>
          {[0, 1, 2, 3, 4].map((lvl) => (
            <div
              key={lvl}
              onClick={() => patch({ verbosity: lvl })}
              style={{
                padding: '6px 4px', borderRadius: 'var(--radius-sm)', textAlign: 'center',
                border: `1px solid ${(cfg.verbosity ?? 3) === lvl ? 'var(--gold)' : 'var(--border-subtle)'}`,
                background: (cfg.verbosity ?? 3) === lvl ? 'rgba(212,175,55,0.08)' : 'transparent',
                color: (cfg.verbosity ?? 3) === lvl ? 'var(--gold)' : 'var(--text-muted)',
                fontSize: '11px', cursor: 'pointer',
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

      <SectionCard title="System Events">
        {Object.entries(SYSTEM_EVENT_LABELS).map(([key, label]) => (
          <ToggleSwitch
            key={key} label={label}
            value={cfg.events?.[key] !== false}
            onChange={(v) => patch({ events: { [key]: v } })}
          />
        ))}
      </SectionCard>

      <SectionCard title="Customization">
        <Slider label="Pitch"  value={cfg.pitch  ?? 1.0} min={0.5} max={2.0} step={0.05} format={(v) => v.toFixed(2)} onChange={(v) => patch({ pitch: v })} />
        <Slider label="Speed"  value={cfg.speed  ?? 1.0} min={0.5} max={2.0} step={0.05} format={(v) => v.toFixed(2)} onChange={(v) => patch({ speed: v })} />
        <Slider label="Volume" value={cfg.volume ?? 0.9} min={0}   max={1}   step={0.05} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch({ volume: v })} />
        <div style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>Tone</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--space-2)' }}>
            {tones.map((t) => (
              <button
                key={t}
                onClick={() => patch({ tone: t })}
                style={{
                  padding: 'var(--space-2)', borderRadius: 'var(--radius-sm)',
                  border: `1px solid ${cfg.tone === t ? 'var(--gold)' : 'var(--border-subtle)'}`,
                  background: cfg.tone === t ? 'rgba(212,175,55,0.08)' : 'transparent',
                  color: cfg.tone === t ? 'var(--gold)' : 'var(--text-secondary)',
                  fontSize: '13px', cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {TONE_LABELS[t] || t}
              </button>
            ))}
          </div>
        </div>
      </SectionCard>

    </div>
  )
}

// ── Customer voice tab ────────────────────────────────────────────────────────

function CustomerVoiceTab({ cfg, customerProfiles, customerTones, saving, patch, testCustomer, testStatus }) {
  const cust = cfg.customer || {}

  const patchCust = useCallback((update) => {
    patch({ customer: update })
  }, [patch])

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-4)' }}>

      <SectionCard title="Customer Channel" accent="var(--info)">
        <ToggleSwitch
          label="Enable Customer Voice"
          value={cust.enabled || false}
          onChange={(v) => patchCust({ enabled: v })}
        />
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 'var(--space-2) 0 var(--space-3)' }}>
          Natural, warm, human-like voice for customer interactions.
        </div>
        <div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>
            Voice Profile
          </div>
          <select
            value={cust.profile || 'customer_default'}
            onChange={(e) => patchCust({ profile: e.target.value })}
            disabled={saving}
            style={{
              width: '100%', padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)',
              background: 'var(--bg-elevated)', color: 'var(--text-primary)',
              fontSize: '13px', fontFamily: 'inherit', cursor: 'pointer',
            }}
          >
            {customerProfiles.map((p) => (
              <option key={p} value={p}>{CUSTOMER_PROFILE_LABELS[p] || p}</option>
            ))}
          </select>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            {cust.profile === 'customer_default'       && 'Neutral, natural — good for most interactions.'}
            {cust.profile === 'customer_friendly'      && 'Warm and approachable tone.'}
            {cust.profile === 'customer_professional'  && 'Formal, measured, business-appropriate.'}
            {cust.profile === 'customer_fast_response' && 'Slightly faster pace — ideal for quick queries.'}
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Customer Voice Settings" accent="var(--info)">
        <Slider
          label="Speed"
          value={cust.speed ?? 1.0}
          min={0.5} max={2.0} step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => patchCust({ speed: v })}
        />
        <Slider
          label="Warmth"
          value={cust.warmth ?? 0.7}
          min={0} max={1} step={0.05}
          format={(v) => `${Math.round(v * 100)}%`}
          onChange={(v) => patchCust({ warmth: v })}
        />
        <Slider
          label="Formality"
          value={cust.formality ?? 0.5}
          min={0} max={1} step={0.05}
          format={(v) => `${Math.round(v * 100)}%`}
          onChange={(v) => patchCust({ formality: v })}
        />

        <div style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>Tone</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--space-2)' }}>
            {customerTones.map((t) => (
              <button
                key={t}
                onClick={() => patchCust({ tone: t })}
                style={{
                  padding: 'var(--space-2)', borderRadius: 'var(--radius-sm)',
                  border: `1px solid ${(cust.tone || 'warm') === t ? 'var(--info)' : 'var(--border-subtle)'}`,
                  background: (cust.tone || 'warm') === t ? 'rgba(59,130,246,0.08)' : 'transparent',
                  color: (cust.tone || 'warm') === t ? 'var(--info)' : 'var(--text-secondary)',
                  fontSize: '13px', cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {TONE_LABELS[t] || t}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 'var(--space-3)' }}>
          <button
            onClick={testCustomer}
            style={{
              width: '100%', padding: 'var(--space-2) var(--space-4)',
              borderRadius: 'var(--radius-md)', border: '1px solid var(--info)',
              background: 'rgba(59,130,246,0.06)', color: 'var(--info)',
              fontSize: '13px', fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {testStatus || '▶ Test Customer Voice'}
          </button>
        </div>
      </SectionCard>

      <SectionCard title="Call Triggers" accent="var(--info)">
        {Object.entries(CUSTOMER_EVENT_LABELS).map(([key, label]) => (
          <ToggleSwitch
            key={key} label={label}
            value={cust.events?.[key] !== false}
            onChange={(v) => patchCust({ events: { [key]: v } })}
          />
        ))}
        <div style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-1)' }}>
            Max Call Duration
          </div>
          <select
            value={cust.maxCallDurationMs || 600000}
            onChange={(e) => patchCust({ maxCallDurationMs: Number(e.target.value) })}
            style={{
              width: '100%', padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)',
              background: 'var(--bg-elevated)', color: 'var(--text-primary)',
              fontSize: '13px', fontFamily: 'inherit', cursor: 'pointer',
            }}
          >
            <option value={120000}>2 minutes</option>
            <option value={300000}>5 minutes</option>
            <option value={600000}>10 minutes</option>
            <option value={1800000}>30 minutes</option>
          </select>
        </div>
      </SectionCard>

    </div>
  )
}

// ── Pipeline settings tab ─────────────────────────────────────────────────────

function PipelineTab({ pipelineOpts, onPatch, interruptStatus, onInterrupt }) {
  const opts = pipelineOpts || {}

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-4)' }}>

      <SectionCard title="Streaming Pipeline" accent="var(--success)">
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: 'var(--space-3)', lineHeight: 1.5 }}>
          Sentence-level chunk streaming. First sentence plays within ~100ms.
          Remaining chunks chain with micro-pauses so speech sounds natural.
        </div>
        <ToggleSwitch
          label="Pre-roll filler phrases"
          value={opts.preRollEnabled !== false}
          onChange={(v) => onPatch({ preRollEnabled: v })}
        />
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
          Speaks "One moment…" / "Processing…" immediately while a longer response generates.
        </div>
        <Slider
          label="Pre-roll threshold (chunks)"
          value={opts.preRollThreshold ?? 2}
          min={1} max={6} step={1}
          format={(v) => `≥ ${v} sentences`}
          onChange={(v) => onPatch({ preRollThreshold: v })}
        />
      </SectionCard>

      <SectionCard title="Timing" accent="var(--success)">
        <Slider
          label="Micro-pause between sentences"
          value={opts.microPauseMs ?? 80}
          min={0} max={400} step={10}
          format={(v) => `${v} ms`}
          onChange={(v) => onPatch({ microPauseMs: v })}
        />
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
          50–150 ms sounds natural. 0 ms is robotic. 300+ ms is very deliberate.
        </div>
        <Slider
          label="Thinking delay"
          value={opts.thinkingDelayMs ?? 0}
          min={0} max={800} step={50}
          format={(v) => v === 0 ? 'Off' : `${v} ms`}
          onChange={(v) => onPatch({ thinkingDelayMs: v })}
        />
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Artificial pause before first chunk. 0 = instant. Only applied after pre-roll finishes.
        </div>
      </SectionCard>

      <SectionCard title="Interrupt Control" accent="var(--success)">
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: 'var(--space-3)', lineHeight: 1.5 }}>
          Manual override — immediately stop all current speech. In production this
          fires automatically when the VAD detects user speech.
        </div>
        <button
          onClick={onInterrupt}
          style={{
            width: '100%', padding: 'var(--space-2) var(--space-4)',
            borderRadius: 'var(--radius-md)', border: '1px solid var(--error, #ef4444)',
            background: 'rgba(239,68,68,0.06)', color: 'var(--error, #ef4444)',
            fontSize: '13px', fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          {interruptStatus || '⬛ Stop Speech Now'}
        </button>
        <div style={{ marginTop: 'var(--space-4)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500, marginBottom: 'var(--space-2)' }}>
            Future: Real-time VAD + STT
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            VAD and STT stubs are already wired in{' '}
            <code style={{ background: 'var(--bg-base)', padding: '1px 4px', borderRadius: '3px', fontSize: '10px' }}>
              stream_pipeline.js
            </code>
            . When Whisper.cpp is added, replace <code style={{ background: 'var(--bg-base)', padding: '1px 4px', borderRadius: '3px', fontSize: '10px' }}>detectSpeech()</code> and{' '}
            <code style={{ background: 'var(--bg-base)', padding: '1px 4px', borderRadius: '3px', fontSize: '10px' }}>streamTranscribe()</code> bodies.
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Target Latency" accent="var(--success)">
        <div style={{ display: 'grid', gap: 'var(--space-2)' }}>
          {[
            { stage: 'Sentence split', target: '< 1 ms',    note: 'Pure JS, O(n) text' },
            { stage: 'TTS first chunk', target: '50–150 ms', note: 'OS TTS startup' },
            { stage: 'Pipeline feel',   target: '< 300 ms',  note: 'Perceived by humans as instant' },
          ].map(({ stage, target, note }) => (
            <div key={stage} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
            }}>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>{stage}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{note}</div>
              </div>
              <div style={{ fontSize: '13px', color: 'var(--success)', fontWeight: 600, fontVariantNumeric: 'tabular-nums', flexShrink: 0, marginLeft: 'var(--space-3)' }}>
                {target}
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 'var(--space-3)', fontSize: '11px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
          With STT + token streaming, first-word latency drops to ~300–700 ms total.
          STT and token-session API stubs are ready for drop-in integration.
        </div>
      </SectionCard>

    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function VoicePage() {
  const [cfg, setCfg] = useState(null)
  const [pipelineOpts, setPipelineOpts] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [customerProfiles, setCustomerProfiles] = useState([])
  const [tones, setTones] = useState([])
  const [customerTones, setCustomerTones] = useState([])
  const [saving, setSaving] = useState(false)
  const [testStatus, setTestStatus] = useState('')
  const [customerTestStatus, setCustomerTestStatus] = useState('')
  const [saveStatus, setSaveStatus] = useState('')
  const [activeTab, setActiveTab] = useState('system')
  const [interruptStatus, setInterruptStatus] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        const res = await fetch(`${BASE}/api/voice/config`, { signal: controller.signal })
        const data = await res.json()
        setCfg(data.config || {})
        setProfiles(data.profiles || [])
        setCustomerProfiles(data.customer_profiles || [])
        setTones(data.tones || [])
        setCustomerTones(data.customer_tones || [])
        setPipelineOpts(data.pipeline || {})
      } catch (_e) {
        // keep current state
      }
    }
    load()
    return () => controller.abort()
  }, [])

  const patch = useCallback(async (update) => {
    const next = {
      ...cfg,
      ...update,
      events:   update.events   ? { ...cfg.events,   ...update.events   } : cfg.events,
      customer: update.customer ? {
        ...cfg.customer,
        ...update.customer,
        events: update.customer.events
          ? { ...cfg.customer?.events, ...update.customer.events }
          : cfg.customer?.events,
      } : cfg.customer,
    }
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

  const patchPipeline = useCallback(async (update) => {
    setPipelineOpts((prev) => ({ ...prev, ...update }))
    try {
      await fetch(`${BASE}/api/voice/pipeline/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      })
    } catch (_e) {
      // best-effort
    }
  }, [])

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

  const testCustomerVoice = useCallback(async () => {
    setCustomerTestStatus('Testing...')
    try {
      const res = await fetch(`${BASE}/api/voice/calls/test`, { method: 'POST' })
      const data = await res.json()
      setCustomerTestStatus(data.ok ? data.message || 'Done.' : data.message || 'Disabled.')
    } catch (_e) {
      setCustomerTestStatus('Error.')
    }
    setTimeout(() => setCustomerTestStatus(''), 3000)
  }, [])

  const interruptSpeech = useCallback(async () => {
    setInterruptStatus('Stopping…')
    try {
      await fetch(`${BASE}/api/voice/pipeline/interrupt`, { method: 'POST' })
      setInterruptStatus('Stopped.')
    } catch (_e) {
      setInterruptStatus('Error.')
    }
    setTimeout(() => setInterruptStatus(''), 2000)
  }, [])

  if (!cfg) {
    return (
      <div className="page-enter">
        <PageHeader title="Voice" subtitle="Dual-mode TTS engine configuration" />
        <div style={{ color: 'var(--text-muted)', fontSize: '13px', padding: 'var(--space-4)' }}>Loading…</div>
      </div>
    )
  }

  return (
    <div className="page-enter">
      <PageHeader title="Voice" subtitle="Dual-mode TTS · offline · event-driven" />

      {/* Status + system test button */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span className={`status-dot ${cfg.enabled ? 'status-dot--active status-dot--pulse' : 'status-dot--idle'}`} />
          <span style={{ fontSize: '13px', color: cfg.enabled ? 'var(--success)' : 'var(--text-muted)' }}>
            {cfg.enabled ? 'System Voice Active' : 'System Voice Off'}
          </span>
          {cfg.customer?.enabled && (
            <>
              <span style={{ color: 'var(--border-subtle)', margin: '0 var(--space-1)' }}>·</span>
              <span className="status-dot status-dot--active" style={{ background: 'var(--info)' }} />
              <span style={{ fontSize: '13px', color: 'var(--info)' }}>Customer Voice Active</span>
            </>
          )}
          {saveStatus && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'var(--space-2)' }}>
              {saveStatus}
            </span>
          )}
        </div>
        {activeTab === 'system' && (
          <button
            onClick={testVoice}
            style={{
              padding: 'var(--space-2) var(--space-4)', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--gold)', background: 'rgba(212,175,55,0.06)',
              color: 'var(--gold)', fontSize: '13px', fontWeight: 500,
              cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {testStatus || '▶ Test System Voice'}
          </button>
        )}
      </div>

      <TabBar
        tabs={[
          { id: 'system',   label: '◈ System Voice' },
          { id: 'customer', label: '◎ Customer Voice' },
          { id: 'pipeline', label: '⚡ Pipeline' },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      {activeTab === 'system' && (
        <SystemVoiceTab
          cfg={cfg}
          profiles={profiles}
          tones={tones}
          saving={saving}
          patch={patch}
        />
      )}

      {activeTab === 'customer' && (
        <CustomerVoiceTab
          cfg={cfg}
          customerProfiles={customerProfiles}
          customerTones={customerTones}
          saving={saving}
          patch={patch}
          testCustomer={testCustomerVoice}
          testStatus={customerTestStatus}
        />
      )}

      {activeTab === 'pipeline' && (
        <PipelineTab
          pipelineOpts={pipelineOpts}
          onPatch={patchPipeline}
          interruptStatus={interruptStatus}
          onInterrupt={interruptSpeech}
        />
      )}
    </div>
  )
}
