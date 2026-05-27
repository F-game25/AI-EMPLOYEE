import { useState, useEffect, useCallback } from 'react'
import { Panel, Badge, StatCard } from '../ui/primitives'
import { API_URL } from '../../config/api'

const BASE = API_URL

const MODES = [
  { id: 'OFF',  label: 'Off',  color: 'rgba(255,255,255,0.3)', desc: 'No self-modification. System is frozen.' },
  { id: 'SAFE', label: 'Safe', color: '#E5C76B',               desc: 'Proposes patches — requires human approval before applying.' },
  { id: 'AUTO', label: 'Auto', color: '#22C55E',               desc: 'Automatically generates, validates, and deploys safe patches.' },
]

function ModeCard({ mode, active, onSelect, disabled }) {
  return (
    <div
      onClick={() => !disabled && onSelect(mode.id)}
      style={{ padding: '14px 16px', borderRadius: 10, border: `1px solid ${active ? mode.color + '55' : 'rgba(255,255,255,0.08)'}`, background: active ? `${mode.color}10` : 'rgba(255,255,255,0.02)', cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1, transition: 'all 0.2s' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: active ? mode.color : 'rgba(255,255,255,0.15)', boxShadow: active ? `0 0 8px ${mode.color}` : 'none' }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: active ? mode.color : 'var(--text-primary, #F0E9D2)' }}>{mode.label}</span>
        {active && <Badge color={mode.color} label="ACTIVE" />}
      </div>
      <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{mode.desc}</div>
    </div>
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
    setConfirm(null)
    setChanging(true)
    setError(null)
    try {
      const token = localStorage.getItem('auth_token') || ''
      const r = await fetch(`${BASE}/api/evolution/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, flexShrink: 0 }}>
        <StatCard label="Mode" value={mode} color={activeMode.color} sub="current evolution mode" />
        <StatCard label="Running" value={status?.running ? 'Yes' : 'No'} color={status?.running ? '#22C55E' : 'rgba(255,255,255,0.3)'} sub="evolution loop active" />
        <StatCard label="Patches" value={status?.patches_applied ?? 0} color="#20D6C7" sub="applied this session" />
      </div>

      {error && (
        <div style={{ padding: '10px 14px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#EF4444', fontSize: 12 }}>{error}</div>
      )}

      {confirm && (
        <div style={{ padding: '14px 18px', borderRadius: 10, background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.3)', display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#EF4444', marginBottom: 4 }}>Enable AUTO evolution?</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>The system will autonomously generate and deploy code patches without human approval.</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setConfirm(null)} style={{ padding: '7px 14px', borderRadius: 7, border: '1px solid rgba(255,255,255,0.15)', background: 'transparent', color: 'rgba(255,255,255,0.5)', fontSize: 12, cursor: 'pointer' }}>Cancel</button>
            <button onClick={() => applyMode(confirm)} style={{ padding: '7px 14px', borderRadius: 7, border: '1px solid rgba(239,68,68,0.4)', background: 'rgba(239,68,68,0.12)', color: '#EF4444', fontSize: 12, cursor: 'pointer', fontWeight: 600 }}>Confirm AUTO</button>
          </div>
        </div>
      )}

      <Panel title="Evolution Mode">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
          {MODES.map(m => (
            <ModeCard key={m.id} mode={m} active={mode === m.id} onSelect={requestMode} disabled={changing} />
          ))}
        </div>
      </Panel>

      <Panel title="Status">
        {loading ? (
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)' }}>Loading…</div>
        ) : status ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Object.entries(status).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: 12 }}>
                <span style={{ color: 'rgba(255,255,255,0.45)', fontFamily: 'monospace', fontSize: 11 }}>{k}</span>
                <span style={{ color: 'var(--text-primary, #F0E9D2)', fontFamily: 'monospace', fontSize: 11 }}>{JSON.stringify(v)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', fontStyle: 'italic' }}>Evolution status unavailable — Python backend may be offline.</div>
        )}
      </Panel>

      <Panel title="How It Works">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12, color: 'rgba(255,255,255,0.5)', lineHeight: 1.6 }}>
          <div><strong style={{ color: 'var(--text-primary, #F0E9D2)' }}>SAFE mode:</strong> The system proposes code patches via Ascend Forge. Each patch goes through sandbox testing and appears in the Forge queue for human approval before being applied.</div>
          <div><strong style={{ color: 'var(--text-primary, #F0E9D2)' }}>AUTO mode:</strong> The system autonomously detects improvement opportunities, generates patches, validates them in the sandbox, and deploys if validation passes — no human step.</div>
          <div><strong style={{ color: 'var(--text-primary, #F0E9D2)' }}>Engine:</strong> <code style={{ fontFamily: 'monospace', fontSize: 11 }}>runtime/core/self_evolution/</code> — patch_generator → patch_validator → safe_deployer pipeline.</div>
        </div>
      </Panel>
    </div>
  )
}
