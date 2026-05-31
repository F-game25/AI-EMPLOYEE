import { useState, useEffect, useRef } from 'react'
import { SectionLabel, StatusPill } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JGET, JPOST_JSON } from './helpers'
import { PendingApprovalsPanel, ReplayTimeline } from './ReviewPanel'

const RUN_WRITE_TYPES = new Set(['write_file', 'file_create', 'file_update', 'scaffold_create'])
const STATUS_TONES = { verified: 'success', applied: 'success', waiting_approval: 'warn', verify_failed: 'alert', failed: 'alert', planning: 'info', executing: 'info', testing: 'info', reviewing: 'info' }

export function RunTimeline({ run, onVerify, onApply, busy }) {
  if (!run) {
    return (
      <div className="af-run-compact">
        <div className="af-run-compact__empty">
          <strong>◆ No active run</strong> — send a goal to start
        </div>
      </div>
    )
  }
  const latestTest = (run.test_results || []).slice(-1)[0]
  const patches = run.patches || []
  const actions = run.actions || []
  const stagedCount = patches.filter(patch => ['staged', 'verified', 'applied'].includes(String(patch.status || '').toLowerCase())).length
  const blockedCount = patches.filter(patch => patch.policy?.allowed === false || String(patch.status || '').toLowerCase() === 'blocked').length
  const writeCount = actions.filter(action => RUN_WRITE_TYPES.has(action.type)).length || patches.length
  const canVerify = !busy && stagedCount > 0 && blockedCount === 0 && run.status !== 'applied'
  const canApply = !busy && run.status === 'verified' && latestTest?.all_passed === true && blockedCount === 0
  const verifyReason = busy ? 'Run operation in progress'
    : blockedCount > 0 ? 'Blocked patches must be resolved first'
    : stagedCount === 0 ? 'Approve and stage a write action first'
    : run.status === 'applied' ? 'Run has already been applied'
    : 'Run is staged and ready to verify'
  const applyReason = busy ? 'Run operation in progress'
    : run.status !== 'verified' ? 'Verification must pass before apply'
    : latestTest?.all_passed !== true ? 'Latest verification did not pass'
    : blockedCount > 0 ? 'Blocked patches cannot be applied'
    : 'Verified run is ready to apply'
  const statusTone = run.status === 'applied' || run.status === 'verified' ? 'success'
    : run.status === 'blocked' || run.status === 'verify_failed' ? 'alert'
    : 'gold'
  const NEXT = { new: 'APPROVAL', awaiting_approval: 'STAGING', pending_approval: 'STAGING', staged: 'VERIFY', verified: 'APPLY', applied: 'DONE' }
  const nextStageLabel = NEXT[run.status] ?? 'REVIEW'

  return (
    <div className="af-run-compact">
      <div className="af-run-compact__stage-row">
        <span>Stage:</span>
        <StatusPill label={String(run.status || 'new').toUpperCase()} tone={statusTone} size="sm" />
        <span className="af-run-compact__stage-arrow">→</span>
        <span>Next:</span>
        <StatusPill label={nextStageLabel} tone="idle" size="sm" />
        <code style={{marginLeft:'auto',fontSize:9,color:'var(--nx-text-muted)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:80}}>{run.id}</code>
      </div>
      <div className="af-run-compact__counts">
        <div className="af-run-compact__count"><b>{stagedCount}</b><small>staged</small></div>
        <div className="af-run-compact__count"><b>{blockedCount}</b><small>blocked</small></div>
        <div className="af-run-compact__count"><b>{writeCount}</b><small>writes</small></div>
      </div>
      {run.ui_error && <div style={{color:'var(--af-red)',fontSize:10,marginBottom:6}}>{run.ui_error}</div>}
      <div className="af-run-compact__actions">
        <button className="af-btn af-btn--ghost af-btn--sm" onClick={onVerify} disabled={!canVerify} title={verifyReason}>
          {busy ? '…' : 'Verify'}
        </button>
        <button className="af-btn af-btn--primary af-btn--sm" onClick={onApply} disabled={!canApply} title={applyReason}>
          Apply
        </button>
      </div>
    </div>
  )
}

export function Terminal({ lines }) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines])

  return (
    <div className="af-terminal">
      <div className="af-terminal__header">
        <span className="af-terminal__dot af-terminal__dot--r" />
        <span className="af-terminal__dot af-terminal__dot--y" />
        <span className="af-terminal__dot af-terminal__dot--g" />
        <span className="af-terminal__title">RUN CONSOLE</span>
      </div>
      <div className="af-terminal__body">
        {lines.length === 0 && <span className="af-terminal__empty">No run output yet. Create, stage, verify, or apply a run to stream real events here.</span>}
        {lines.map((l, i) => (
          <div key={i} className={`af-terminal__line af-terminal__line--${l.type || 'out'}`}>
            <span className="af-terminal__prompt">{l.type === 'cmd' ? '$ ' : '  '}</span>
            <span>{l.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  )
}

function AgentStageBadge({ stage, label, color }) {
  if (!stage) return <div className="af-agent-badge af-agent-badge--pending" style={{ borderColor: color }}><span>{label}</span><span className="af-agent-badge__status">—</span></div>
  const ok = stage.status === 'done'
  const fail = stage.status === 'failed' || stage.status === 'blocked'
  const dur = stage.duration_ms ? `${(stage.duration_ms / 1000).toFixed(1)}s` : ''
  return (
    <div className={`af-agent-badge ${ok ? 'af-agent-badge--ok' : fail ? 'af-agent-badge--fail' : 'af-agent-badge--warn'}`} style={{ borderColor: color }}>
      <span style={{ color }}>{label}</span>
      <span className="af-agent-badge__status">{ok ? `✓ ${dur}` : fail ? `✗ ${dur}` : `~ ${dur}`}</span>
    </div>
  )
}

function AgentIterationRow({ t, idx }) {
  const [open, setOpen] = useState(idx === 0)
  const iterPass = t.verify?.all_passed && t.reviewer?.output?.verdict !== 'block'
  return (
    <div className="af-agentic__iter">
      <div className="af-agentic__itertitle" onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', userSelect: 'none' }}>
        <span>{open ? '▾' : '▸'}</span>
        <span>Iteration {t.iteration}</span>
        <span className={iterPass ? 'af-pill--ok-sm' : 'af-pill--fail-sm'}>{iterPass ? 'PASS' : 'FAIL'}</span>
        <div className="af-agent-badges">
          <AgentStageBadge stage={t.planner} label="PLANNER" color="#E5C76B" />
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.coder} label="CODER" color="#60A5FA" />
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.tester} label="TESTER" color="#C084FC" />
          {t.debug?.length > 0 && <><span className="af-agent-arrow">↻</span><AgentStageBadge stage={t.debug[t.debug.length-1]} label="DEBUG" color="#F59E0B" /></>}
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.security} label="SECURITY" color="#FCA5A5" />
          <span className="af-agent-arrow">→</span>
          <AgentStageBadge stage={t.reviewer} label="REVIEWER" color="#20D6C7" />
        </div>
      </div>

      {open && (
        <div className="af-agent-detail">
          {t.planner?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#E5C76B' }}>Planner</div>
              {(t.planner.output.objectives || []).length > 0 && (
                <ul className="af-agent-list">{t.planner.output.objectives.map((o, i) => <li key={i}>{o}</li>)}</ul>
              )}
              {(t.planner.output.relevant_files || []).length > 0 && (
                <div className="af-agent-files-hint">Files: {t.planner.output.relevant_files.join(', ')}</div>
              )}
              {(t.planner.output.risks || []).length > 0 && (
                <div className="af-agent-risks">Risks: {t.planner.output.risks.join(' · ')}</div>
              )}
            </div>
          )}

          {t.files_written?.length > 0 && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#60A5FA' }}>Coder</div>
              <div className="af-agentic__files">
                {t.files_written.map((f, i) => <span key={i} className={f.ok ? 'ok' : 'fail'}>{f.path}{f.error ? ` (${f.error})` : ''}</span>)}
              </div>
            </div>
          )}

          {t.tester?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#C084FC' }}>Tester</div>
              {(t.tester.output.results || []).map((r, i) => (
                <div key={i} className={`af-agent-test-row ${r.pass ? 'ok' : 'fail'}`}>
                  <span>{r.pass ? '✓' : '✗'}</span>
                  <span>{r.command}</span>
                  {!r.pass && <pre className="af-agentic__err">{(r.output || '').slice(-300)}</pre>}
                </div>
              ))}
            </div>
          )}

          {t.debug?.length > 0 && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#F59E0B' }}>Debug ({t.debug.length} attempt(s))</div>
              {t.debug.map((d, i) => (
                <div key={i} className="af-agent-risks">
                  Retry {i+1}: {d.output?.root_cause || 'unknown cause'} → {d.output?.fix_description || ''}
                  {d.output?.repair_staged && <span style={{ color: '#22c55e', marginLeft: 6 }}>✓ repair staged</span>}
                </div>
              ))}
            </div>
          )}

          {t.security?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#FCA5A5' }}>Security — {t.security.output.verdict?.toUpperCase()}</div>
              {t.security.output.summary && <div className="af-agent-risks">{t.security.output.summary}</div>}
              {(t.security.output.findings || []).map((f, i) => (
                <div key={i} className={`af-agent-finding af-agent-finding--${f.severity === 'critical' ? 'error' : f.severity || 'info'}`}>
                  <span className="af-agent-finding__type">{f.type}</span>
                  <span className="af-agent-finding__file">{f.file}{f.line ? `:${f.line}` : ''}</span>
                  <span>{f.message}</span>
                </div>
              ))}
            </div>
          )}

          {t.reviewer?.output && (
            <div className="af-agent-section">
              <div className="af-agent-section__label" style={{ color: '#20D6C7' }}>Reviewer — {t.reviewer.output.verdict?.toUpperCase()}</div>
              {t.reviewer.output.summary && <div className="af-agent-risks">{t.reviewer.output.summary}</div>}
              {(t.reviewer.output.findings || []).map((f, i) => (
                <div key={i} className={`af-agent-finding af-agent-finding--${f.severity || 'info'}`}>
                  <span className="af-agent-finding__type">{f.type}</span>
                  <span className="af-agent-finding__file">{f.file}{f.line ? `:${f.line}` : ''}</span>
                  <span>{f.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function AgenticPane({ project }) {
  const [goal, setGoal] = useState('')
  const [maxIters, setMaxIters] = useState(3)
  const [running, setRunning] = useState(false)
  const [run, setRun] = useState(null)

  if (!project) return <div className="af-chat__no-project">Select a writable project to auto-build.</div>
  if (!project.write_access) return <div className="af-understand__hint">This project is read-only — auto-build needs write access (import with write access or create a project).</div>

  const start = async () => {
    if (!goal.trim()) return
    setRunning(true); setRun(null)
    try {
      const d = await JPOST_JSON('/api/forge/agentic-run', { project_id: project.id, goal, max_iterations: maxIters, ownerApproved: true, auto_rollback: true })
      setRun(d)
      d.success ? toastSuccess(d.summary) : toastError(d.summary)
    } catch (e) { toastError(e.message) } finally { setRunning(false) }
  }

  return (
    <div className="af-understand">
      <SectionLabel>AUTONOMOUS BUILD</SectionLabel>
      <div className="af-understand__hint">Planner → Coder → Tester → Reviewer, looping until green. Auto-rolls-back on failure. Owner-approved &amp; bounded.</div>
      <textarea className="af-agentic__goal" rows={3} value={goal} onChange={e => setGoal(e.target.value)} placeholder="e.g. Add a /health route that returns {status:'ok'} and make sure the build passes" />
      <div className="af-agentic__controls">
        <label>Max iterations
          <select value={maxIters} onChange={e => setMaxIters(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button className="af-index-btn" onClick={start} disabled={running}>{running ? 'Building…' : '▶ Auto-build'}</button>
      </div>

      {running && (
        <div className="af-agentic__pipeline-loading">
          <div className="af-agent-badges">
            {['PLANNER','CODER','TESTER','SECURITY','REVIEWER'].map((a, i) => (
              <span key={a}>{i > 0 && <span className="af-agent-arrow">→</span>}<span className="af-agent-badge af-agent-badge--pending">{a}</span></span>
            ))}
          </div>
          <div className="af-understand__hint" style={{ marginTop: 8 }}>Running multi-agent pipeline…</div>
        </div>
      )}

      {run?.waiting_approval && (
        <PendingApprovalsPanel
          run={run.run ? run.run : run}
          onApprove={() => {}}
          onReject={() => {}}
          onContinue={() => setRun(null)}
        />
      )}

      {run && !run.waiting_approval && (
        <div className="af-agentic__result">
          <div className={`af-agentic__status ${run.success ? 'ok' : 'fail'}`}>
            {run.success ? '✓ ' : '✗ '}{run.summary}
          </div>
          {(run.transcript || []).map((t, i) => <AgentIterationRow key={t.iteration} t={t} idx={i} />)}
        </div>
      )}
    </div>
  )
}

export function RunHistoryPane({ project }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [loadingTranscript, setLoadingTranscript] = useState(false)
  const [replayRunId, setReplayRunId] = useState(null)

  useEffect(() => {
    if (!project) { setRuns([]); setLoading(false); return }
    JGET(`/api/forge/runs?project_id=${project.id}&limit=30`)
      .then(r => r.json())
      .then(d => setRuns(Array.isArray(d.runs) ? d.runs : []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false))
  }, [project?.id])

  const selectRun = async (run) => {
    setSelected(run)
    setTranscript(null)
    setLoadingTranscript(true)
    try {
      const d = await JGET(`/api/forge/runs/${run.id}/transcript`).then(r => r.json())
      setTranscript(d.transcript || [])
    } catch { setTranscript([]) } finally { setLoadingTranscript(false) }
  }

  if (!project) return <div className="af-understand__hint">Select a project to view run history.</div>

  return (
    <div className="af-run-history">
      <div className="af-run-history__list">
        <SectionLabel>RUN HISTORY</SectionLabel>
        {loading && <div className="af-understand__hint">Loading…</div>}
        {!loading && !runs.length && <div className="af-understand__hint">No runs yet for this project.</div>}
        {runs.map(r => (
          <div key={r.id} className={`af-run-row ${selected?.id === r.id ? 'af-run-row--active' : ''}`} onClick={() => { selectRun(r); setReplayRunId(null) }}>
            <div className="af-run-row__id">{(r.id || '').slice(-8)}</div>
            <div className="af-run-row__goal">{(r.goal || r.final_report?.summary || '').slice(0, 55)}</div>
            <StatusPill label={(r.status || 'unknown').toUpperCase()} tone={STATUS_TONES[r.status] || 'muted'} size="sm" />
            <div className="af-run-row__meta">{r.final_report?.transcript?.length || 0}i · {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}</div>
          </div>
        ))}
      </div>
      {selected && !replayRunId && (
        <div className="af-run-history__detail">
          <div className="af-run-history__detail-header">
            <SectionLabel>{(selected.id || '').slice(-8)} — {(selected.status || '').toUpperCase()}</SectionLabel>
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setReplayRunId(selected.id)}>▶ Replay</button>
          </div>
          {selected.final_report?.summary && <div className="af-understand__hint">{selected.final_report.summary}</div>}
          {selected.final_report?.recommended_next_task && <div className="af-agent-risks" style={{ color: '#60A5FA' }}>Next: {selected.final_report.recommended_next_task}</div>}
          {loadingTranscript && <div className="af-understand__hint">Loading transcript…</div>}
          {transcript && transcript.map((t, i) => <AgentIterationRow key={t.iteration ?? i} t={t} idx={i} />)}
          {transcript && !transcript.length && <div className="af-understand__hint">No agent transcript recorded for this run.</div>}
        </div>
      )}
      {replayRunId && <ReplayTimeline runId={replayRunId} onClose={() => setReplayRunId(null)} />}
    </div>
  )
}

function MetricBar({ label, value, max, color }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className="af-metric-bar">
      <div className="af-metric-bar__label">{label}</div>
      <div className="af-metric-bar__track"><div className="af-metric-bar__fill" style={{ width: `${pct}%`, background: color || '#E5C76B' }} /></div>
      <div className="af-metric-bar__value">{value}</div>
    </div>
  )
}

export function RunMetricsPane({ project }) {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!project?.id) { setLoading(false); return }
    JGET(`/api/forge/projects/${project.id}/forge-metrics`)
      .then(r => r.json())
      .then(d => setMetrics(d.ok ? d : null))
      .catch(() => setMetrics(null))
      .finally(() => setLoading(false))
  }, [project?.id])

  if (!project) return <div className="af-understand__hint">Select a project to view metrics.</div>
  if (loading) return <div className="af-understand__hint">Loading metrics…</div>
  if (!metrics) return <div className="af-understand__hint">No metrics yet. Run auto-build to generate data.</div>

  const successCount = (metrics.by_status?.applied || 0) + (metrics.by_status?.verified || 0)
  const byStatus = Object.entries(metrics.by_status || {})

  return (
    <div className="af-metrics">
      <SectionLabel>PROJECT METRICS</SectionLabel>
      <div className="af-metrics__grid">
        <div className="af-metric-card">
          <div className="af-metric-card__value">{metrics.total_runs}</div>
          <div className="af-metric-card__label">Total Runs</div>
        </div>
        <div className="af-metric-card">
          <div className="af-metric-card__value" style={{ color: '#22c55e' }}>{Math.round((metrics.success_rate || 0) * 100)}%</div>
          <div className="af-metric-card__label">Success Rate</div>
        </div>
        <div className="af-metric-card">
          <div className="af-metric-card__value">{metrics.avg_duration_sec}s</div>
          <div className="af-metric-card__label">Avg Duration</div>
        </div>
        <div className="af-metric-card">
          <div className="af-metric-card__value" style={{ color: '#FCA5A5' }}>{metrics.security_blocks || 0}</div>
          <div className="af-metric-card__label">Security Blocks</div>
        </div>
      </div>

      <SectionLabel>BY STATUS</SectionLabel>
      {byStatus.map(([status, count]) => (
        <MetricBar key={status} label={status} value={count} max={metrics.total_runs} color={['applied','verified'].includes(status) ? '#22c55e' : ['failed','verify_failed'].includes(status) ? '#ef4444' : '#60A5FA'} />
      ))}

      {(metrics.most_edited_files || []).length > 0 && (
        <>
          <SectionLabel>MOST EDITED FILES</SectionLabel>
          {metrics.most_edited_files.slice(0, 5).map((f, i) => (
            <div key={i} className="af-agent-files-hint" style={{ marginBottom: 2 }}>{f}</div>
          ))}
        </>
      )}

      {metrics.patch_stats && (
        <>
          <SectionLabel>PATCH STATS</SectionLabel>
          <div className="af-metrics__grid">
            {Object.entries(metrics.patch_stats).map(([k, v]) => (
              <div key={k} className="af-metric-card">
                <div className="af-metric-card__value">{v}</div>
                <div className="af-metric-card__label">{k}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
