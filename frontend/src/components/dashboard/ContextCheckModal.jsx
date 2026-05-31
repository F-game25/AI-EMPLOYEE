import { useState, useEffect, useCallback } from 'react'
import { useCognitiveStore } from '../../store/cognitiveStore'
import api from '../../api/client'
import './ContextCheckModal.css'

function scoreTier(score) {
  if (score >= 0.6) return 'high'
  if (score >= 0.35) return 'medium'
  return 'low'
}

export default function ContextCheckModal() {
  const contextCheck = useCognitiveStore(s => s.contextCheck)
  const clearContextCheck = useCognitiveStore(s => s.clearContextCheck)
  const [busy, setBusy] = useState(false)

  const respond = useCallback(async (choice) => {
    if (!contextCheck?.taskId || busy) return
    setBusy(true)
    try {
      await api.post(`/api/tasks/${encodeURIComponent(contextCheck.taskId)}/context-response`, { choice })
    } catch (e) {
      // best-effort — the AgentController times out to "continue" on no response
      console.warn('[ContextCheckModal] response failed', e)
    } finally {
      setBusy(false)
      clearContextCheck()
    }
  }, [contextCheck, busy, clearContextCheck])

  // Keyboard: Enter = research (deliberate "no, learn first"), Esc = continue
  useEffect(() => {
    if (!contextCheck) return
    const onKey = (e) => {
      if (e.key === 'Escape') respond('continue')
      else if (e.key === 'Enter') respond('research')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [contextCheck, respond])

  if (!contextCheck) return null

  const score = Number(contextCheck.score || 0)
  const tier = scoreTier(score)
  const pct = (score * 100).toFixed(0)

  return (
    <div className="ccm-backdrop" role="dialog" aria-modal="true" aria-labelledby="ccm-title">
      <div className="ccm-card">
        <div className="ccm-header">
          <span id="ccm-title" className="ccm-title">TASK — ENOUGH CONTEXT?</span>
          <span className={`ccm-score-pill ${tier}`}>{pct}% / 100</span>
        </div>

        <div className="ccm-goal">{contextCheck.goal || '(no goal)'}</div>

        <div className="ccm-metrics">
          <div className="ccm-metric">
            <span className="ccm-metric-label">Memory Hits</span>
            <span className="ccm-metric-value">{contextCheck.memory_hits ?? 0}</span>
          </div>
          <div className="ccm-metric">
            <span className="ccm-metric-label">Graph Concepts</span>
            <span className="ccm-metric-value">{contextCheck.graph_hits ?? 0}</span>
          </div>
          <div className="ccm-metric">
            <span className="ccm-metric-label">Confidence</span>
            <span className="ccm-metric-value">{tier.toUpperCase()}</span>
          </div>
        </div>

        {Array.isArray(contextCheck.gaps) && contextCheck.gaps.length > 0 && (
          <div className="ccm-gaps">
            <div className="ccm-gaps-label">Knowledge Gaps</div>
            <ul>
              {contextCheck.gaps.slice(0, 5).map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="ccm-actions">
          <button
            type="button"
            className="ccm-btn ccm-btn-secondary"
            onClick={() => respond('continue')}
            disabled={busy}
            title="Skip research and execute now (Esc)"
          >
            Yes, Continue
          </button>
          <button
            type="button"
            className="ccm-btn ccm-btn-primary"
            onClick={() => respond('research')}
            disabled={busy}
            title="Start online learning first (Enter)"
          >
            {busy ? 'Sending…' : 'No, Learn First'}
          </button>
        </div>
      </div>
    </div>
  )
}
