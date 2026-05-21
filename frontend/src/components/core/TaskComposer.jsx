import { useMemo, useState } from 'react'
import api from '../../api/client'
import { useTaskStore } from '../../store/taskStore'
import './TaskComposer.css'

const DEFAULT_PRESETS = [
  {
    key: 'research',
    label: 'Research',
    prompt: 'Research this topic and return sources, decisions, and proof:',
  },
  {
    key: 'build',
    label: 'Build',
    prompt: 'Build a usable output for this request and include artifact proof:',
  },
  {
    key: 'analyze',
    label: 'Analyze',
    prompt: 'Analyze this and return findings, risks, next actions, and proof:',
  },
]

export const MONEY_PRESETS = [
  {
    key: 'discover',
    label: 'Find Opportunity',
    prompt: 'Money Mode: discover revenue opportunities. Do not publish, send outreach, spend money, accept paid work, or modify external accounts without approval. Goal:',
  },
  {
    key: 'draft',
    label: 'Draft Offer',
    prompt: 'Money Mode: draft an offer, pricing, delivery plan, and proof checklist. Keep this as a draft until approved. Goal:',
  },
  {
    key: 'evaluate',
    label: 'Evaluate Lead',
    prompt: 'Money Mode: evaluate this lead or paid task for fit, ROI, risk, required approvals, and next steps. Goal:',
  },
]

function buildTaskText(prefix, text) {
  const clean = String(text || '').trim()
  const intro = String(prefix || '').trim()
  return intro ? `${intro} ${clean}`.trim() : clean
}

export default function TaskComposer({
  title = 'RUN TASK',
  subtitle = 'One route for input, action, output and proof.',
  presets = DEFAULT_PRESETS,
  placeholder = 'Describe the result you want...',
  source = 'task-composer',
  compact = false,
  onResult,
}) {
  const [text, setText] = useState('')
  const [presetKey, setPresetKey] = useState(presets[0]?.key || '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [lastStatus, setLastStatus] = useState('')

  const addChatMessage = useTaskStore(s => s.addChatMessage)
  const upsertTurnMessage = useTaskStore(s => s.upsertTurnMessage)
  const setTyping = useTaskStore(s => s.setTyping)

  const selectedPreset = useMemo(
    () => presets.find(item => item.key === presetKey) || presets[0] || null,
    [presetKey, presets],
  )

  async function submitTask(event) {
    event?.preventDefault?.()
    const task = buildTaskText(selectedPreset?.prompt, text)
    if (!task || submitting) return
    setSubmitting(true)
    setError('')
    setLastStatus('running')
    addChatMessage?.({ role: 'user', content: task, source, ts: Date.now() })
    setTyping?.(true)
    try {
      const result = await api.post('/api/tasks/run', { task, user_id: 'user:operator' })
      if (result?.turn_id) upsertTurnMessage?.(result)
      else addChatMessage?.({ role: 'ai', content: result?.reply || result?.response || 'Task submitted.', source, ts: Date.now() })
      setText('')
      setLastStatus(result?.status || 'submitted')
      onResult?.(result)
    } catch (err) {
      const message = err?.message || 'Task submission failed'
      setError(message)
      setLastStatus('failed')
      addChatMessage?.({ role: 'ai', content: `Task failed: ${message}`, degraded: true, source, ts: Date.now() })
    } finally {
      setTyping?.(false)
      setSubmitting(false)
    }
  }

  return (
    <section className={`tcx ${compact ? 'tcx--compact' : ''}`} aria-label={title}>
      <div className="tcx__head">
        <div>
          <div className="tcx__title">{title}</div>
          <div className="tcx__sub">{subtitle}</div>
        </div>
        <span className={`tcx__state tcx__state--${lastStatus || 'idle'}`}>
          {(lastStatus || 'idle').replace(/_/g, ' ')}
        </span>
      </div>

      <div className="tcx__presets" role="tablist" aria-label="Task templates">
        {presets.map(item => (
          <button
            key={item.key}
            type="button"
            className={`tcx__preset ${presetKey === item.key ? 'tcx__preset--active' : ''}`}
            onClick={() => setPresetKey(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <form className="tcx__form" onSubmit={submitTask}>
        <textarea
          className="tcx__input"
          value={text}
          onChange={event => setText(event.target.value)}
          placeholder={placeholder}
          rows={compact ? 3 : 4}
        />
        <div className="tcx__bar">
          {error ? <span className="tcx__error">{error}</span> : <span className="tcx__hint">Returns a normalized turn with actions and proof.</span>}
          <button className="tcx__submit" type="submit" disabled={submitting || !text.trim()}>
            {submitting ? 'RUNNING' : 'RUN'}
          </button>
        </div>
      </form>
    </section>
  )
}
