import { useState, useEffect, useCallback } from 'react'
import { SectionLabel, EmptyState } from '../../nexus-ui'
import api from '../../../api/client'
import { PendingApprovalsPanel } from './ReviewPanel'

export function MemoryV3Pane({ project }) {
  const [facts, setFacts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [category, setCategory] = useState('')

  const load = useCallback(() => {
    if (!project?.id) return
    setLoading(true); setError(null)
    api.forge.getMemory(project.id, category || undefined)
      .then(d => { if (d.ok) setFacts(d.facts || []); else setError(d.error || 'Failed to load memory') })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [project?.id, category])

  useEffect(() => { load() }, [load])

  if (!project) return <div className="af-understand__hint">Select a project to view memory.</div>

  const CONF_COLOR = { HIGH: '#22c55e', MEDIUM: '#f59e0b', LOW: '#6b7280' }
  const categories = [...new Set(facts.map(f => f.category).filter(Boolean))]

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <SectionLabel>MEMORY V3 — {facts.length} FACTS</SectionLabel>
        <div style={{ display: 'flex', gap: 6 }}>
          <select
            style={{ fontSize: 10, padding: '2px 6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 3, color: 'var(--af-text-muted)' }}
            value={category} onChange={e => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>Refresh</button>
        </div>
      </div>

      {loading && <div className="af-understand__hint">Loading memory…</div>}
      {error && (
        <div style={{ color: '#ef4444', fontSize: 11 }}>
          {error} <button className="af-btn af-btn--ghost af-btn--sm" onClick={load}>Retry</button>
        </div>
      )}
      {!loading && !error && facts.length === 0 && (
        <EmptyState title="No memory facts yet" body="Facts are extracted automatically after runs as the system learns from each agentic execution." />
      )}
      {facts.map((f, i) => (
        <div key={f.id || i} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ font: '600 11px/1 monospace', color: CONF_COLOR[f.confidence] || '#888' }}>{f.confidence || 'LOW'}</span>
            {f.category && <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>{f.category}</span>}
            <span style={{ marginLeft: 'auto', font: '400 9px monospace', color: 'var(--af-text-dim)' }}>used {f.usage_count || 0}x</span>
          </div>
          <div style={{ font: '400 12px/1.5 system-ui', color: 'var(--af-text)' }}>{f.fact || f.content}</div>
          {f.source && <div style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', marginTop: 4 }}>source: {f.source}</div>}
          {f.evidence && <div style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', marginTop: 2 }}>evidence: {String(f.evidence).slice(0, 120)}</div>}
          {f.created_at && <div style={{ font: '400 9px monospace', color: 'var(--af-text-dim)', marginTop: 3 }}>{new Date(f.created_at).toLocaleString()}</div>}
        </div>
      ))}
    </div>
  )
}

export function SafetyPane({ project, activeRun, onApprove, onReject, onContinue }) {
  const [patches, setPatches] = useState([])
  const [loading, setLoading] = useState(false)
  const autonomyLevel = project?.autonomy_level ?? null

  useEffect(() => {
    if (!activeRun?.id) { setPatches([]); return }
    setLoading(true)
    api.forge.getRunPatches(activeRun.id)
      .then(d => setPatches(d.patches || []))
      .catch(() => setPatches([]))
      .finally(() => setLoading(false))
  }, [activeRun?.id])

  const secFindings = activeRun?.final_report?.security_findings || []
  const highRiskPatches = patches.filter(p => ['high', 'critical'].includes((p.risk_level || '').toLowerCase()))
  const pendingPatches = patches.filter(p => p.status === 'staged' || p.status === 'awaiting_approval')

  const autonomyColors = { 0: '#22c55e', 1: '#22c55e', 2: '#f59e0b', 3: '#ef4444' }
  const autonomyLabels = { 0: 'ReadOnly', 1: 'SafeEdits', 2: 'Guided', 3: 'Autopilot' }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>
      <SectionLabel>SAFETY &amp; APPROVALS</SectionLabel>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 5, border: '1px solid rgba(255,255,255,0.07)' }}>
        <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>Autonomy Level</span>
        <span style={{ font: '700 12px monospace', color: autonomyColors[autonomyLevel] || '#888' }}>
          {autonomyLevel != null ? `Level ${autonomyLevel}` : '—'}
        </span>
        {autonomyLevel != null && (
          <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)' }}>({autonomyLabels[autonomyLevel] || ''})</span>
        )}
      </div>

      {activeRun ? (
        <PendingApprovalsPanel run={activeRun} onApprove={onApprove} onReject={onReject} onContinue={onContinue} />
      ) : (
        <div className="af-understand__hint">No active run — start a run to see pending approvals here.</div>
      )}

      {secFindings.length > 0 && (
        <>
          <SectionLabel>SECURITY FINDINGS — {secFindings.length}</SectionLabel>
          {secFindings.map((f, i) => (
            <div key={i} style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 5, padding: '8px 12px' }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
                <span style={{ font: '600 10px monospace', color: '#ef4444', textTransform: 'uppercase' }}>{f.severity || 'medium'}</span>
                {f.file && <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)' }}>{f.file}</span>}
              </div>
              <div style={{ font: '400 11px/1.4 monospace', color: 'var(--af-text-muted)' }}>{f.description || f.message || String(f)}</div>
            </div>
          ))}
        </>
      )}

      {loading && <div className="af-understand__hint">Loading patches…</div>}
      {!loading && highRiskPatches.length > 0 && (
        <>
          <SectionLabel>HIGH-RISK STAGED PATCHES — {highRiskPatches.length}</SectionLabel>
          {highRiskPatches.map((p, i) => (
            <div key={p.id || i} style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 5, padding: '10px 12px' }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'center' }}>
                <span style={{ font: '600 10px monospace', color: '#f59e0b', textTransform: 'uppercase' }}>{p.risk_level || 'high'}</span>
                <span style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.file_path || p.path}</span>
                <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase', flexShrink: 0 }}>{p.status}</span>
              </div>
              {p.unified_diff && (
                <pre style={{ font: '400 10px/1.4 monospace', color: 'var(--af-text-muted)', maxHeight: 120, overflow: 'auto', background: 'rgba(0,0,0,0.3)', padding: '6px 8px', borderRadius: 3, margin: '4px 0' }}>
                  {p.unified_diff.slice(0, 600)}{p.unified_diff.length > 600 ? '\n...' : ''}
                </pre>
              )}
              {pendingPatches.some(pp => pp.id === p.id) && onApprove && (
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <button className="af-btn af-btn--success af-btn--sm" onClick={() => onApprove(p.id)}>Approve</button>
                  <button className="af-btn af-btn--danger af-btn--sm" onClick={() => onReject(p.id)}>Reject</button>
                </div>
              )}
            </div>
          ))}
        </>
      )}
      {!loading && !activeRun && secFindings.length === 0 && highRiskPatches.length === 0 && (
        <EmptyState title="All clear" body="No pending approvals, security findings, or high-risk patches." />
      )}
    </div>
  )
}
