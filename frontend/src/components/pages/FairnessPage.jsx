import { useState, useEffect } from 'react'
import { Panel, KPITile, StatusPill, HexButton } from '../nexus-ui'
import api from '../../api/client'
import './FairnessPage.css'

export default function FairnessPage() {
  const [categories, setCategories] = useState([])
  const [samples, setSamples] = useState([])
  const [audits, setAudits] = useState([])
  const [loading, setLoading] = useState(true)
  const [sel, setSel] = useState(null)
  const [correcting, setCorrecting] = useState(false)
  const [corrected, setCorrected] = useState(null)

  useEffect(() => {
    const fetchFairness = async () => {
      try {
        const fairness = await api.get('/api/fairness/report')
        setCategories(fairness?.categories || [])
        setSamples(fairness?.samples || [])

        const audit = await api.get('/api/audit/events')
        if (audit?.events) {
          const batches = {}
          audit.events.forEach(e => {
            const date = new Date(e.ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
            if (!batches[date]) batches[date] = { date, outputs: 0, flagged: 0, passed: true }
            batches[date].outputs++
            if (e.severity === 'HIGH' || e.severity === 'WARN') batches[date].flagged++
            if (e.severity === 'ERROR') batches[date].passed = false
          })
          setAudits(Object.values(batches).slice(0, 4))
        }
        setLoading(false)
      } catch (e) {
        setLoading(false)
      }
    }
    fetchFairness()
    const t = setInterval(fetchFairness, 8000)
    return () => clearInterval(t)
  }, [])

  const selS = sel ?? (samples.length > 0 ? samples[0] : null)

  const handleApplyCorrection = async () => {
    if (!selS) return
    setCorrecting(true)
    setCorrected(null)
    try {
      await api.chat.send(`Apply fairness correction for flag "${selS.flag}": Replace "${selS.output}" with "${selS.corrected}"`)
      setCorrected({ ok: true, id: selS.id })
    } catch {
      setCorrected({ ok: false, id: selS.id })
    }
    setCorrecting(false)
  }

  const avgScore = categories.length ? Math.round(categories.reduce((a, c) => a + (c.score || 0), 0) / categories.length) : loading ? 0 : 100
  const totalFlagged = categories.reduce((a, c) => a + (c.flagged || 0), 0)
  const passedAudits = audits.filter(a => a.passed).length

  const avgScoreTone = avgScore > 90 ? 'success' : 'warning'

  return (
    <div className="fa-grid">
      <div className="fa-kpis">
        <KPITile icon="⚖" iconTone={avgScoreTone} label="Fairness Score" value={loading ? '—' : `${avgScore}/100`} sub="Avg across categories" accent />
        <KPITile icon="◈" iconTone="cyan" label="Outputs Audited" value={loading ? '—' : categories[0]?.samples || '0'} sub="Latest audit" />
        <KPITile icon="🚩" iconTone={totalFlagged > 5 ? 'warning' : 'success'} label="Flags Raised" value={loading ? '—' : totalFlagged} sub="This batch" />
        <KPITile icon="✓" iconTone="success" label="Passed Audits" value={loading ? '—' : `${passedAudits}/${audits.length}`} sub="Recent history" />
      </div>

      <div className="fa-cols">
        <div className="fa-col">
          <Panel icon="🔍" title="Bias Categories" className="fa-panel" actions={<StatusPill tone="gold" label={loading ? 'LOADING' : 'REPORT'} dot={false} size="sm" />}>
            {loading ? (
              <div className="fa-empty">Fetching fairness report…</div>
            ) : !categories.length ? (
              <div className="fa-empty">No categories available</div>
            ) : (
              <div className="fa-categories">
                {categories.map(c => (
                  <div key={c.cat} className="fa-category">
                    <div className="fa-category__head">
                      <span className="fa-category__name">{c.cat}</span>
                      <div className="fa-category__bar">
                        <div className="fa-category__progress" style={{ width: `${c.score}%` }} />
                      </div>
                      <span className={`fa-category__score fa-category__score--${c.score > 93 ? 'high' : c.score > 85 ? 'mid' : 'low'}`}>{c.score}%</span>
                      <span className={`fa-category__flags ${c.flagged > 0 ? 'is-active' : ''}`}>{c.flagged}</span>
                    </div>
                    {c.flagged > 0 && <div className="fa-category__bias">{c.bias}</div>}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel icon="📋" title="Audit History" className="fa-panel fa-col__grow">
            {loading ? (
              <div className="fa-empty">Loading audit history…</div>
            ) : (
              <div className="fa-audit-table">
                <div className="fa-audit-header">
                  <span>Date</span>
                  <span>Outputs</span>
                  <span>Flagged</span>
                  <span>Status</span>
                </div>
                {audits.map((a, i) => (
                  <div key={i} className={`fa-audit-row fa-audit-row--${a.passed ? 'pass' : 'fail'}`}>
                    <span className="fa-audit-row__date">{a.date}</span>
                    <span className="fa-audit-row__outputs">{a.outputs}</span>
                    <span className={`fa-audit-row__flagged ${a.flagged > 5 ? 'is-high' : a.flagged > 0 ? 'is-med' : ''}`}>{a.flagged}</span>
                    <StatusPill tone={a.passed ? 'success' : 'alert'} label={a.passed ? 'PASS' : 'FAIL'} dot={false} size="xs" />
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="fa-col">
          <Panel icon="🚨" title="Flagged Samples" className="fa-panel">
            {loading ? (
              <div className="fa-empty">Loading samples…</div>
            ) : !samples.length ? (
              <div className="fa-empty fa-empty--ok">✓ No flagged samples</div>
            ) : (
              <div className="fa-samples">
                {samples.map(s => (
                  <button key={s.id} onClick={() => setSel(s)} className={`fa-sample ${selS?.id === s.id ? 'is-selected' : ''}`}>
                    <div className="fa-sample__head">
                      <StatusPill tone={s.severity === 'HIGH' ? 'alert' : 'warning'} label={s.severity} dot={false} size="xs" />
                      <span className="fa-sample__flag">{s.flag.replace(/_/g, ' ')}</span>
                    </div>
                    <div className="fa-sample__output">{s.output}</div>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          {selS && (
            <Panel icon="◈" title="Sample Detail" className="fa-panel fa-col__grow">
              <div className="fa-detail">
                <div className="fa-detail__label">ORIGINAL</div>
                <div className="fa-detail__box fa-detail__box--original">{selS.output}</div>

                <div className="fa-detail__label">CORRECTED</div>
                <div className="fa-detail__box fa-detail__box--corrected">{selS.corrected}</div>

                <HexButton
                  onClick={handleApplyCorrection}
                  disabled={correcting}
                  variant="primary"
                  tone={corrected?.ok && corrected?.id === selS?.id ? 'success' : corrected?.id === selS?.id ? 'alert' : 'gold'}
                  size="sm"
                  className="fa-apply-btn"
                >
                  {correcting ? 'APPLYING…' : corrected?.ok && corrected?.id === selS?.id ? '✓ APPLIED' : corrected?.id === selS?.id ? '✗ FAILED' : 'APPLY CORRECTION'}
                </HexButton>
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}
