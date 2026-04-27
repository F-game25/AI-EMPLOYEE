import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'

export default function TaskProgressBlock({ taskId, title = 'Task' }) {
  const [task, setTask] = useState(null)
  const [steps, setSteps] = useState([])
  const [loading, setLoading] = useState(true)
  const wsRef = useRef(null)

  useEffect(() => {
    const fetchTask = async () => {
      try {
        const res = await fetch(`/api/tasks/${taskId}`)
        if (!res.ok) {
          setLoading(false)
          return
        }
        const data = await res.json()
        setTask(data.task)
        setSteps(data.steps || [])
      } catch (e) {
        console.error('Failed to fetch task:', e)
      }
      setLoading(false)
    }

    fetchTask()

    // WebSocket subscription
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    wsRef.current = new WebSocket(
      `${protocol}//${window.location.host}/api/tasks/${taskId}/ws`
    )

    wsRef.current.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data)

        if (update.type === 'step_update') {
          setSteps((prev) => {
            const idx = prev.findIndex((s) => s.id === update.step_id)
            if (idx >= 0) {
              const newSteps = [...prev]
              newSteps[idx] = { ...newSteps[idx], ...update.data }
              return newSteps
            }
            return prev
          })
        }

        if (update.type === 'task_update') {
          setTask((prev) => (prev ? { ...prev, ...update.data } : null))
        }
      } catch (e) {
        console.error('WS parse error:', e)
      }
    }

    wsRef.current.onerror = () => {
      console.warn('Task progress WS connection failed')
    }

    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [taskId])

  if (loading) return <div style={{ fontSize: 12, color: '#999' }}>Loading task...</div>
  if (!task) return <div style={{ fontSize: 12, color: '#999' }}>Task not found</div>

  const elapsed = Math.round((Date.now() - new Date(task.started_at).getTime()) / 1000)
  const completedSteps = steps.filter((s) => s.status === 'done').length
  const totalSteps = steps.length
  const progressPercent = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0

  const icons = {
    pending: '○',
    active: '●',
    done: '✓',
    error: '✗',
  }

  const colors = {
    pending: 'rgba(255,255,255,0.3)',
    active: '#20D6C7',
    done: '#22C55E',
    error: '#FF3B3B',
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      style={{
        background: 'rgba(0,0,0,0.3)',
        border: '2px solid rgba(229,199,107,0.3)',
        borderRadius: 6,
        padding: 12,
        marginBottom: 12,
        fontFamily: 'monospace',
        fontSize: 11,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 10,
        }}
      >
        <div style={{ fontSize: 11, fontWeight: 600, color: 'rgba(229,199,107,1)' }}>
          {title || 'Task'}
          {task.status === 'running' && (
            <span
              style={{
                marginLeft: 8,
                display: 'inline-block',
                animation: 'pulse 1.5s infinite',
              }}
            >
              ●
            </span>
          )}
        </div>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>
          {elapsed}s elapsed
        </div>
      </div>

      {/* Progress bar */}
      <div
        style={{
          height: 4,
          background: 'rgba(139,81,32,0.2)',
          borderRadius: 2,
          marginBottom: 10,
          overflow: 'hidden',
        }}
      >
        <motion.div
          style={{
            height: '100%',
            background: 'linear-gradient(90deg, #E5C76B, #FFD97A)',
            width: `${progressPercent}%`,
          }}
          transition={{ duration: 0.4 }}
        />
      </div>

      {/* Steps list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
        {steps.map((step, idx) => (
          <motion.div
            key={step.id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.05 }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 10,
              color: colors[step.status] || colors.pending,
            }}
          >
            <span style={{ minWidth: 12 }}>{icons[step.status] || '?'}</span>
            <span style={{ flex: 1 }}>
              {step.label}
              {step.status === 'active' && (
                <span
                  style={{
                    marginLeft: 4,
                    animation: 'blink 0.7s infinite',
                    display: 'inline-block',
                  }}
                >
                  ▌
                </span>
              )}
            </span>
            {step.elapsed_ms && (
              <span style={{ fontSize: 9, opacity: 0.6 }}>
                {Math.round(step.elapsed_ms / 1000)}s
              </span>
            )}
          </motion.div>
        ))}
      </div>

      {/* Summary */}
      {task.status === 'done' && (
        <div
          style={{
            padding: 8,
            background: 'rgba(34,197,94,0.1)',
            borderRadius: 4,
            fontSize: 9,
            color: '#22C55E',
            borderLeft: '2px solid #22C55E',
          }}
        >
          ✓ Complete: {completedSteps}/{totalSteps} steps • {elapsed}s total
        </div>
      )}

      {task.status === 'failed' && (
        <div
          style={{
            padding: 8,
            background: 'rgba(255,59,59,0.1)',
            borderRadius: 4,
            fontSize: 9,
            color: '#FF3B3B',
            borderLeft: '2px solid #FF3B3B',
          }}
        >
          ✗ Failed at step {steps.findIndex((s) => s.status === 'error') + 1}
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </motion.div>
  )
}
