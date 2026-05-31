import { useState, useEffect } from 'react'
import api from '../../../api/client'
import { NxToggle, NxField, NxSaveBtn, SafetyConfirmModal, useSave } from './controls'

const RED_ZONE_ACTIONS = [
  { id: 'reset-state',         label: 'RESET ALL STATE',        endpoint: 'POST /api/admin/reset-state',             warning: 'Resets all runtime state files. This cannot be undone.', confirmText: 'RESET ALL STATE', risk: 'critical' },
  { id: 'wipe-memory',         label: 'WIPE MEM0 MEMORY',       endpoint: 'DELETE /api/neural-brain/memory/all',      warning: 'Permanently deletes all stored memories. Cannot be undone.', confirmText: 'WIPE MEM0 MEMORY', risk: 'critical' },
  { id: 'factory-reset',       label: 'FACTORY RESET',          endpoint: 'POST /api/admin/factory-reset',           warning: 'Complete system factory reset. All data will be lost.', confirmText: 'FACTORY RESET', risk: 'critical' },
  { id: 'evolution-rollback',  label: 'EVOLUTION ROLLBACK',     endpoint: 'POST /api/evolution/rollback',            warning: 'Rolls back all applied evolution patches.', confirmText: 'EVOLUTION ROLLBACK', risk: 'high' },
  { id: 'invalidate-sessions', label: 'INVALIDATE SESSIONS',    endpoint: 'POST /api/admin/sessions/invalidate-all', warning: 'Logs out all active users immediately.', confirmText: 'INVALIDATE SESSIONS', risk: 'high' },
  { id: 'flush-telemetry',     label: 'FLUSH TELEMETRY',        endpoint: 'POST /api/neural-brain/telemetry/flush',  warning: 'Clears all queued telemetry data.', confirmText: 'FLUSH TELEMETRY', risk: 'medium' },
]

const EVO_MODES = [
  { id: 'OFF',  label: 'Off',  desc: 'No self-modification. System is frozen.' },
  { id: 'SAFE', label: 'Safe', desc: 'Proposes patches — requires human approval before applying.' },
  { id: 'AUTO', label: 'Auto', desc: 'Autonomously generates, validates, and deploys safe patches.' },
]

function EvolutionModePanel() {
  const [status, setStatus] = useState(null)
  const [mode, setMode] = useState(null)
  const load = () => api.get('/api/evolution/status').then(d => { setStatus(d); setMode(d.mode || 'OFF') }).catch(() => setMode('OFF'))
  useEffect(() => { load() }, [])
  const choose = async (m) => {
    if (m === mode) return
    if (m === 'AUTO' && !window.confirm('Enable AUTO evolution? The system will autonomously generate and deploy code patches without human approval.')) return
    setMode(m)
    try { const d = await api.post('/api/evolution/mode', { mode: m }); setMode(d.mode || m); load() } catch { /* */ }
  }
  return (
    <div className="nx-section">
      <div className="nx-section-label">SELF-EVOLUTION</div>
      <div className="nx-evo-stats">
        <span>Loop: <b>{status?.running ? 'RUNNING' : 'IDLE'}</b></span>
        <span>Patches applied: <b>{status?.patches_applied ?? 0}</b></span>
        {status?.patches_proposed != null && <span>Proposed: <b>{status.patches_proposed}</b></span>}
      </div>
      <div className="nx-render-opts" role="radiogroup" aria-label="Evolution mode">
        {EVO_MODES.map(m => (
          <button key={m.id} type="button" role="radio" aria-checked={mode === m.id}
            className={`nx-render-opt ${mode === m.id ? 'nx-render-opt--active' : ''}`} onClick={() => choose(m.id)}>
            <span className="nx-render-opt__title">{m.label}{mode === m.id && ' ✓'}</span>
            <span className="nx-render-opt__desc">{m.desc}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function AdvancedTab() {
  const [cfg, setCfg] = useState({ strict_pipeline: false, hitl_gate: true, data_retention: 30 })
  const [showRawJson, setShowRawJson] = useState(false)
  const [rawSettings, setRawSettings] = useState(null)
  const [pending, setPending] = useState(null)
  const [results, setResults] = useState({})
  const [downloadMsg, setDownloadMsg] = useState(null)
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings', cfg)

  useEffect(() => {
    api.get('/api/settings').then(d => setCfg(p => ({ ...p, ...d }))).catch(() => {})
  }, [])

  const toggleRaw = async () => {
    if (!showRawJson && !rawSettings) {
      const d = await api.get('/api/settings').catch(() => null)
      setRawSettings(d)
    }
    setShowRawJson(v => !v)
  }

  const downloadLogs = async () => {
    try {
      const resp = await fetch('/api/logs', { headers: { Authorization: `Bearer ${sessionStorage.getItem('ai_jwt') || ''}` } })
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = 'python-backend.log'; a.click()
      URL.revokeObjectURL(url)
      setDownloadMsg('✓ Downloaded')
    } catch { setDownloadMsg('✗ Failed') }
    setTimeout(() => setDownloadMsg(null), 2500)
  }

  const executeAction = async (action, safety) => {
    setPending(null)
    try {
      const result = await api.post('/api/admin/safety-action', {
        action_id: action.id,
        endpoint: action.endpoint,
        reason: safety.reason,
        confirmation: safety.confirmation,
        execution_mode: 'staged',
      })
      setResults(p => ({ ...p, [action.id]: `✓ Staged · ${result.audit_id || result.trace_id}` }))
    } catch (e) {
      setResults(p => ({ ...p, [action.id]: `✗ ${e.message || 'Error'}` }))
    }
  }

  return (
    <div className="nx-tab-content">
      {pending && <SafetyConfirmModal action={pending} onConfirm={executeAction} onCancel={() => setPending(null)} />}

      <EvolutionModePanel />
      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">PIPELINE CONTROLS</div>
        <div className="nx-toggle-list">
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">STRICT PIPELINE MODE</span>
              <span className="nx-toggle-desc">Sets STRICT_PIPELINE=1 — disables graceful fallbacks. Use in CI/staging to surface real failures.</span>
            </div>
            <NxToggle checked={cfg.strict_pipeline} onChange={v => set('strict_pipeline', v)} />
          </div>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">HITL GATE</span>
              <span className="nx-toggle-desc">Require human approval before high-risk agents (lead-hunter, qualification, data-analyst) execute sensitive operations.</span>
            </div>
            <NxToggle checked={cfg.hitl_gate} onChange={v => set('hitl_gate', v)} />
          </div>
        </div>

        <div className="nx-divider" />

        <div className="nx-form-grid">
          <NxField label="DATA RETENTION (DAYS)">
            <input className="nx-input" type="number" min={1} max={365} value={cfg.data_retention} onChange={e => set('data_retention', +e.target.value)} />
          </NxField>
        </div>
        <NxSaveBtn label="SAVE ADVANCED" saving={saving} saved={saved} onClick={save} />
      </div>

      <div className="nx-divider" />

      <div className="nx-section">
        <div className="nx-section-label">DIAGNOSTICS</div>
        <div className="nx-btn-row">
          <button className="nx-save-btn nx-save-btn--outline" onClick={downloadLogs}>
            ⬇ DOWNLOAD LOGS
          </button>
          {downloadMsg && <span className={`nx-test-result ${downloadMsg.startsWith('✓') ? 'nx-test-result--ok' : 'nx-test-result--fail'}`}>{downloadMsg}</span>}
        </div>
        <div className="nx-toggle-list" style={{ marginTop: 16 }}>
          <div className="nx-toggle-row">
            <div className="nx-toggle-info">
              <span className="nx-toggle-title">DEVELOPER MODE</span>
              <span className="nx-toggle-desc">Reveal raw JSON dump of current settings object</span>
            </div>
            <NxToggle checked={showRawJson} onChange={toggleRaw} />
          </div>
        </div>
        {showRawJson && rawSettings && (
          <pre className="nx-raw-json">{JSON.stringify(rawSettings, null, 2)}</pre>
        )}
      </div>

      <div className="nx-divider" />

      <div className="nx-section nx-section--danger">
        <div className="nx-section-label nx-section-label--danger">DANGER ZONE</div>
        <div className="nx-danger-warning">
          These actions are staged through the admin safety endpoint first. They require typed confirmation, a reason, a countdown, and an audit record.
        </div>
        <div className="nx-redzone-list">
          {RED_ZONE_ACTIONS.map(a => (
            <div key={a.id} className="nx-redzone-row">
              <div className="nx-redzone-info">
                <span className="nx-redzone-label">{a.label}</span>
                <span className="nx-redzone-desc">{a.warning}</span>
              </div>
              <div className="nx-redzone-right">
                {results[a.id] && (
                  <span className={`nx-test-result ${results[a.id].startsWith('✓') ? 'nx-test-result--ok' : 'nx-test-result--fail'}`}>
                    {results[a.id]}
                  </span>
                )}
                <button className="nx-save-btn nx-save-btn--danger" onClick={() => setPending(a)}>
                  {a.label}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
