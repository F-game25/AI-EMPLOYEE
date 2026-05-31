import { useState, useEffect, useCallback } from 'react'
import { SectionLabel, EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import api from '../../../api/client'

const CONF_COLORS = { high: '#22c55e', medium: '#f59e0b', low: '#6b7280' }
const PROPOSAL_STATUS_COLORS = { NEW: '#f59e0b', APPROVED: '#22c55e', REJECTED: '#ef4444', APPLIED: '#3b82f6' }
const LESSON_CATEGORIES = ['planning','coding','testing','debugging','security','reviewing','autopilot','model_routing','memory','skills','ui','backend','architecture']

function LearningTab({ label, active, onClick, badge }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '4px 10px', border: 'none', borderRadius: 4, cursor: 'pointer', font: '500 10px monospace',
        background: active ? 'rgba(205,127,50,0.15)' : 'transparent',
        color: active ? 'var(--af-bronze-bright)' : 'var(--af-text-dim)',
        borderBottom: active ? '2px solid var(--af-bronze-bright)' : '2px solid transparent',
        position: 'relative', whiteSpace: 'nowrap',
      }}
    >
      {label}
      {badge > 0 && (
        <span style={{ marginLeft: 4, font: '600 9px monospace', padding: '0 3px', borderRadius: 3, background: 'rgba(205,127,50,0.3)', color: 'var(--af-bronze-bright)' }}>{badge}</span>
      )}
    </button>
  )
}

function LearningSummaryCard({ summary, onRefresh }) {
  const fields = [
    { label: 'Records', value: summary.records },
    { label: 'Lessons', value: summary.lessons },
    { label: 'Pairs', value: summary.preference_pairs },
    { label: 'Eval cases', value: summary.eval_cases },
    { label: 'Proposals', value: summary.skill_proposals },
    { label: 'Pending', value: summary.pending_proposals },
    { label: 'Datasets', value: summary.datasets },
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

function LessonsTab({ project, summary }) {
  const [lessons, setLessons] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [category, setCategory] = useState('')
  const [promoting, setPromoting] = useState({})

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getLessons(project.id, category ? { category } : {})
      .then(d => { if (d.ok) setLessons(d.lessons || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id, category])

  useEffect(() => { load() }, [load])

  async function promote(lesson) {
    setPromoting(p => ({ ...p, [lesson.lesson_id]: true }))
    try {
      const r = await api.forge.promoteLesson(lesson.lesson_id)
      if (r.ok) { toastSuccess('Promoted to Memory V3'); load() }
      else toastError(r.error || 'Promotion failed')
    } catch (e) { toastError(e.message) }
    finally { setPromoting(p => ({ ...p, [lesson.lesson_id]: false })) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflow: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', paddingBottom: 6 }}>
        {['', ...LESSON_CATEGORIES].map(c => (
          <button key={c} className={`af-btn af-btn--ghost af-btn--sm${category === c ? ' af-btn--active' : ''}`} onClick={() => setCategory(c)}>{c || 'All'}</button>
        ))}
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={load} style={{ marginLeft: 'auto' }}>↺</button>
      </div>
      {loading && <EmptyState title="Loading…" />}
      {error && <div style={{ color: '#ef4444', font: '400 11px monospace' }}>{error}</div>}
      {!loading && !error && lessons.length === 0 && <EmptyState title="No lessons yet" body="Lessons are extracted automatically after each agentic run completes." />}
      {lessons.map(l => (
        <div key={l.lesson_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{ font: '600 10px monospace', color: CONF_COLORS[l.confidence] || '#888', textTransform: 'uppercase' }}>{l.confidence}</span>
            <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>{l.category}</span>
            {l.promoted_to_memory && <span style={{ font: '600 9px monospace', color: '#3b82f6', background: 'rgba(59,130,246,0.15)', padding: '1px 5px', borderRadius: 3 }}>IN MEMORY</span>}
            {!l.promoted_to_memory && l.confidence !== 'low' && (
              <button className="af-btn af-btn--ghost af-btn--sm" style={{ marginLeft: 'auto' }} disabled={!!promoting[l.lesson_id]} onClick={() => promote(l)}>
                {promoting[l.lesson_id] ? '…' : '↑ Promote'}
              </button>
            )}
          </div>
          <div style={{ font: '400 12px/1.5 system-ui', color: 'var(--af-text)' }}>{l.lesson}</div>
          {l.run_id && <div style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginTop: 4 }}>run: {l.run_id.slice(0, 18)}…</div>}
        </div>
      ))}
    </div>
  )
}

function ProposalsTab({ project }) {
  const [proposals, setProposals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState({})

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getSkillProposals(project.id)
      .then(d => { if (d.ok) setProposals(d.proposals || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])

  useEffect(() => { load() }, [load])

  async function act(id, action) {
    setBusy(b => ({ ...b, [id]: true }))
    try {
      let r
      if (action === 'approve') r = await api.forge.approveProposal(id)
      else if (action === 'reject') r = await api.forge.rejectProposal(id)
      else if (action === 'apply') r = await api.forge.applyProposal(id)
      if (r?.ok) { toastSuccess(`Proposal ${action}d`); load() }
      else toastError(r?.error || 'Action failed')
    } catch (e) { toastError(e.message) }
    finally { setBusy(b => ({ ...b, [id]: false })) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflow: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>↺ Refresh</button>
      </div>
      {loading && <EmptyState title="Loading…" />}
      {error && <div style={{ color: '#ef4444', font: '400 11px monospace' }}>{error}</div>}
      {!loading && !error && proposals.length === 0 && <EmptyState title="No proposals" body="Skill update proposals are generated from run patterns." />}
      {proposals.map(p => (
        <div key={p.proposal_id} style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${PROPOSAL_STATUS_COLORS[p.status] || 'rgba(255,255,255,0.07)'}33`, borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{ font: '700 10px monospace', color: PROPOSAL_STATUS_COLORS[p.status], textTransform: 'uppercase' }}>{p.status}</span>
            <span style={{ font: '600 11px monospace', color: 'var(--af-text-muted)', flex: 1 }}>{p.skill_id}</span>
            <span style={{ font: '400 9px monospace', color: CONF_COLORS[p.confidence] }}>{p.confidence}</span>
          </div>
          <div style={{ font: '400 12px/1.5 system-ui', color: 'var(--af-text)' }}>{p.reason}</div>
          {p.proposed_change?.checklist_addition && (
            <div style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', marginTop: 5, padding: '4px 8px', background: 'rgba(0,0,0,0.2)', borderRadius: 3 }}>
              + {p.proposed_change.checklist_addition}
            </div>
          )}
          {p.proposed_change?.rule_addition && (
            <div style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', marginTop: 3, padding: '4px 8px', background: 'rgba(0,0,0,0.2)', borderRadius: 3 }}>
              rule: {p.proposed_change.rule_addition}
            </div>
          )}
          {p.proposed_change?.failure_mode && (
            <div style={{ font: '400 10px monospace', color: '#ef4444', marginTop: 3, padding: '4px 8px', background: 'rgba(239,68,68,0.05)', borderRadius: 3 }}>
              failure mode: {p.proposed_change.failure_mode}
            </div>
          )}
          {p.run_id && <div style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginTop: 4 }}>run: {p.run_id.slice(0, 18)}…</div>}
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            {p.status === 'NEW' && (<>
              <button className="af-btn af-btn--success af-btn--sm" disabled={!!busy[p.proposal_id]} onClick={() => act(p.proposal_id, 'approve')}>✓ Approve</button>
              <button className="af-btn af-btn--danger af-btn--sm" disabled={!!busy[p.proposal_id]} onClick={() => act(p.proposal_id, 'reject')}>✗ Reject</button>
            </>)}
            {p.status === 'APPROVED' && (
              <button className="af-btn af-btn--sm" style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6' }} disabled={!!busy[p.proposal_id]} onClick={() => act(p.proposal_id, 'apply')}>⚡ Apply to skill</button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function PairsTab({ project }) {
  const [pairs, setPairs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [toggling, setToggling] = useState({})

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getPreferencePairs(project.id)
      .then(d => { if (d.ok) setPairs(d.pairs || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])

  useEffect(() => { load() }, [load])

  async function toggleApproved(pair) {
    setToggling(t => ({ ...t, [pair.pair_id]: true }))
    try {
      const r = await api.forge.updatePreferencePair(pair.pair_id, { approved_for_training: !pair.approved_for_training })
      if (r?.ok) load()
    } catch { /* ignore */ }
    finally { setToggling(t => ({ ...t, [pair.pair_id]: false })) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflow: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
        <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', alignSelf: 'center' }}>Approve pairs for future DPO training</span>
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>↺</button>
      </div>
      {loading && <EmptyState title="Loading…" />}
      {error && <div style={{ color: '#ef4444', font: '400 11px monospace' }}>{error}</div>}
      {!loading && !error && pairs.length === 0 && <EmptyState title="No preference pairs" body="Pairs are generated from approved vs rejected patches and plan iterations." />}
      {pairs.map(p => (
        <div key={p.pair_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{ font: '600 10px monospace', color: CONF_COLORS[p.confidence], textTransform: 'uppercase' }}>{p.confidence}</span>
            <span style={{ font: '400 11px system-ui', color: 'var(--af-text-muted)', flex: 1 }}>{p.reason}</span>
            <button
              className={`af-btn af-btn--sm ${p.approved_for_training ? 'af-btn--success' : 'af-btn--ghost'}`}
              disabled={!!toggling[p.pair_id]}
              onClick={() => toggleApproved(p)}
              title="Toggle approval for training"
            >
              {p.approved_for_training ? '✓ Approved' : 'Approve'}
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 5 }}>
            <div style={{ background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.15)', borderRadius: 4, padding: '6px 8px' }}>
              <div style={{ font: '600 9px monospace', color: '#22c55e', marginBottom: 3 }}>PREFERRED</div>
              <pre style={{ font: '400 9px/1.3 monospace', color: 'var(--af-text-muted)', margin: 0, whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'auto' }}>
                {JSON.stringify(p.preferred, null, 1).slice(0, 300)}
              </pre>
            </div>
            <div style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: 4, padding: '6px 8px' }}>
              <div style={{ font: '600 9px monospace', color: '#ef4444', marginBottom: 3 }}>REJECTED</div>
              <pre style={{ font: '400 9px/1.3 monospace', color: 'var(--af-text-muted)', margin: 0, whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'auto' }}>
                {JSON.stringify(p.rejected, null, 1).slice(0, 300)}
              </pre>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function EvalCasesTab({ project }) {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [evalType, setEvalType] = useState('')
  const EVAL_TYPES = ['', 'planner_eval', 'decomposer_eval', 'risk_classifier_eval', 'command_safety_eval', 'reviewer_eval', 'model_router_eval', 'skill_selection_eval', 'autopilot_eval']

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getEvalCases(project.id, evalType ? { eval_type: evalType } : {})
      .then(d => { if (d.ok) setCases(d.cases || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id, evalType])

  useEffect(() => { load() }, [load])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflow: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', paddingBottom: 6 }}>
        {EVAL_TYPES.map(t => (
          <button key={t} className={`af-btn af-btn--ghost af-btn--sm${evalType === t ? ' af-btn--active' : ''}`} onClick={() => setEvalType(t)}>{t || 'All'}</button>
        ))}
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={load} style={{ marginLeft: 'auto' }}>↺</button>
      </div>
      {loading && <EmptyState title="Loading…" />}
      {error && <div style={{ color: '#ef4444', font: '400 11px monospace' }}>{error}</div>}
      {!loading && !error && cases.length === 0 && <EmptyState title="No eval cases" body="Evaluation cases are generated from successful and failed run trajectories." />}
      {cases.map(ec => (
        <div key={ec.eval_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{ font: '600 10px monospace', color: '#a78bfa', textTransform: 'uppercase' }}>{ec.eval_type}</span>
            <span style={{ font: '400 10px monospace', color: CONF_COLORS[ec.confidence] }}>{ec.confidence}</span>
            <span style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginLeft: 'auto' }}>{ec.source}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 4 }}>
            <div style={{ background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.12)', borderRadius: 4, padding: '6px 8px' }}>
              <div style={{ font: '600 9px monospace', color: '#3b82f6', marginBottom: 3 }}>INPUT</div>
              <pre style={{ font: '400 9px/1.3 monospace', color: 'var(--af-text-muted)', margin: 0, whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'auto' }}>
                {JSON.stringify(ec.input, null, 1).slice(0, 300)}
              </pre>
            </div>
            <div style={{ background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.12)', borderRadius: 4, padding: '6px 8px' }}>
              <div style={{ font: '600 9px monospace', color: '#22c55e', marginBottom: 3 }}>EXPECTED</div>
              <pre style={{ font: '400 9px/1.3 monospace', color: 'var(--af-text-muted)', margin: 0, whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'auto' }}>
                {JSON.stringify(ec.expected, null, 1).slice(0, 300)}
              </pre>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function DatasetsTab({ project }) {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(false)
  const [exportForm, setExportForm] = useState({ dataset_type: 'jsonl', min_confidence: 'low', name: '' })

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getDatasets(project.id)
      .then(d => { if (d.ok) setDatasets(d.datasets || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])

  useEffect(() => { load() }, [load])

  async function doExport() {
    setExporting(true)
    try {
      const r = await api.forge.exportDataset(project.id, {
        ...exportForm,
        name: exportForm.name || `export-${Date.now().toString(36)}`,
      })
      if (r.ok) { toastSuccess(`Exported ${r.dataset.record_count} records`); load() }
      else toastError(r.error || 'Export failed')
    } catch (e) { toastError(e.message) }
    finally { setExporting(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflow: 'auto', height: '100%' }}>
      <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: 12 }}>
        <SectionLabel>EXPORT DATASET</SectionLabel>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          <select value={exportForm.dataset_type} onChange={e => setExportForm(f => ({ ...f, dataset_type: e.target.value }))} style={{ font: '400 10px monospace', padding: '3px 6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted)' }}>
            <option value="jsonl">JSONL (full records)</option>
            <option value="preference_jsonl">Preference JSONL (DPO)</option>
            <option value="eval_jsonl">Eval JSONL</option>
          </select>
          <select value={exportForm.min_confidence} onChange={e => setExportForm(f => ({ ...f, min_confidence: e.target.value }))} style={{ font: '400 10px monospace', padding: '3px 6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted)' }}>
            <option value="low">Min: low</option>
            <option value="medium">Min: medium</option>
            <option value="high">High only</option>
          </select>
          <input value={exportForm.name} onChange={e => setExportForm(f => ({ ...f, name: e.target.value }))} placeholder="Export name (optional)" style={{ font: '400 10px monospace', padding: '3px 6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted)', flex: 1, minWidth: 120 }} />
          <button className="af-btn af-btn--sm" style={{ background: 'rgba(205,127,50,0.15)', color: 'var(--af-bronze-bright)' }} disabled={exporting} onClick={doExport}>
            {exporting ? 'Exporting…' : '↓ Export'}
          </button>
        </div>
      </div>
      {loading && <EmptyState title="Loading…" />}
      {error && <div style={{ color: '#ef4444', font: '400 11px monospace' }}>{error}</div>}
      {!loading && !error && datasets.length === 0 && <EmptyState title="No exports yet" body="Use the form above to export a learning dataset." />}
      {datasets.map(ds => (
        <div key={ds.dataset_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ font: '600 11px monospace', color: 'var(--af-text)', flex: 1 }}>{ds.name}</span>
            <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>{ds.dataset_type}</span>
            <span style={{ font: '700 11px monospace', color: 'var(--af-text-muted)' }}>{ds.record_count} recs</span>
          </div>
          <div style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginTop: 3 }}>{new Date(ds.created_at).toLocaleString()}</div>
        </div>
      ))}
    </div>
  )
}

function RecordsTab({ project }) {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getLearning(project.id)
      .then(d => { if (d.ok) setRecords(d.recent_records || []); else setError(d.error) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id])

  useEffect(() => { load() }, [load])

  async function distillRun(runId) {
    try {
      const r = await api.forge.distillRun(runId)
      if (r.ok) { toastSuccess('Distillation created'); load() }
      else toastError(r.error || 'Distillation failed')
    } catch (e) { toastError(e.message) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflow: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>↺ Refresh</button>
      </div>
      {loading && <EmptyState title="Loading…" />}
      {error && <div style={{ color: '#ef4444', font: '400 11px monospace' }}>{error}</div>}
      {!loading && !error && records.length === 0 && <EmptyState title="No distillation records" body="Records are created automatically after each run completes." />}
      {records.map(r => (
        <div key={r.distill_id} style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${r.scores?.is_positive ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.1)'}`, borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ font: '600 10px monospace', color: r.scores?.is_positive ? '#22c55e' : '#ef4444', textTransform: 'uppercase' }}>{r.scores?.is_positive ? 'POSITIVE' : 'NEGATIVE'}</span>
            <span style={{ font: '400 10px monospace', color: CONF_COLORS[r.confidence] }}>{r.confidence}</span>
            <span style={{ font: '600 10px monospace', color: 'var(--af-text-muted)' }}>score: {r.scores?.composite ?? '—'}</span>
            <span style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginLeft: 'auto' }}>{new Date(r.created_at).toLocaleString()}</span>
          </div>
          <div style={{ font: '400 11px/1.4 system-ui', color: 'var(--af-text)' }}>{(r.goal || '').slice(0, 120)}</div>
          <div style={{ display: 'flex', gap: 10, marginTop: 5, font: '400 9px monospace', color: 'var(--af-text-dim)' }}>
            <span>{r.lessons?.length || 0} lessons</span>
            <span>{r.preference_pairs?.length || 0} pairs</span>
            <span>{r.eval_cases?.length || 0} evals</span>
            <span>{r.skill_proposals?.length || 0} proposals</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export function LearningPane({ project }) {
  const [tab, setTab] = useState('summary')
  const [summary, setSummary] = useState({ records: 0, lessons: 0, preference_pairs: 0, eval_cases: 0, skill_proposals: 0, pending_proposals: 0, datasets: 0 })
  const [loadingSummary, setLoadingSummary] = useState(true)

  const loadSummary = useCallback(() => {
    if (!project?.id) return
    setLoadingSummary(true)
    api.forge.getLearning(project.id)
      .then(d => { if (d.ok) setSummary(d.summary || {}) })
      .catch(() => {})
      .finally(() => setLoadingSummary(false))
  }, [project?.id])

  useEffect(() => { loadSummary() }, [loadSummary])

  if (!project) return <div className="af-understand__hint">Select a project to view learning data.</div>

  const TABS = [
    { id: 'summary', label: 'Records', badge: summary.records },
    { id: 'lessons', label: 'Lessons', badge: summary.lessons },
    { id: 'proposals', label: 'Proposals', badge: summary.pending_proposals },
    { id: 'pairs', label: 'Pairs', badge: summary.preference_pairs },
    { id: 'evals', label: 'Eval Cases', badge: summary.eval_cases },
    { id: 'datasets', label: 'Datasets', badge: summary.datasets },
  ]

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden', height: '100%' }}>
      <SectionLabel>LEARNING CORE — PHASE 7</SectionLabel>
      {!loadingSummary && <LearningSummaryCard summary={summary} onRefresh={loadSummary} />}

      <div style={{ display: 'flex', gap: 2, overflowX: 'auto', flexShrink: 0, borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 2 }}>
        {TABS.map(t => <LearningTab key={t.id} label={t.label} active={tab === t.id} badge={t.badge} onClick={() => setTab(t.id)} />)}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {tab === 'summary' && <RecordsTab project={project} />}
        {tab === 'lessons' && <LessonsTab project={project} summary={summary} />}
        {tab === 'proposals' && <ProposalsTab project={project} />}
        {tab === 'pairs' && <PairsTab project={project} />}
        {tab === 'evals' && <EvalCasesTab project={project} />}
        {tab === 'datasets' && <DatasetsTab project={project} />}
      </div>
    </div>
  )
}
