import { useState, useEffect, useCallback } from 'react'
import { Panel, KPITile, StatusPill, HexButton, SectionLabel, LiveBadge } from '../nexus-ui'
import { API_URL } from '../../config/api'
import './EvolutionPage.css'

const BASE = API_URL

const MODES = [
  { id:'OFF',  label:'Off',  tone:'idle',    desc:'No self-modification. System is frozen.' },
  { id:'SAFE', label:'Safe', tone:'gold',    desc:'Proposes patches — requires human approval before applying.' },
  { id:'AUTO', label:'Auto', tone:'success', desc:'Automatically generates, validates, and deploys safe patches.' },
]

function ModeCard({ mode, active, onSelect, disabled }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onSelect(mode.id)}
      disabled={disabled}
      className={`evo-mode evo-mode--${mode.tone} ${active ? 'is-active' : ''}`}
    >
      <div className="evo-mode__head">
        <span className={`evo-mode__dot evo-mode__dot--${mode.tone}`} />
        <span className="evo-mode__label">{mode.label}</span>
        {active && <StatusPill tone={mode.tone} label="ACTIVE" dot={false} size="sm" />}
      </div>
      <div className="evo-mode__desc">{mode.desc}</div>
    </button>
  )
}

export default function EvolutionPage() {
  const [status, setStatus]     = useState(null)
  const [mode, setMode]         = useState('OFF')
  const [loading, setLoading]   = useState(true)
  const [changing, setChanging] = useState(false)
  const [error, setError]       = useState(null)
  const [confirm, setConfirm]   = useState(null)

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/evolution/status`)
      const d = await r.json()
      setStatus(d)
      setMode(d.mode || 'OFF')
    } catch { setStatus(null) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t) }, [load])

  const applyMode = useCallback(async (newMode) => {
    setConfirm(null); setChanging(true); setError(null)
    try {
      const token = localStorage.getItem('auth_token') || ''
      const r = await fetch(`${BASE}/api/evolution/mode`, {
        method:'POST',
        headers:{ 'Content-Type':'application/json', Authorization:`Bearer ${token}` },
        body: JSON.stringify({ mode: newMode }),
      })
      const d = await r.json()
      setMode(d.mode || newMode)
      await load()
    } catch (e) {
      setError(`Mode change failed: ${e.message}`)
    } finally { setChanging(false) }
  }, [load])

  const requestMode = (newMode) => {
    if (newMode === mode) return
    if (newMode === 'AUTO') { setConfirm(newMode); return }
    applyMode(newMode)
  }

  const activeMode = MODES.find(m => m.id === mode) || MODES[0]

  return (
    <div className="evo-grid">
      <div className="evo-kpis">
        <KPITile icon="◐" iconTone={activeMode.tone === 'idle' ? 'gold' : activeMode.tone}
          label="Mode" value={mode} sub="Current evolution mode" accent />
        <KPITile icon="◷" iconTone={status?.running ? 'success' : 'cool'}
          label="Loop" value={status?.running ? 'RUNNING' : 'IDLE'} sub="Evolution loop" />
        <KPITile icon="✦" iconTone="gold"
          label="Patches" value={status?.patches_applied ?? 0} sub="Applied this session" />
      </div>

      {error && (
        <div className="evo-error">
          <span className="evo-error__dot" />
          <span>{error}</span>
        </div>
      )}

      {confirm && (
        <div className="evo-confirm">
          <div className="evo-confirm__body">
            <div className="evo-confirm__title">Enable AUTO evolution?</div>
            <div className="evo-confirm__sub">
              The system will autonomously generate and deploy code patches without human approval.
            </div>
          </div>
          <div className="evo-confirm__cta">
            <HexButton variant="ghost" size="sm" onClick={() => setConfirm(null)}>Cancel</HexButton>
            <HexButton variant="primary" size="sm" tone="alert" icon="!" onClick={() => applyMode(confirm)}>
              Confirm AUTO
            </HexButton>
          </div>
        </div>
      )}

      <Panel
        icon="⚙"
        title="Evolution Mode"
        actions={<LiveBadge variant={status?.running ? 'live' : 'idle'} />}
      >
        <div className="evo-modes">
          {MODES.map(m => (
            <ModeCard
              key={m.id}
              mode={m}
              active={mode === m.id}
              onSelect={requestMode}
              disabled={changing}
            />
          ))}
        </div>
      </Panel>

      <div className="evo-cols">
        <Panel icon="◈" title="Status">
          {loading ? (
            <div className="evo-empty">Loading…</div>
          ) : status ? (
            <div className="evo-status">
              {Object.entries(status).map(([k, v]) => (
                <div key={k} className="evo-status__row">
                  <span className="evo-status__key">{k}</span>
                  <span className="evo-status__val">{JSON.stringify(v)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="evo-empty evo-empty--alert">
              Evolution status unavailable — Python backend may be offline.
            </div>
          )}
        </Panel>

        <Panel icon="✺" title="How It Works">
          <div className="evo-info">
            <SectionLabel size="sm" tone="gold">Safe Mode</SectionLabel>
            <p>
              The system proposes code patches via Ascend Forge. Each patch goes through sandbox testing
              and appears in the Forge queue for human approval before being applied.
            </p>
            <SectionLabel size="sm" tone="success" rule>Auto Mode</SectionLabel>
            <p>
              The system autonomously detects improvement opportunities, generates patches, validates them
              in the sandbox, and deploys if validation passes — no human step.
            </p>
            <SectionLabel size="sm" tone="cool" rule>Engine</SectionLabel>
            <p>
              <code className="evo-code">runtime/core/self_evolution/</code> — patch_generator → patch_validator → safe_deployer pipeline.
            </p>
          </div>
        </Panel>
      </div>
    </div>
  )
}
