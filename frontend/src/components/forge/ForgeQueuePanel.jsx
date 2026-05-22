import { useState, useEffect } from 'react'
import { useAppStore } from '../../store/appStore'
import api from '../../api/client'

const RISK_COLORS = { HIGH: '#EF4444', MEDIUM: '#F59E0B', LOW: '#22C55E' }
const STATUS_COLORS = { pending: '#E5C76B', approved: '#22C55E', rejected: '#EF4444', running: '#20D6C7', deployed: '#9333EA' }

const TABS = ['Approval Queue', 'Builder Mode', 'Evolution Status']

function riskLabel(score) {
  if (score >= 0.7) return 'HIGH'
  if (score >= 0.3) return 'MEDIUM'
  return 'LOW'
}

function relTime(ts) {
  if (!ts) return ''
  const secs = Math.floor(Date.now() / 1000) - Number(ts)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

// ── Approval Queue Tab ────────────────────────────────────────────────────────

function ApprovalQueue() {
  const forgeQueue = useAppStore(s => s.forgeQueue)
  const setForgeQueue = useAppStore(s => s.setForgeQueue)
  const upsertForgeItem = useAppStore(s => s.upsertForgeItem)
  const [goalInput, setGoalInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [expanded, setExpanded] = useState(null)
  const [filter, setFilter] = useState('all')

  // Hydrate queue on mount
  useEffect(() => {
    api.get('/api/forge/queue')
      .then(d => setForgeQueue(d.items || []))
      .catch(() => {})
  }, [setForgeQueue])

  const submitGoal = async () => {
    if (!goalInput.trim() || submitting) return
    setSubmitting(true)
    try {
      await api.post('/api/forge/submit', { goal: goalInput })
      setGoalInput('')
    } catch (e) {
      console.error('forge submit failed', e)
    } finally {
      setSubmitting(false)
    }
  }

  const approve = async (id) => {
    try {
      await api.post(`/api/forge/approve/${id}`)
      upsertForgeItem({ id, status: 'approved' })
    } catch (e) { console.error(e) }
  }

  const reject = async (id) => {
    try {
      await api.post(`/api/forge/reject/${id}`)
      upsertForgeItem({ id, status: 'rejected' })
    } catch (e) { console.error(e) }
  }

  const visible = filter === 'all' ? forgeQueue : forgeQueue.filter(r => r.status === filter)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Submit */}
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={goalInput}
          onChange={e => setGoalInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submitGoal()}
          placeholder="Describe an improvement goal…"
          style={{ flex: 1, padding: '8px 12px', background: 'rgba(10,11,18,0.9)', border: '1px solid rgba(32,214,199,0.2)', borderRadius: 6, color: '#F0E9D2', fontSize: 11, outline: 'none' }}
        />
        <button
          onClick={submitGoal}
          disabled={submitting}
          style={{ padding: '8px 14px', background: 'rgba(32,214,199,0.15)', border: '1px solid rgba(32,214,199,0.4)', borderRadius: 6, color: '#20D6C7', fontSize: 11, cursor: submitting ? 'not-allowed' : 'pointer' }}
        >
          {submitting ? '…' : 'Submit'}
        </button>
      </div>

      {/* Filter row */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {['all', 'pending', 'approved', 'rejected', 'running'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{ padding: '3px 9px', background: filter === f ? 'rgba(32,214,199,0.15)' : 'transparent', border: `1px solid ${filter === f ? 'rgba(32,214,199,0.4)' : 'rgba(255,255,255,0.1)'}`, borderRadius: 4, color: filter === f ? '#20D6C7' : 'rgba(255,255,255,0.4)', fontSize: 10, cursor: 'pointer' }}
          >
            {f}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'rgba(255,255,255,0.3)', alignSelf: 'center' }}>{visible.length} items</span>
      </div>

      {/* Items */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 420, overflowY: 'auto' }}>
        {visible.length === 0 && (
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', textAlign: 'center', padding: '24px 0' }}>No forge items</div>
        )}
        {visible.map(item => {
          const risk = riskLabel(item.risk_score ?? 0.1)
          const isOpen = expanded === item.id
          return (
            <div key={item.id} style={{ borderRadius: 7, background: 'rgba(10,11,18,0.8)', border: `1px solid rgba(${risk === 'HIGH' ? '239,68,68' : risk === 'MEDIUM' ? '245,158,11' : '34,197,94'},0.2)`, overflow: 'hidden' }}>
              <div
                onClick={() => setExpanded(isOpen ? null : item.id)}
                style={{ padding: '9px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
              >
                <span style={{ padding: '2px 6px', borderRadius: 3, background: `${RISK_COLORS[risk]}22`, color: RISK_COLORS[risk], fontSize: 9, fontWeight: 700, flexShrink: 0 }}>{risk}</span>
                <span style={{ flex: 1, color: '#F0E9D2', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.goal || item.description || item.id}</span>
                <span style={{ padding: '2px 6px', borderRadius: 3, background: `${STATUS_COLORS[item.status] || '#9A9AA5'}22`, color: STATUS_COLORS[item.status] || '#9A9AA5', fontSize: 9 }}>{item.status || 'pending'}</span>
                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', flexShrink: 0 }}>{relTime(item.created_at)}</span>
              </div>

              {isOpen && (
                <div style={{ padding: '0 12px 12px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                  {item.goal && <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)', margin: '8px 0 10px', lineHeight: 1.5 }}>{item.goal}</p>}
                  {item.sandbox_result && (
                    <div style={{ padding: '6px 8px', background: 'rgba(0,0,0,0.4)', borderRadius: 5, fontFamily: 'monospace', fontSize: 10, color: '#20D6C7', marginBottom: 10, maxHeight: 120, overflowY: 'auto' }}>
                      {JSON.stringify(item.sandbox_result, null, 2)}
                    </div>
                  )}
                  {item.status === 'pending' && (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => approve(item.id)} style={{ flex: 1, padding: '6px 0', background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.4)', borderRadius: 5, color: '#22C55E', fontSize: 11, cursor: 'pointer' }}>✓ Approve</button>
                      <button onClick={() => reject(item.id)} style={{ flex: 1, padding: '6px 0', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 5, color: '#EF4444', fontSize: 11, cursor: 'pointer' }}>✕ Reject</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Builder Mode Tab ──────────────────────────────────────────────────────────

const TARGET_TYPES = [
  { value: 'fastapi_app', label: 'FastAPI App' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'agent', label: 'Agent' },
  { value: 'frontend_page', label: 'Frontend Page' },
]

function BuilderMode() {
  const [spec, setSpec] = useState('')
  const [projectName, setProjectName] = useState('')
  const [targetType, setTargetType] = useState('fastapi_app')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const generate = async () => {
    if (!spec.trim() || !projectName.trim() || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.post('/api/neural-brain/forge/builder/generate', { spec, project_name: projectName, target_type: targetType }))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const submitToForge = async () => {
    if (!result) return
    try {
      await api.post('/api/forge/submit', { goal: `Deploy generated project: ${projectName}`, files: result.files })
    } catch (e) { console.error(e) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={projectName}
          onChange={e => setProjectName(e.target.value)}
          placeholder="Project name…"
          style={{ flex: 1, padding: '7px 10px', background: 'rgba(10,11,18,0.9)', border: '1px solid rgba(229,199,107,0.2)', borderRadius: 5, color: '#F0E9D2', fontSize: 11, outline: 'none' }}
        />
        <select
          value={targetType}
          onChange={e => setTargetType(e.target.value)}
          style={{ padding: '7px 10px', background: 'rgba(10,11,18,0.9)', border: '1px solid rgba(229,199,107,0.2)', borderRadius: 5, color: '#E5C76B', fontSize: 11, outline: 'none' }}
        >
          {TARGET_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </div>
      <textarea
        value={spec}
        onChange={e => setSpec(e.target.value)}
        placeholder="Describe what you want to build…"
        rows={4}
        style={{ width: '100%', padding: '8px 10px', background: 'rgba(10,11,18,0.9)', border: '1px solid rgba(229,199,107,0.2)', borderRadius: 5, color: '#F0E9D2', fontSize: 11, outline: 'none', resize: 'vertical', boxSizing: 'border-box' }}
      />
      <button
        onClick={generate}
        disabled={loading}
        style={{ padding: '8px 0', background: loading ? 'rgba(229,199,107,0.1)' : 'rgba(229,199,107,0.15)', border: '1px solid rgba(229,199,107,0.4)', borderRadius: 6, color: '#E5C76B', fontSize: 12, cursor: loading ? 'not-allowed' : 'pointer' }}
      >
        {loading ? 'Generating…' : '⚡ Generate'}
      </button>
      {error && <div style={{ fontSize: 10, color: '#EF4444', padding: '6px 8px', background: 'rgba(239,68,68,0.1)', borderRadius: 5 }}>Error: {error}</div>}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ fontSize: 11, color: '#22C55E' }}>✓ Generated {result.files?.length || 0} files</div>
          <div style={{ maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
            {(result.files || []).map((f, i) => (
              <div key={i} style={{ padding: '4px 8px', background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.1)', borderRadius: 4, fontSize: 10, color: '#20D6C7', fontFamily: 'monospace' }}>{f.path}</div>
            ))}
          </div>
          {result.readme && <p style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', margin: 0, lineHeight: 1.5 }}>{result.readme.slice(0, 200)}…</p>}
          <button onClick={submitToForge} style={{ padding: '7px 0', background: 'rgba(147,51,234,0.15)', border: '1px solid rgba(147,51,234,0.3)', borderRadius: 5, color: '#9333EA', fontSize: 11, cursor: 'pointer' }}>Submit to Forge</button>
        </div>
      )}
    </div>
  )
}

// ── Evolution Status Tab ──────────────────────────────────────────────────────

function EvolutionStatus() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    api.get('/api/neural-brain/forge/evolution/status')
      .then(setStatus)
      .catch(() => {})
  }, [])

  if (!status) return <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', textAlign: 'center', padding: 24 }}>Loading…</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {Object.entries(status).map(([k, v]) => (
        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', background: 'rgba(10,11,18,0.6)', borderRadius: 5, fontSize: 11 }}>
          <span style={{ color: 'rgba(255,255,255,0.5)' }}>{k}</span>
          <span style={{ color: '#20D6C7', fontFamily: 'monospace' }}>{String(v)}</span>
        </div>
      ))}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function ForgeQueuePanel() {
  const [activeTab, setActiveTab] = useState(0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Tab row */}
      <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.08)', marginBottom: 12 }}>
        {TABS.map((tab, i) => (
          <button
            key={tab}
            onClick={() => setActiveTab(i)}
            style={{
              flex: 1,
              padding: '8px 4px',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === i ? '2px solid #20D6C7' : '2px solid transparent',
              color: activeTab === i ? '#20D6C7' : 'rgba(255,255,255,0.4)',
              fontSize: 10,
              cursor: 'pointer',
              transition: 'color 0.2s',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 0 && <ApprovalQueue />}
      {activeTab === 1 && <BuilderMode />}
      {activeTab === 2 && <EvolutionStatus />}
    </div>
  )
}
