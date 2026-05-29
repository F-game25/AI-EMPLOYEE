import { useState, useEffect, useCallback } from 'react'
import { SectionLabel, EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import api from '../../../api/client'

const STATUS_COLORS = {
  CREATED: '#6b7280', VALIDATING_DATASET: '#f59e0b', READY: '#3b82f6',
  TRAINING: '#a78bfa', EVALUATING: '#a78bfa', FAILED: '#ef4444',
  COMPLETED: '#22c55e', PROMOTED: '#22c55e', ROLLED_BACK: '#6b7280',
}
const MV_STATUS_COLORS = {
  CANDIDATE: '#f59e0b', APPROVED: '#3b82f6', ACTIVE: '#22c55e',
  REJECTED: '#ef4444', ROLLED_BACK: '#6b7280',
}

function TrainingSummaryCard({ summary, onRefresh }) {
  const fields = [
    { label: 'Datasets', value: summary.datasets },
    { label: 'Train runs', value: summary.training_runs },
    { label: 'Candidates', value: summary.candidates },
    { label: 'Active', value: summary.active_helpers },
    { label: 'Last score', value: summary.last_eval_score != null ? summary.last_eval_score : '—' },
    { label: 'Failed', value: summary.failed_jobs },
  ]
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)', marginBottom: 8 }}>
      {fields.map(f => (
        <div key={f.label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '4px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: 5, border: '1px solid rgba(255,255,255,0.06)' }}>
          <span style={{ font: '700 14px monospace', color: 'var(--af-text)' }}>{f.value ?? 0}</span>
          <span style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>{f.label}</span>
        </div>
      ))}
      <button className="af-btn af-btn--ghost af-btn--sm" onClick={onRefresh} style={{ marginLeft: 'auto' }}>Refresh</button>
    </div>
  )
}

function CreateRunForm({ project, datasets, modelTypes, methods, onCreated }) {
  const [form, setForm] = useState({ dataset_id: '', model_type: 'risk_classifier', training_method: 'local_classifier' })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function create() {
    if (!form.dataset_id) return toastError('Select a dataset first')
    setBusy(true)
    try {
      const r = await api.forge.training.createRun(project.id, form)
      if (r.ok) { toastSuccess('Training run created'); onCreated(r.training_run) }
      else toastError(r.error || 'Create failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  const sel = { font: '400 10px monospace', padding: '4px 6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted)' }
  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: 12, marginBottom: 10 }}>
      <SectionLabel>NEW TRAINING RUN</SectionLabel>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8, alignItems: 'center' }}>
        <select style={sel} value={form.dataset_id} onChange={e => set('dataset_id', e.target.value)}>
          <option value="">Select dataset…</option>
          {datasets.map(d => <option key={d.dataset_id} value={d.dataset_id}>{d.name} ({d.dataset_type}, {d.record_count})</option>)}
        </select>
        <select style={sel} value={form.model_type} onChange={e => set('model_type', e.target.value)}>
          {modelTypes.map(mt => <option key={mt.id} value={mt.id}>{mt.label}</option>)}
        </select>
        <select style={sel} value={form.training_method} onChange={e => set('training_method', e.target.value)}>
          {methods.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <button className="af-btn af-btn--sm" style={{ background: 'rgba(205,127,50,0.15)', color: 'var(--af-bronze-bright)' }} disabled={busy} onClick={create}>
          {busy ? 'Creating…' : '+ Create'}
        </button>
      </div>
    </div>
  )
}

function TrainingRunCard({ run, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [validation, setValidation] = useState(null)

  async function act(fn, label) {
    setBusy(true)
    try {
      const r = await fn()
      if (r.ok) {
        toastSuccess(`${label} ok`)
        if (r.validation) setValidation(r.validation)
        onChanged()
      } else {
        toastError(r.error || `${label} failed`)
        if (r.validation) setValidation(r.validation)
        else if (r.issues) setValidation({ result: 'failed', issues: r.issues })
        onChanged()
      }
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
        <span style={{ font: '700 10px monospace', color: STATUS_COLORS[run.status] || '#888', textTransform: 'uppercase' }}>{run.status}</span>
        <span style={{ font: '600 11px monospace', color: 'var(--af-text-muted)' }}>{run.model_type}</span>
        <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)' }}>{run.training_method}</span>
        <span style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginLeft: 'auto' }}>{new Date(run.created_at).toLocaleString()}</span>
      </div>
      {run.metrics?.train_accuracy != null && (
        <div style={{ font: '400 10px monospace', color: '#22c55e', marginBottom: 4 }}>train acc: {run.metrics.train_accuracy} · {run.metrics.train_records} recs</div>
      )}
      {run.metrics?.eval && (
        <div style={{ font: '400 10px monospace', color: run.metrics.eval_passed ? '#22c55e' : '#f59e0b', marginBottom: 4 }}>
          eval acc: {run.metrics.eval.accuracy} · {run.metrics.eval_passed ? 'PASSED gate' : 'did not pass'}
        </div>
      )}
      {run.error && <div style={{ font: '400 10px monospace', color: '#ef4444', marginBottom: 4 }}>{run.error}</div>}
      {validation && (
        <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 4, padding: '6px 8px', margin: '4px 0' }}>
          <div style={{ font: '600 9px monospace', color: validation.result === 'passed' ? '#22c55e' : validation.result === 'warn' ? '#f59e0b' : '#ef4444', textTransform: 'uppercase' }}>
            validation: {validation.result} {validation.secret_scan_passed === false && '· SECRET DETECTED'}
          </div>
          {validation.approved_count != null && <div style={{ font: '400 9px monospace', color: 'var(--af-text-dim)' }}>{validation.approved_count} usable / {validation.record_count} records</div>}
          {(validation.issues || []).slice(0, 4).map((iss, i) => <div key={i} style={{ font: '400 9px monospace', color: 'var(--af-text-dim)' }}>• {iss}</div>)}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
        <button className="af-btn af-btn--ghost af-btn--sm" disabled={busy} onClick={() => act(() => api.forge.training.validateRun(run.training_run_id), 'Validate')}>Validate</button>
        {(run.status === 'READY' || run.status === 'CREATED') && (
          <button className="af-btn af-btn--sm" style={{ background: 'rgba(167,139,250,0.15)', color: '#a78bfa' }} disabled={busy} onClick={() => act(() => api.forge.training.startRun(run.training_run_id, { override_too_small: run.status === 'CREATED' }), 'Train')}>Start training</button>
        )}
        {run.status === 'COMPLETED' && (
          <button className="af-btn af-btn--sm" style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6' }} disabled={busy} onClick={() => act(() => api.forge.training.evaluateRun(run.training_run_id), 'Evaluate')}>Run evaluation</button>
        )}
      </div>
    </div>
  )
}

function ModelVersionCard({ mv, onChanged }) {
  const [busy, setBusy] = useState(false)
  const passedEval = (mv.evaluations || []).some(e => e.passed)
  const lastEval = (mv.evaluations || [])[0]

  async function act(fn, label) {
    setBusy(true)
    try {
      const r = await fn()
      if (r.ok) { toastSuccess(`${label} ok`); onChanged() }
      else toastError(r.error || `${label} failed`)
    } catch (e) { toastError(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${MV_STATUS_COLORS[mv.status] || '#555'}33`, borderRadius: 6, padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
        <span style={{ font: '700 10px monospace', color: MV_STATUS_COLORS[mv.status], textTransform: 'uppercase' }}>{mv.status}</span>
        <span style={{ font: '600 11px monospace', color: 'var(--af-text-muted)' }}>{mv.version_label || mv.model_type}</span>
        <span style={{ font: '400 9px monospace', color: 'var(--af-text-dim)' }}>{mv.base_model}</span>
        {mv.eval_score != null && <span style={{ font: '600 10px monospace', color: 'var(--af-text-muted)', marginLeft: 'auto' }}>score {mv.eval_score}</span>}
      </div>
      {lastEval && (
        <div style={{ font: '400 9px monospace', color: lastEval.passed ? '#22c55e' : '#f59e0b', marginBottom: 4 }}>
          eval: {lastEval.passed ? 'PASSED' : 'not passed'}
          {(lastEval.failure_reasons || []).slice(0, 2).map((r, i) => <div key={i} style={{ color: 'var(--af-text-dim)' }}>• {r}</div>)}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
        {mv.status === 'CANDIDATE' && passedEval && mv.base_model !== 'rule_baseline' && (
          <button className="af-btn af-btn--success af-btn--sm" disabled={busy} onClick={() => act(() => api.forge.training.promoteVersion(mv.model_version_id, { reason: 'cockpit promotion' }), 'Promote')}>↑ Promote to ACTIVE</button>
        )}
        {mv.status === 'CANDIDATE' && !passedEval && mv.base_model !== 'rule_baseline' && (
          <span style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', alignSelf: 'center' }}>run evaluation before promoting</span>
        )}
        {(mv.status === 'CANDIDATE' || mv.status === 'APPROVED') && (
          <button className="af-btn af-btn--danger af-btn--sm" disabled={busy} onClick={() => act(() => api.forge.training.rejectVersion(mv.model_version_id), 'Reject')}>Reject</button>
        )}
        {mv.status === 'ACTIVE' && (
          <button className="af-btn af-btn--sm" style={{ background: 'rgba(245,158,11,0.15)', color: '#f59e0b' }} disabled={busy} onClick={() => act(() => api.forge.training.rollbackVersion(mv.model_version_id), 'Rollback')}>↩ Rollback</button>
        )}
      </div>
    </div>
  )
}

export function TrainingPane({ project }) {
  const [tab, setTab] = useState('runs')
  const [overview, setOverview] = useState(null)
  const [runs, setRuns] = useState([])
  const [versions, setVersions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    Promise.all([
      api.forge.training.getOverview(project.id),
      api.forge.training.getRuns(project.id),
      api.forge.training.getModelVersions(project.id),
    ]).then(([ov, rn, mv]) => {
      if (ov.ok) setOverview(ov)
      if (rn.ok) setRuns(rn.training_runs || [])
      if (mv.ok) setVersions(mv.model_versions || [])
      if (!ov.ok) setError(ov.error || 'Failed to load')
    }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [project?.id])

  useEffect(() => { load() }, [load])

  if (!project) return <div className="af-understand__hint">Select a project to view training.</div>

  const summary = overview?.summary || { datasets: 0, training_runs: 0, candidates: 0, active_helpers: 0, last_eval_score: null, failed_jobs: 0 }
  const TABS = [
    { id: 'runs', label: 'Training Runs', badge: summary.training_runs },
    { id: 'versions', label: 'Model Versions', badge: summary.candidates + summary.active_helpers },
  ]

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden', height: '100%' }}>
      <SectionLabel>MODEL TRAINING — PHASE 8 (advisory helper models)</SectionLabel>
      <TrainingSummaryCard summary={summary} onRefresh={load} />

      <div style={{ display: 'flex', gap: 2, borderBottom: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '4px 10px', border: 'none', borderRadius: 4, cursor: 'pointer', font: '500 10px monospace',
            background: tab === t.id ? 'rgba(205,127,50,0.15)' : 'transparent',
            color: tab === t.id ? 'var(--af-bronze-bright)' : 'var(--af-text-dim)',
            borderBottom: tab === t.id ? '2px solid var(--af-bronze-bright)' : '2px solid transparent',
          }}>
            {t.label} {t.badge > 0 && <span style={{ marginLeft: 3, font: '600 9px monospace', padding: '0 3px', borderRadius: 3, background: 'rgba(205,127,50,0.3)' }}>{t.badge}</span>}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {loading && <EmptyState title="Loading…" />}
        {error && <div style={{ color: '#ef4444', font: '400 11px monospace' }}>{error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>Retry</button></div>}

        {!loading && tab === 'runs' && (<>
          {overview && (
            <CreateRunForm
              project={project}
              datasets={overview.datasets || []}
              modelTypes={overview.model_types || []}
              methods={overview.training_methods || []}
              onCreated={() => load()}
            />
          )}
          {runs.length === 0 && <EmptyState title="No training runs" body="Create a run from an approved Phase 7 dataset export." />}
          {runs.map(r => <TrainingRunCard key={r.training_run_id} run={r} onChanged={load} />)}
        </>)}

        {!loading && tab === 'versions' && (<>
          {versions.length === 0 && <EmptyState title="No model versions" body="Model versions appear after training completes. They stay CANDIDATE until you promote them." />}
          {versions.map(mv => <ModelVersionCard key={mv.model_version_id} mv={mv} onChanged={load} />)}
        </>)}
      </div>
    </div>
  )
}

export default TrainingPane
