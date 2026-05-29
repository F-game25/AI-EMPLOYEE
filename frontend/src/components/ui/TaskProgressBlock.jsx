import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const STATUS_ICON  = { pending: '○', active: '●', done: '✓', error: '✗' }
const STATUS_COLOR = {
  pending: 'rgba(255,255,255,0.25)',
  active:  '#20D6C7',
  done:    '#22C55E',
  error:   '#EF4444',
}

function MiniGraph({ data = [] }) {
  const canvasRef = useRef(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || data.length < 2) return
    const ctx = canvas.getContext('2d')
    const { width: w, height: h } = canvas
    ctx.clearRect(0, 0, w, h)
    const pts = data.slice(-12)
    const max = Math.max(...pts, 1)
    const step = w / Math.max(pts.length - 1, 1)
    ctx.beginPath()
    pts.forEach((v, i) => {
      const x = i * step
      const y = h - (v / max) * (h - 4) - 2
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.strokeStyle = 'rgba(32,214,199,0.7)'
    ctx.lineWidth = 1.5
    ctx.stroke()
    ctx.lineTo((pts.length - 1) * step, h)
    ctx.lineTo(0, h)
    ctx.closePath()
    ctx.fillStyle = 'rgba(32,214,199,0.08)'
    ctx.fill()
  }, [data])
  if (data.length < 2) return null
  return <canvas ref={canvasRef} width={200} height={36} style={{ width: '100%', height: 36, marginTop: 8 }} />
}

export default function TaskProgressBlock({ taskId, title, steps: propSteps = [], graph: propGraph = [] }) {
  // SSE-driven state — active when taskId is provided and not externally controlled
  const [liveSteps, setLiveSteps] = useState(null)  // null = use props
  const [liveGraph, setLiveGraph] = useState(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!taskId) return
    const token = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('ai_jwt') : null
    // EventSource doesn't support custom headers; pass token as query param for SSE auth
    const url = `/api/tasks/${taskId}/progress${token ? `?token=${encodeURIComponent(token)}` : ''}`
    const es = new EventSource(url)
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'heartbeat' || data.type === 'connected') return
        if (data.type === 'snapshot' && Array.isArray(data.steps)) {
          setLiveSteps(data.steps.map(s => ({
            id: s.id ?? s.step_id,
            label: s.label ?? s.name ?? String(s.id),
            status: s.status ?? 'pending',
            elapsed: s.elapsed_ms ?? s.elapsed ?? null,
          })))
        } else if (data.type === 'task_progress' && Array.isArray(data.steps)) {
          setLiveSteps(data.steps.map(s => ({
            id: s.id ?? s.step_id,
            label: s.label ?? s.name ?? String(s.id),
            status: s.status ?? 'pending',
            elapsed: s.elapsed_ms ?? s.elapsed ?? null,
          })))
          if (typeof data.percent === 'number') {
            setLiveGraph(prev => [...(prev || []), data.percent])
          }
        } else if (data.type === 'workflow_update') {
          const status = data.status === 'complete' ? 'done'
            : data.status === 'running' ? 'active'
            : data.status === 'failed' ? 'error' : 'pending'
          setLiveSteps(prev => {
            const next = (prev || propSteps).map(s =>
              (s.id === data.task_id || s.id === data.taskId) ? { ...s, status } : s
            )
            return next
          })
        }
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'done' || data.status === 'error') {
          setDone(true)
          es.close()
        }
      } catch (_) {}
    }
    es.onerror = () => { es.close() }
    return () => { es.close() }
  }, [taskId]) // eslint-disable-line react-hooks/exhaustive-deps

  const steps = (liveSteps !== null ? liveSteps : propSteps)
  const graph  = (liveGraph !== null ? liveGraph : propGraph)

  const isActive  = !done && steps.some(s => s.status === 'active')
  const doneCount = steps.filter(s => s.status === 'done').length
  const errCount  = steps.filter(s => s.status === 'error').length

  return (
    <div style={{
      background: 'rgba(0,0,0,0.3)',
      border: '1px solid rgba(229,199,107,0.15)',
      borderLeft: '3px solid rgba(229,199,107,0.4)',
      borderRadius: 6,
      padding: '10px 12px',
      fontFamily: 'var(--nx-font-mono, monospace)',
      fontSize: 11,
      maxWidth: 480,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {isActive && (
          <motion.span
            animate={{ opacity: [1, 0.2, 1] }}
            transition={{ repeat: Infinity, duration: 1.2 }}
            style={{ width: 6, height: 6, borderRadius: '50%', background: '#20D6C7', display: 'inline-block', flexShrink: 0 }}
          />
        )}
        <span style={{ flex: 1, color: '#E5C76B', fontWeight: 700, letterSpacing: '0.06em' }}>
          {title || `Task ${taskId}`}
        </span>
        <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)' }}>
          {doneCount}/{steps.length} done{errCount > 0 ? ` · ${errCount} err` : ''}
        </span>
      </div>

      {/* Steps */}
      <AnimatePresence initial={false}>
        {steps.map((step, i) => (
          <motion.div
            key={step.id ?? i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '3px 0',
              borderBottom: i < steps.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
            }}
          >
            <span style={{ color: STATUS_COLOR[step.status] ?? STATUS_COLOR.pending, flexShrink: 0 }}>
              {STATUS_ICON[step.status] ?? '○'}
            </span>
            <span style={{
              flex: 1,
              color: step.status === 'done'   ? 'rgba(255,255,255,0.4)' :
                     step.status === 'active' ? '#20D6C7' :
                     step.status === 'error'  ? '#EF4444' : 'rgba(255,255,255,0.25)',
            }}>
              {step.label}
              {step.status === 'active' && (
                <motion.span
                  animate={{ opacity: [1, 0] }}
                  transition={{ repeat: Infinity, duration: 0.6, ease: 'steps(1)' }}
                >▌</motion.span>
              )}
            </span>
            {step.elapsed != null && (
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)' }}>{step.elapsed}ms</span>
            )}
            {step.status !== 'pending' && (
              <span style={{
                fontSize: 8, padding: '1px 5px', borderRadius: 3, flexShrink: 0,
                background: `${STATUS_COLOR[step.status]}18`,
                border: `1px solid ${STATUS_COLOR[step.status]}44`,
                color: STATUS_COLOR[step.status],
                letterSpacing: '0.08em',
              }}>
                {step.status.toUpperCase()}
              </span>
            )}
          </motion.div>
        ))}
      </AnimatePresence>

      <MiniGraph data={graph} />
    </div>
  )
}
