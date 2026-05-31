import { useState, useEffect, useRef } from 'react'
import api from '../../../api/client'
import { useUpdateCheck } from '../../../hooks/useUpdateCheck'
import { useAppStore } from '../../../store/appStore'
import { NxField, NxSaveBtn, useSave } from './controls'

export default function GeneralTab() {
  const setActiveSection = useAppStore(s => s.setActiveSection)
  const [cfg, setCfg] = useState({
    system_name: 'AETERNUS NEXUS',
    operating_mode: 'AUTONOMOUS',
    evolution_mode: 'SAFE',
    log_level: 'INFO',
    max_agents: 15,
  })
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }))
  const { saving, saved, save } = useSave('/api/settings', cfg)

  useEffect(() => {
    api.get('/api/settings').then(d => setCfg(p => ({ ...p, ...d }))).catch(() => {})
  }, [])

  return (
    <div className="nx-tab-content">
      <div className="nx-section">
        <div className="nx-section-label">SYSTEM IDENTITY</div>
        <div className="nx-form-grid">
          <NxField label="SYSTEM NAME">
            <input className="nx-input" value={cfg.system_name} onChange={e => set('system_name', e.target.value)} />
          </NxField>
          <NxField label="OPERATING MODE">
            <select className="nx-input" value={cfg.operating_mode} onChange={e => set('operating_mode', e.target.value)}>
              {['AUTONOMOUS','BALANCED','SUPERVISED','SAFE','MAINTENANCE'].map(m =>
                <option key={m} value={m}>{m}</option>)}
            </select>
          </NxField>
          <NxField label="EVOLUTION MODE">
            <select className="nx-input" value={cfg.evolution_mode} onChange={e => set('evolution_mode', e.target.value)}>
              {['AUTO','SAFE','OFF'].map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </NxField>
          <NxField label="LOG LEVEL">
            <select className="nx-input" value={cfg.log_level} onChange={e => set('log_level', e.target.value)}>
              {['DEBUG','INFO','WARNING','ERROR'].map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </NxField>
          <NxField label="MAX AGENTS">
            <input className="nx-input" type="number" min={1} max={100} value={cfg.max_agents} onChange={e => set('max_agents', +e.target.value)} />
          </NxField>
        </div>
        <NxSaveBtn label="SAVE GENERAL SETTINGS" saving={saving} saved={saved} onClick={save} />
      </div>

      <div className="nx-divider" />
      <div className="nx-section">
        <div className="nx-section-label">ADMIN SETUP</div>
        <p className="nx-help-text">
          Reopen the technical setup wizard to verify runtime, providers, memory, integrations, approval gates, and the safe smoke test.
        </p>
        <button className="nx-save-btn" type="button" onClick={() => setActiveSection('setup')}>
          OPEN SETUP CENTER
        </button>
      </div>

      <div className="nx-divider" />
      <UpdateSection />
    </div>
  )
}

function UpdateSection() {
  const {
    checking, applying, progress, stage, log, error,
    lastChecked, currentCommit, remoteCommit, updateComplete,
    checkForUpdates, applyUpdate,
  } = useUpdateCheck()
  const logRef = useRef(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  const stageLabel = {
    starting: 'Initializing…', fetching: 'Fetching remote…', comparing: 'Comparing versions…',
    applying: 'Applying update…', building: 'Building frontend…', restarting: 'Restarting services…',
    done: 'Complete', error: 'Error', running: 'Running…',
  }

  return (
    <div className="nx-section">
      <div className="nx-section-label">SYSTEM UPDATES</div>
      <div className="nx-update-meta">
        <div className="nx-update-row">
          <span className="nx-update-key">CURRENT COMMIT</span>
          <code className="nx-commit">{currentCommit || '—'}</code>
        </div>
        {remoteCommit && (
          <div className="nx-update-row">
            <span className="nx-update-key">REMOTE COMMIT</span>
            <code className="nx-commit nx-commit--remote">{remoteCommit}</code>
          </div>
        )}
        {lastChecked && (
          <div className="nx-update-row">
            <span className="nx-update-key">LAST CHECKED</span>
            <span className="nx-update-val">{new Date(lastChecked).toLocaleTimeString()}</span>
          </div>
        )}
        {updateComplete && <div className="nx-badge nx-badge--ok">✓ UPDATE APPLIED — reload to activate</div>}
        {error && <div className="nx-badge nx-badge--err">✗ {error}</div>}
      </div>

      {applying && (
        <div className="nx-progress-wrap">
          <div className="nx-progress-bar"><div className="nx-progress-fill" style={{ width: `${progress}%` }} /></div>
          <span className="nx-progress-label">{stageLabel[stage] || stage || '…'} — {progress}%</span>
        </div>
      )}

      {log.length > 0 && (
        <div className="nx-log" ref={logRef}>
          {log.map((e, i) => (
            <div key={i} className={`nx-log-line nx-log-line--${e.level || 'info'}`}>
              <span className="nx-log-stage">[{e.stage || '—'}]</span>{e.text}
            </div>
          ))}
        </div>
      )}

      <div className="nx-btn-row">
        <button className="nx-save-btn" onClick={checkForUpdates} disabled={checking || applying}>
          {checking ? 'CHECKING…' : 'CHECK FOR UPDATES'}
        </button>
        <button className="nx-save-btn nx-save-btn--green" onClick={applyUpdate} disabled={applying || checking}>
          {applying ? `UPDATING… ${progress}%` : 'UPDATE SYSTEM NOW'}
        </button>
        {updateComplete && (
          <button className="nx-save-btn nx-save-btn--reload" onClick={() => window.location.reload()}>
            RELOAD NOW →
          </button>
        )}
      </div>
    </div>
  )
}
