import { useEffect, useRef, useState, useCallback } from 'react'
import api from '../../api/client'
import './LearnTopicWizard.css'

const STEPS = ['TOPIC', 'DEPTH', 'SOURCES', 'VERIFY', 'EXECUTE', 'DONE']

const DEPTH_OPTIONS = [
  { id: 'shallow',    title: 'SHALLOW',    sub: '1 hop · ~5 sources · fast brief' },
  { id: 'normal',     title: 'NORMAL',     sub: '2 hops · ~12 sources · balanced' },
  { id: 'deep',       title: 'DEEP',       sub: '3 hops · ~25 sources · thorough' },
  { id: 'continuous', title: 'CONTINUOUS', sub: 'standing topic · auto-refresh' },
]

const SOURCE_TYPE_OPTIONS = ['academic', 'docs', 'blogs', 'news', 'forums', 'video']

const VERIFY_OPTIONS = [
  { id: 'strict',     title: 'STRICT',     sub: 'multi-source cross-check · high-trust only' },
  { id: 'normal',     title: 'NORMAL',     sub: 'cross-check key claims · mixed trust' },
  { id: 'permissive', title: 'PERMISSIVE', sub: 'accept single-source · low-trust ok' },
]

const trustColor = (t) => {
  const v = typeof t === 'number' ? t : 0.5
  if (v >= 0.75) return '#22c55e'
  if (v >= 0.5)  return '#fbbf24'
  if (v >= 0.25) return '#f97316'
  return '#ef4444'
}

export default function LearnTopicWizard({ open, onClose, presetTopic = '', presetMode = '' }) {
  const [step, setStep] = useState(1)
  const [topic, setTopic] = useState(presetTopic)
  const [scope, setScope] = useState('')
  const [subtopics, setSubtopics] = useState([])
  const [subtopicDraft, setSubtopicDraft] = useState('')
  const [depth, setDepth] = useState(presetMode === 'continuous' ? 'continuous' : 'normal')
  const [sourceTypes, setSourceTypes] = useState(['academic', 'docs', 'blogs'])
  const [budget, setBudget] = useState(2.0)
  const [discoveredSources, setDiscoveredSources] = useState([])
  const [selectedSources, setSelectedSources] = useState(new Set())
  const [verificationLevel, setVerificationLevel] = useState('normal')
  const [sessionId, setSessionId] = useState(null)
  const [progressLog, setProgressLog] = useState([])
  const [progressPct, setProgressPct] = useState(0)
  const [result, setResult] = useState(null)
  const [scheduleRecurring, setScheduleRecurring] = useState(presetMode === 'continuous')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const logEndRef = useRef(null)

  // Reset when closed
  useEffect(() => {
    if (!open) return
    setStep(1)
    setTopic(presetTopic)
    setScope('')
    setSubtopics([])
    setSubtopicDraft('')
    setDepth(presetMode === 'continuous' ? 'continuous' : 'normal')
    setSourceTypes(['academic', 'docs', 'blogs'])
    setBudget(2.0)
    setDiscoveredSources([])
    setSelectedSources(new Set())
    setVerificationLevel('normal')
    setSessionId(null)
    setProgressLog([])
    setProgressPct(0)
    setResult(null)
    setScheduleRecurring(presetMode === 'continuous')
    setBusy(false)
    setErr(null)
  }, [open, presetTopic, presetMode])

  // ESC to close
  useEffect(() => {
    if (!open) return
    const h = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])

  // Auto-scroll log
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [progressLog])

  // WS listener for learning progress
  useEffect(() => {
    if (!sessionId) return
    const handler = (ev) => {
      const detail = ev?.detail || {}
      const type = detail.type || ev?.type
      const data = detail.data || detail
      if (!data || (data.session_id && data.session_id !== sessionId)) return

      if (type === 'learning:progress' || type === 'learning:started') {
        const line = data.message || data.stage || JSON.stringify(data)
        setProgressLog(prev => [...prev, { text: line, ts: Date.now(), kind: 'info' }])
        if (typeof data.progress === 'number') setProgressPct(Math.min(95, data.progress * 100))
      }
      if (type === 'learning:completed') {
        setProgressPct(100)
        setResult({
          new_memories: data.new_memories || data.memories_added || 0,
          sources_used: data.sources_used || 0,
          skill_level_before: data.skill_level_before || 0,
          skill_level_after: data.skill_level_after || data.skill_level || 0,
          topic_id: data.topic_id || null,
        })
        setProgressLog(prev => [...prev, { text: 'learning session complete', ts: Date.now(), kind: 'ok' }])
        setStep(6)
      }
    }
    window.addEventListener('ws:event', handler)
    window.addEventListener('learning:progress', handler)
    window.addEventListener('learning:completed', handler)
    return () => {
      window.removeEventListener('ws:event', handler)
      window.removeEventListener('learning:progress', handler)
      window.removeEventListener('learning:completed', handler)
    }
  }, [sessionId])

  const toggleSet = (set, value) => {
    const next = new Set(set)
    if (next.has(value)) next.delete(value); else next.add(value)
    return next
  }

  const addSubtopic = () => {
    const v = subtopicDraft.trim()
    if (!v) return
    setSubtopics(prev => prev.includes(v) ? prev : [...prev, v])
    setSubtopicDraft('')
  }

  const goNext = useCallback(async () => {
    setErr(null)
    if (step === 2) {
      // Trigger source discovery before showing step 3
      setBusy(true)
      try {
        const q = `${topic} ${scope}`.trim()
        const resp = await api.post('/api/research/discover', {
          query: q, max_sources: 15, source_types: sourceTypes,
        })
        const sources = resp?.sources || resp?.candidates || []
        setDiscoveredSources(sources)
        // Pre-select high-trust by default
        setSelectedSources(new Set(
          sources.filter(s => (s.trust ?? s.trust_score ?? 0.5) >= 0.6).map((s, i) => s.id || s.url || `s${i}`)
        ))
        setStep(3)
      } catch (e) {
        setErr(e?.message || 'discovery failed')
        // Allow user to proceed anyway with empty sources
        setDiscoveredSources([])
        setStep(3)
      } finally { setBusy(false) }
      return
    }
    if (step === 4) {
      // Kick off learning
      setBusy(true)
      try {
        const selected = discoveredSources.filter((s, i) => selectedSources.has(s.id || s.url || `s${i}`))
        const payload = {
          topic,
          scope,
          subtopics,
          depth,
          source_types: sourceTypes,
          budget_usd: budget,
          sources: selected,
          verification: verificationLevel,
          continuous: depth === 'continuous' || scheduleRecurring,
        }
        const resp = await api.post('/api/learning/execute', payload)
        const sid = resp?.session_id || resp?.id || `s_${Date.now()}`
        setSessionId(sid)
        setProgressLog([{ text: `session ${sid} started`, ts: Date.now(), kind: 'info' }])
        setStep(5)
      } catch (e) {
        setErr(e?.message || 'failed to start learning session')
      } finally { setBusy(false) }
      return
    }
    setStep(s => Math.min(6, s + 1))
  }, [step, topic, scope, subtopics, depth, sourceTypes, budget, discoveredSources, selectedSources, verificationLevel, scheduleRecurring])

  const goBack = () => { setErr(null); setStep(s => Math.max(1, s - 1)) }

  const finish = async () => {
    if (scheduleRecurring && result?.topic_id) {
      try { await api.post(`/api/topics/${result.topic_id}/pin`, { pinned: true, schedule: 'every_6h' }) } catch {}
    }
    onClose?.()
  }

  // Validation per step
  const canAdvance = (() => {
    if (busy) return false
    if (step === 1) return topic.trim().length >= 2
    if (step === 2) return depth && sourceTypes.length > 0 && budget > 0
    if (step === 3) return selectedSources.size > 0
    if (step === 4) return !!verificationLevel
    if (step === 5) return !!result
    return true
  })()

  if (!open) return null

  return (
    <div className="ltw-overlay" role="dialog" aria-modal="true" aria-label="Learn topic wizard" onClick={(e) => { if (e.target === e.currentTarget) onClose?.() }}>
      <div className="ltw-modal">
        <header className="ltw-header">
          <span className="ltw-title">LEARN TOPIC — WIZARD</span>
          <button className="ltw-close" onClick={onClose} aria-label="Close">×</button>
        </header>

        <nav className="ltw-steps" aria-label="Wizard steps">
          {STEPS.map((label, i) => {
            const n = i + 1
            const cls = n === step ? 'ltw-step ltw-step--active'
                      : n < step  ? 'ltw-step ltw-step--done'
                                  : 'ltw-step'
            return <span key={label} className={cls}>{n}. {label}</span>
          })}
        </nav>

        <div className="ltw-body">
          {err && <div className="ltw-log-entry ltw-log-entry--err" style={{ marginBottom: 12 }}>⚠ {err}</div>}

          {/* STEP 1 — Topic & Scope */}
          {step === 1 && (
            <>
              <div className="ltw-field">
                <label className="ltw-label" htmlFor="ltw-topic">Topic</label>
                <input
                  id="ltw-topic"
                  className="ltw-input"
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  placeholder="e.g. Differential privacy in federated learning"
                  autoFocus
                />
              </div>
              <div className="ltw-field">
                <label className="ltw-label" htmlFor="ltw-scope">Scope (optional)</label>
                <textarea
                  id="ltw-scope"
                  className="ltw-textarea"
                  value={scope}
                  onChange={e => setScope(e.target.value)}
                  placeholder="What angle, depth, or constraints matter for this topic?"
                />
              </div>
              <div className="ltw-field">
                <label className="ltw-label">Subtopics (optional)</label>
                <div className="ltw-chip-row" style={{ marginBottom: 8 }}>
                  {subtopics.map(s => (
                    <button key={s} type="button" className="ltw-chip ltw-chip--active"
                            onClick={() => setSubtopics(prev => prev.filter(x => x !== s))}>
                      {s} ×
                    </button>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    className="ltw-input"
                    style={{ flex: 1 }}
                    value={subtopicDraft}
                    onChange={e => setSubtopicDraft(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSubtopic() } }}
                    placeholder="add subtopic + Enter"
                  />
                  <button type="button" className="ltw-btn ltw-btn--ghost" onClick={addSubtopic}>ADD</button>
                </div>
              </div>
            </>
          )}

          {/* STEP 2 — Depth & Budget */}
          {step === 2 && (
            <>
              <div className="ltw-field">
                <label className="ltw-label">Depth</label>
                <div className="ltw-radio-grid">
                  {DEPTH_OPTIONS.map(o => (
                    <button key={o.id} type="button"
                            className={`ltw-radio-card ${depth === o.id ? 'ltw-radio-card--active' : ''}`}
                            onClick={() => setDepth(o.id)}>
                      <div className="ltw-radio-card__title">{o.title}</div>
                      <div className="ltw-radio-card__sub">{o.sub}</div>
                    </button>
                  ))}
                </div>
              </div>
              <div className="ltw-field">
                <label className="ltw-label">Source types</label>
                <div className="ltw-chip-row">
                  {SOURCE_TYPE_OPTIONS.map(t => (
                    <button key={t} type="button"
                            className={`ltw-chip ${sourceTypes.includes(t) ? 'ltw-chip--active' : ''}`}
                            onClick={() => setSourceTypes(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t])}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div className="ltw-field">
                <label className="ltw-label" htmlFor="ltw-budget">Max LLM budget (USD)</label>
                <input
                  id="ltw-budget"
                  className="ltw-input"
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={budget}
                  onChange={e => setBudget(parseFloat(e.target.value) || 0)}
                />
                <div className="ltw-help">Hard ceiling for token spend on this session.</div>
              </div>
            </>
          )}

          {/* STEP 3 — Source Discovery */}
          {step === 3 && (
            <>
              <div className="ltw-source-toolbar">
                <button type="button" className="ltw-chip"
                        onClick={() => setSelectedSources(new Set(discoveredSources.map((s, i) => s.id || s.url || `s${i}`)))}>
                  select all
                </button>
                <button type="button" className="ltw-chip" onClick={() => setSelectedSources(new Set())}>
                  select none
                </button>
                <button type="button" className="ltw-chip"
                        onClick={() => setSelectedSources(new Set(
                          discoveredSources.filter(s => (s.trust ?? s.trust_score ?? 0.5) >= 0.75)
                            .map((s, i) => s.id || s.url || `s${i}`)
                        ))}>
                  high-trust only
                </button>
                <span style={{ marginLeft: 'auto', fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>
                  {selectedSources.size} / {discoveredSources.length} selected
                </span>
              </div>
              {discoveredSources.length === 0 && (
                <div className="ltw-help" style={{ textAlign: 'center', padding: 20 }}>
                  No sources discovered. Try going back and broadening scope.
                </div>
              )}
              {discoveredSources.map((s, i) => {
                const sid = s.id || s.url || `s${i}`
                const trust = s.trust ?? s.trust_score ?? 0.5
                const isSel = selectedSources.has(sid)
                return (
                  <div key={sid}
                       className={`ltw-source-card ${isSel ? 'ltw-source-card--selected' : ''}`}
                       onClick={() => setSelectedSources(prev => toggleSet(prev, sid))}>
                    <input type="checkbox" checked={isSel} readOnly tabIndex={-1} />
                    <span className="ltw-trust-dot" style={{ background: trustColor(trust) }} title={`trust: ${trust.toFixed(2)}`} />
                    <div className="ltw-source-meta">
                      <div className="ltw-source-domain">{s.domain || (s.url || '').replace(/^https?:\/\//, '').split('/')[0]}</div>
                      <div className="ltw-source-title">{s.title || s.url || 'untitled'}</div>
                      <div className="ltw-source-snippet">{s.snippet || s.summary || ''}</div>
                    </div>
                  </div>
                )
              })}
            </>
          )}

          {/* STEP 4 — Verification */}
          {step === 4 && (
            <div className="ltw-field">
              <label className="ltw-label">Verification level</label>
              <div className="ltw-radio-grid">
                {VERIFY_OPTIONS.map(o => (
                  <button key={o.id} type="button"
                          className={`ltw-radio-card ${verificationLevel === o.id ? 'ltw-radio-card--active' : ''}`}
                          onClick={() => setVerificationLevel(o.id)}
                          title={o.sub}>
                    <div className="ltw-radio-card__title">{o.title}</div>
                    <div className="ltw-radio-card__sub">{o.sub}</div>
                  </button>
                ))}
              </div>
              <div className="ltw-help" style={{ marginTop: 12 }}>
                Higher verification = slower, more expensive, but reduces hallucination + low-quality memory.
              </div>
            </div>
          )}

          {/* STEP 5 — Execute */}
          {step === 5 && (
            <div className="ltw-progress">
              <div className="ltw-progress-bar">
                <div className="ltw-progress-fill" style={{ width: `${progressPct}%` }} />
              </div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', marginBottom: 8 }}>
                session: {sessionId || '—'} · {Math.round(progressPct)}%
              </div>
              <div className="ltw-log">
                {progressLog.length === 0 && <div className="ltw-log-entry">waiting for first event…</div>}
                {progressLog.map((l, i) => (
                  <div key={i} className={`ltw-log-entry ${l.kind === 'ok' ? 'ltw-log-entry--ok' : ''} ${l.kind === 'err' ? 'ltw-log-entry--err' : ''}`}>
                    › {l.text}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            </div>
          )}

          {/* STEP 6 — Done */}
          {step === 6 && result && (
            <div className="ltw-skill-gauge">
              <div style={{ fontSize: 12, letterSpacing: 2, color: '#22c55e' }}>LEARNING COMPLETE</div>
              <div className="ltw-gauge-row">
                <span className="ltw-gauge-row__label">BEFORE</span>
                <div className="ltw-gauge-track">
                  <div className="ltw-gauge-fill" style={{ width: `${Math.round((result.skill_level_before || 0) * 100)}%` }} />
                </div>
                <span className="ltw-gauge-label">{Math.round((result.skill_level_before || 0) * 100)}%</span>
              </div>
              <div className="ltw-gauge-row">
                <span className="ltw-gauge-row__label">AFTER</span>
                <div className="ltw-gauge-track">
                  <div className="ltw-gauge-fill" style={{ width: `${Math.round((result.skill_level_after || 0) * 100)}%` }} />
                </div>
                <span className="ltw-gauge-label">{Math.round((result.skill_level_after || 0) * 100)}%</span>
              </div>
              <div className="ltw-gauge-delta">
                +{Math.round(((result.skill_level_after || 0) - (result.skill_level_before || 0)) * 100)} pts
              </div>

              <div className="ltw-summary-stats">
                <div className="ltw-stat">
                  <div className="ltw-stat__value">{result.new_memories}</div>
                  <div className="ltw-stat__label">NEW MEMORIES</div>
                </div>
                <div className="ltw-stat">
                  <div className="ltw-stat__value">{result.sources_used}</div>
                  <div className="ltw-stat__label">SOURCES USED</div>
                </div>
                <div className="ltw-stat">
                  <div className="ltw-stat__value">{Math.round(progressPct)}%</div>
                  <div className="ltw-stat__label">PROGRESS</div>
                </div>
              </div>

              <label className="ltw-toggle-row" style={{ width: '100%' }}>
                <input
                  type="checkbox"
                  checked={scheduleRecurring}
                  onChange={e => setScheduleRecurring(e.target.checked)}
                />
                <span style={{ fontSize: 11 }}>Schedule recurring updates (every 6h)</span>
              </label>
            </div>
          )}
        </div>

        <footer className="ltw-footer">
          <button type="button" className="ltw-btn ltw-btn--ghost" onClick={goBack} disabled={step === 1 || step === 5 || busy}>
            BACK
          </button>
          {step < 5 && (
            <button type="button" className="ltw-btn ltw-btn--primary" onClick={goNext} disabled={!canAdvance}>
              {busy ? '…' : step === 4 ? 'START LEARNING' : 'NEXT'}
            </button>
          )}
          {step === 5 && (
            <button type="button" className="ltw-btn ltw-btn--ghost" onClick={onClose}>
              RUN IN BACKGROUND
            </button>
          )}
          {step === 6 && (
            <button type="button" className="ltw-btn ltw-btn--primary" onClick={finish}>
              DONE
            </button>
          )}
        </footer>
      </div>
    </div>
  )
}
