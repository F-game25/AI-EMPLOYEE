import { useCallback, useEffect, useState } from 'react'
import Panel from '../nexus-ui/Panel'
import StatusPill from '../nexus-ui/StatusPill'
import { EmptyState, ErrorState, NxButton, LoadingSkeleton } from '../nexus-ui'
import api from '../../api/client'
import { fmtDate } from '../../utils/format'
import './CompanyBuilderPage.css'

// ── verdict → visual tone ───────────────────────────────────────────────────
const VERDICT_TONE = {
  build:         { tone: 'success', label: 'BUILD' },
  pivot:         { tone: 'warn',    label: 'PIVOT' },
  need_evidence: { tone: 'warn',    label: 'NEED EVIDENCE' },
  reject:        { tone: 'alert',   label: 'REJECT' },
}

const STATUS_TONE = {
  building:  'cool',
  validated: 'success',
  draft:     'idle',
  intake:    'idle',
  blocked:   'alert',
}

const SCORE_DIMS = [
  { key: 'demand',          label: 'Demand' },
  { key: 'competition_gap', label: 'Competition gap' },
  { key: 'monetization',    label: 'Monetization' },
  { key: 'feasibility',     label: 'Feasibility' },
]

function pct(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  // scores may arrive 0–1 or 0–100; normalise to 0–100
  return Math.max(0, Math.min(100, n <= 1 ? n * 100 : n))
}

function scoreTone(p) {
  return p >= 66 ? 'ok' : p >= 40 ? 'warn' : 'crit'
}

// ── Score bars ──────────────────────────────────────────────────────────────
function ScoreBars({ scores }) {
  if (!scores) return null
  return (
    <div className="cob-scores">
      {SCORE_DIMS.map(({ key, label }) => {
        const p = pct(scores[key])
        return (
          <div key={key} className="cob-score">
            <div className="cob-score__head">
              <span className="cob-score__label">{label}</span>
              <span className="cob-score__val">{Math.round(p)}%</span>
            </div>
            <div className="cob-score__track">
              <div className={`cob-score__fill cob-score__fill--${scoreTone(p)}`} style={{ width: `${p}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Validation panel — the hero "validate before build" differentiator ───────
function ValidationView({ validation }) {
  if (!validation) return null
  const v = VERDICT_TONE[validation.verdict] || { tone: 'idle', label: (validation.verdict || 'UNKNOWN').toUpperCase() }
  const composite = pct(validation.composite)
  const confidence = pct(validation.confidence)
  return (
    <div className="cob-validation">
      <div className="cob-validation__verdict">
        <span className="cob-validation__verdict-tag">VERDICT</span>
        <StatusPill label={v.label} tone={v.tone} />
        <div className="cob-validation__composite">
          <span className="cob-validation__composite-num">{Math.round(composite)}</span>
          <span className="cob-validation__composite-lbl">composite</span>
        </div>
        <div className="cob-validation__composite">
          <span className="cob-validation__composite-num">{Math.round(confidence)}%</span>
          <span className="cob-validation__composite-lbl">confidence</span>
        </div>
      </div>

      <ScoreBars scores={validation.scores} />

      {validation.strongest_objection && (
        <div className="cob-objection">
          <span className="cob-objection__tag">STRONGEST OBJECTION</span>
          <p className="cob-objection__text">{validation.strongest_objection}</p>
        </div>
      )}

      {Array.isArray(validation.reasons) && validation.reasons.length > 0 && (
        <ul className="cob-reasons">
          {validation.reasons.map((r, i) => <li key={i} className="cob-reasons__item">{r}</li>)}
        </ul>
      )}

      {validation.recommendation && (
        <div className="cob-reco">
          <span className="cob-reco__tag">RECOMMENDATION</span>
          <p className="cob-reco__text">{validation.recommendation}</p>
        </div>
      )}
    </div>
  )
}

// ── Refinement suggestions (pivot cards) ─────────────────────────────────────
function RefinementView({ refinement, onUseIdea }) {
  if (!refinement) return null
  const suggestions = refinement.suggestions || []
  const weak = refinement.weak_dimensions || []
  return (
    <div className="cob-refine">
      {weak.length > 0 && (
        <div className="cob-refine__weak">
          <span className="cob-refine__weak-tag">WEAK DIMENSIONS</span>
          {weak.map((w, i) => <StatusPill key={i} label={String(w).toUpperCase()} tone="warn" size="sm" />)}
        </div>
      )}

      {suggestions.length === 0 ? (
        <EmptyState icon="◈" title="No pivot suggestions" sub="The validator did not propose alternative angles." />
      ) : (
        <div className="cob-refine__cards">
          {suggestions.map((s, i) => (
            <div key={i} className="cob-suggestion">
              <div className="cob-suggestion__head">
                <span className="cob-suggestion__angle">{s.angle || `Angle ${i + 1}`}</span>
                {s.targets && <StatusPill label={String(s.targets).toUpperCase()} tone="cool" size="sm" />}
              </div>
              {s.change && <p className="cob-suggestion__change">{s.change}</p>}
              {s.why && <p className="cob-suggestion__why"><span>Why:</span> {s.why}</p>}
            </div>
          ))}
        </div>
      )}

      {refinement.improved_idea && (
        <div className="cob-improved">
          <span className="cob-improved__tag">IMPROVED IDEA</span>
          <p className="cob-improved__text">{refinement.improved_idea}</p>
          <NxButton variant="primary" size="sm" onClick={() => onUseIdea(refinement.improved_idea)}>
            Use this idea
          </NxButton>
        </div>
      )}
    </div>
  )
}

// ── Start-a-company form ─────────────────────────────────────────────────────
function StartCompanyForm({ onStarted }) {
  const [name, setName] = useState('')
  const [idea, setIdea] = useState('')
  const [targetCustomer, setTargetCustomer] = useState('')
  const [problem, setProblem] = useState('')
  const [monetization, setMonetization] = useState('')
  const [openAnswers, setOpenAnswers] = useState({})
  const [intake, setIntake] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = useCallback(async (extraAnswers = {}) => {
    if (!name.trim() || !idea.trim()) {
      setError('Name and idea are required.')
      return
    }
    setBusy(true); setError(null)
    try {
      const answers = {
        ...(targetCustomer.trim() && { target_customer: targetCustomer.trim() }),
        ...(problem.trim() && { problem: problem.trim() }),
        ...(monetization.trim() && { monetization: monetization.trim() }),
        ...openAnswers,
        ...extraAnswers,
      }
      const res = await api.company.start({ name: name.trim(), idea: idea.trim(), answers })
      setIntake(res.intake || null)
      if (res.company) onStarted?.(res.company)
    } catch (e) {
      setError(e.message || 'Failed to start company.')
    } finally {
      setBusy(false)
    }
  }, [name, idea, targetCustomer, problem, monetization, openAnswers, onStarted])

  const openQuestions = intake?.open_questions || []

  return (
    <div className="cob-form">
      <label className="cob-field">
        <span className="cob-field__label">Company name</span>
        <input className="cob-input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. NorthSignal" disabled={busy} />
      </label>

      <label className="cob-field">
        <span className="cob-field__label">The idea</span>
        <textarea className="cob-textarea" rows={4} value={idea} onChange={e => setIdea(e.target.value)} placeholder="Describe what the company does and for whom…" disabled={busy} />
      </label>

      <div className="cob-form__grid">
        <label className="cob-field">
          <span className="cob-field__label">Target customer <em>(optional)</em></span>
          <input className="cob-input" value={targetCustomer} onChange={e => setTargetCustomer(e.target.value)} placeholder="Who buys this?" disabled={busy} />
        </label>
        <label className="cob-field">
          <span className="cob-field__label">Problem <em>(optional)</em></span>
          <input className="cob-input" value={problem} onChange={e => setProblem(e.target.value)} placeholder="What pain does it solve?" disabled={busy} />
        </label>
        <label className="cob-field">
          <span className="cob-field__label">Monetization <em>(optional)</em></span>
          <input className="cob-input" value={monetization} onChange={e => setMonetization(e.target.value)} placeholder="How does it earn?" disabled={busy} />
        </label>
      </div>

      {error && <ErrorState message={error} />}

      <NxButton variant="primary" loading={busy} onClick={() => submit()}>
        {busy ? 'Drafting brief…' : 'Start company'}
      </NxButton>

      {/* Intake result */}
      {intake && (
        <div className="cob-intake">
          {intake.surprise_me_warning && (
            <div className="cob-warning">
              <span className="cob-warning__icon">⚠</span>
              <span>{intake.surprise_me_warning}</span>
            </div>
          )}

          {intake.brief && (
            <div className="cob-intake__brief">
              <span className="cob-intake__brief-tag">BRIEF</span>
              <p>{intake.brief}</p>
            </div>
          )}

          <div className="cob-intake__ready">
            <StatusPill
              label={intake.ready ? 'READY' : 'NEEDS MORE INPUT'}
              tone={intake.ready ? 'success' : 'warn'}
              size="sm"
            />
          </div>

          {!intake.ready && openQuestions.length > 0 && (
            <div className="cob-open-questions">
              <span className="cob-open-questions__tag">OPEN QUESTIONS</span>
              {openQuestions.map((q, i) => {
                const key = typeof q === 'string' ? q : (q.id || q.key || `q_${i}`)
                const prompt = typeof q === 'string' ? q : (q.question || q.prompt || q.label || key)
                return (
                  <label key={key} className="cob-field">
                    <span className="cob-field__label">{prompt}</span>
                    <input
                      className="cob-input"
                      value={openAnswers[key] || ''}
                      onChange={e => setOpenAnswers(prev => ({ ...prev, [key]: e.target.value }))}
                      placeholder="Your answer…"
                      disabled={busy}
                    />
                  </label>
                )
              })}
              <NxButton variant="primary" size="sm" loading={busy} onClick={() => submit()}>
                Submit answers
              </NxButton>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Decisions log (anti-Polsia transparency) ─────────────────────────────────
function DecisionsLog({ decisions }) {
  if (!Array.isArray(decisions) || decisions.length === 0) {
    return <EmptyState icon="◷" title="No decisions yet" sub="Every decision the builder makes is logged here." />
  }
  return (
    <ul className="cob-decisions">
      {decisions.map((d, i) => (
        <li key={d.id || i} className="cob-decision">
          <div className="cob-decision__head">
            <span className="cob-decision__what">{d.what || d.action || d.decision || 'Decision'}</span>
            {d.ts && <span className="cob-decision__ts">{fmtDate(d.ts, { time: true })}</span>}
          </div>
          {(d.why || d.reason) && <p className="cob-decision__why">{d.why || d.reason}</p>}
        </li>
      ))}
    </ul>
  )
}

// ── Build gate ───────────────────────────────────────────────────────────────
function BuildGate({ company, onBuilt }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [blocked, setBlocked] = useState(null)
  const [overrideOpen, setOverrideOpen] = useState(false)
  const [overrideReason, setOverrideReason] = useState('')

  const status = company?.status

  const runBuild = useCallback(async (override = false) => {
    if (override && !overrideReason.trim()) {
      setError('An override reason is required.')
      return
    }
    setBusy(true); setError(null); setBlocked(null)
    try {
      const body = override ? { override: true, override_reason: overrideReason.trim() } : {}
      const res = await api.company.build(company.id, body)
      onBuilt?.(res)
      setOverrideOpen(false); setOverrideReason('')
    } catch (e) {
      // 409 → blocked: surface the reason, never hide it
      if (e.status === 409 && e.body?.blocked) {
        setBlocked(e.body)
      } else {
        setError(e.message || 'Build failed.')
      }
    } finally {
      setBusy(false)
    }
  }, [company, overrideReason, onBuilt])

  if (status === 'building') {
    return (
      <div className="cob-build cob-build--active">
        <StatusPill label="BUILDING" tone="cool" />
        <span className="cob-build__note">Build in progress — the company is being assembled.</span>
      </div>
    )
  }

  return (
    <div className="cob-build">
      <NxButton variant="primary" loading={busy} onClick={() => runBuild(false)}>
        Begin build
      </NxButton>

      {error && <ErrorState message={error} />}

      {blocked && (
        <div className="cob-blocked">
          <div className="cob-blocked__head">
            <span className="cob-blocked__icon">⛔</span>
            <span className="cob-blocked__title">Build blocked</span>
          </div>
          <p className="cob-blocked__reason">{blocked.reason || 'Idea must be validated before building.'}</p>
          {blocked.validation && (
            <div className="cob-blocked__validation">
              <ValidationView validation={blocked.validation} />
            </div>
          )}

          {!overrideOpen ? (
            <NxButton variant="warn" size="sm" onClick={() => setOverrideOpen(true)}>
              Override (requires reason)
            </NxButton>
          ) : (
            <div className="cob-override">
              <textarea
                className="cob-textarea"
                rows={2}
                value={overrideReason}
                onChange={e => setOverrideReason(e.target.value)}
                placeholder="Why are you overriding the validation gate?"
                disabled={busy}
              />
              <div className="cob-override__actions">
                <NxButton variant="danger" size="sm" loading={busy} onClick={() => runBuild(true)}>
                  Confirm override & build
                </NxButton>
                <NxButton variant="ghost" size="sm" disabled={busy} onClick={() => { setOverrideOpen(false); setOverrideReason('') }}>
                  Cancel
                </NxButton>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Detail view for a selected company ───────────────────────────────────────
function CompanyDetail({ companyId, onChanged }) {
  const [state, setState] = useState({ loading: true, error: null, company: null })
  const [validateBusy, setValidateBusy] = useState(false)
  const [validateErr, setValidateErr] = useState(null)
  const [refineBusy, setRefineBusy] = useState(false)
  const [refineErr, setRefineErr] = useState(null)
  const [refineResult, setRefineResult] = useState(null)

  const load = useCallback(async () => {
    setState(s => ({ ...s, loading: true, error: null }))
    try {
      const res = await api.company.get(companyId)
      setState({ loading: false, error: null, company: res.company || null })
    } catch (e) {
      setState({ loading: false, error: e.message || 'Failed to load company.', company: null })
    }
  }, [companyId])

  useEffect(() => { setRefineResult(null); load() }, [load])

  const company = state.company

  const runValidate = useCallback(async () => {
    setValidateBusy(true); setValidateErr(null)
    try {
      const res = await api.company.validate(companyId)
      setState(s => ({
        ...s,
        company: { ...(s.company || {}), validation: res.validation, refinement: res.refinement, can_build: res.can_build },
      }))
      onChanged?.()
    } catch (e) {
      setValidateErr(e.message || 'Validation failed.')
    } finally {
      setValidateBusy(false)
    }
  }, [companyId, onChanged])

  const runRefine = useCallback(async (ideaText) => {
    const idea = ideaText ?? company?.brief?.idea ?? company?.brief
    if (!idea) { setRefineErr('No idea text available to refine.'); return }
    setRefineBusy(true); setRefineErr(null)
    try {
      const res = await api.company.refine(typeof idea === 'string' ? idea : JSON.stringify(idea))
      setRefineResult(res)
    } catch (e) {
      setRefineErr(e.message || 'Refine failed.')
    } finally {
      setRefineBusy(false)
    }
  }, [company])

  if (state.loading) {
    return <Panel title="COMPANY" tone="gold"><LoadingSkeleton variant="card" /></Panel>
  }
  if (state.error) {
    return <Panel title="COMPANY" tone="alert"><ErrorState message={state.error} onRetry={load} /></Panel>
  }
  if (!company) {
    return <Panel title="COMPANY" tone="gold"><EmptyState icon="◈" title="Company not found" /></Panel>
  }

  const refinement = refineResult || company.refinement
  const validation = company.validation

  return (
    <div className="cob-detail">
      <Panel
        title={(company.name || 'COMPANY').toUpperCase()}
        icon="▲"
        tone="gold"
        actions={<StatusPill label={(company.status || 'draft').toUpperCase()} tone={STATUS_TONE[company.status] || 'idle'} size="sm" />}
      >
        {company.brief && (
          <div className="cob-detail__brief">
            {typeof company.brief === 'string'
              ? <p>{company.brief}</p>
              : <p>{company.brief.summary || company.brief.idea || JSON.stringify(company.brief)}</p>}
          </div>
        )}
      </Panel>

      {/* Validation — hero differentiator */}
      <Panel
        title="VALIDATE DEMAND — BEFORE YOU BUILD"
        icon="✓"
        tone="gold"
        actions={<NxButton variant="primary" size="sm" loading={validateBusy} onClick={runValidate}>Validate demand</NxButton>}
      >
        {validateBusy && <div className="cob-loading">Running demand validation… this can take 30–120s.</div>}
        {validateErr && <ErrorState message={validateErr} />}
        {!validateBusy && !validation && !validateErr && (
          <EmptyState icon="✓" title="Not validated yet" sub="Run demand validation before building. The build gate enforces this." />
        )}
        {validation && <ValidationView validation={validation} />}
      </Panel>

      {/* Refinement */}
      <Panel
        title="REFINE & PIVOT"
        icon="↻"
        tone="cool"
        actions={<NxButton variant="ghost" size="sm" loading={refineBusy} onClick={() => runRefine()}>Refine this idea</NxButton>}
      >
        {refineBusy && <div className="cob-loading">Generating pivot suggestions… this can take 30–120s.</div>}
        {refineErr && <ErrorState message={refineErr} />}
        {!refineBusy && !refinement && !refineErr && (
          <EmptyState icon="↻" title="No refinement yet" sub="Refine to surface pivot angles and a stronger idea." />
        )}
        {refinement && <RefinementView refinement={refinement} onUseIdea={(idea) => runRefine(idea)} />}
      </Panel>

      {/* Build gate */}
      <Panel title="BUILD GATE" icon="▶" tone="gold">
        <BuildGate company={company} onBuilt={() => { load(); onChanged?.() }} />
      </Panel>

      {/* Decisions log */}
      <Panel title="DECISIONS LOG" icon="◷" tone="cool" sub="Transparent audit — what, why, when">
        <DecisionsLog decisions={company.decisions} />
      </Panel>
    </div>
  )
}

// ── Company list ─────────────────────────────────────────────────────────────
function CompanyList({ companies, selectedId, onSelect }) {
  if (!companies.length) {
    return <EmptyState icon="◈" title="No companies yet" sub="Start one from an idea using the form." />
  }
  return (
    <ul className="cob-list">
      {companies.map((c) => (
        <li key={c.id}>
          <button
            className={`cob-list__item ${selectedId === c.id ? 'cob-list__item--active' : ''}`}
            onClick={() => onSelect(c.id)}
          >
            <span className="cob-list__name">{c.name || c.id}</span>
            <StatusPill label={(c.status || 'draft').toUpperCase()} tone={STATUS_TONE[c.status] || 'idle'} size="sm" />
          </button>
        </li>
      ))}
    </ul>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function CompanyBuilderPage() {
  const [listState, setListState] = useState({ loading: true, error: null, companies: [] })
  const [selectedId, setSelectedId] = useState(null)

  const loadList = useCallback(async () => {
    setListState(s => ({ ...s, loading: true, error: null }))
    try {
      const res = await api.company.list()
      const companies = res.companies || []
      setListState({ loading: false, error: null, companies })
      setSelectedId(prev => prev && companies.some(c => c.id === prev) ? prev : (companies[0]?.id || null))
    } catch (e) {
      setListState({ loading: false, error: e.message || 'Failed to load companies.', companies: [] })
    }
  }, [])

  useEffect(() => { loadList() }, [loadList])

  const handleStarted = useCallback((company) => {
    loadList()
    if (company?.id) setSelectedId(company.id)
  }, [loadList])

  const companies = listState.companies

  return (
    <div className="cob-page">
      <header className="cob-header">
        <div>
          <h1 className="cob-title">Company Builder</h1>
          <p className="cob-subtitle">Validate demand before you build. Every decision logged.</p>
        </div>
      </header>

      <div className="cob-layout">
        {/* Left column — list + start form */}
        <aside className="cob-aside">
          <Panel title="COMPANIES" icon="◆" tone="gold">
            {listState.loading
              ? <LoadingSkeleton variant="rows" rows={4} />
              : listState.error
                ? <ErrorState message={listState.error} onRetry={loadList} />
                : <CompanyList companies={companies} selectedId={selectedId} onSelect={setSelectedId} />}
          </Panel>

          <Panel title="START A COMPANY" icon="+" tone="cool">
            <StartCompanyForm onStarted={handleStarted} />
          </Panel>
        </aside>

        {/* Right column — selected company cockpit */}
        <section className="cob-main">
          {selectedId
            ? <CompanyDetail companyId={selectedId} onChanged={loadList} />
            : (
              <Panel title="COCKPIT" tone="gold">
                <EmptyState icon="▲" title="No company selected" sub="Select a company on the left, or start one from an idea." />
              </Panel>
            )}
        </section>
      </div>
    </div>
  )
}
