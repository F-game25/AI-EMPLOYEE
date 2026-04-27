import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export default function HistoryPanel() {
  const [tasks, setTasks] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedTask, setSelectedTask] = useState(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    fetchHistory()
    fetchStats()
    // Refresh every 30 seconds
    const interval = setInterval(() => {
      fetchHistory()
      fetchStats()
    }, 30000)
    return () => clearInterval(interval)
  }, [filter])

  const fetchHistory = async () => {
    try {
      const params = filter !== 'all' ? `?status=${filter}` : ''
      const res = await fetch(`/api/history${params}`)
      if (res.ok) {
        const data = await res.json()
        setTasks(data.tasks || [])
      }
    } catch (e) {
      console.error('Failed to fetch history:', e)
    }
    setLoading(false)
  }

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/history/stats')
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch (e) {
      console.error('Failed to fetch stats:', e)
    }
  }

  const formatTime = (ms) => {
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  const formatDate = (iso) => {
    const date = new Date(iso)
    const today = new Date()
    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'done':
        return '#22C55E'
      case 'failed':
        return '#FF3B3B'
      case 'partial':
        return '#FBBF24'
      default:
        return 'rgba(255,255,255,0.5)'
    }
  }

  return (
    <div
      className="flex flex-col h-full"
      style={{
        background: 'rgba(0,0,0,0.2)',
        borderLeft: '1px solid var(--border-subtle)',
      }}
    >
      {/* Header */}
      <div
        className="p-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="font-mono text-xs tracking-widest mb-2" style={{ color: 'var(--gold)' }}>
          HISTORY
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div style={{ background: 'rgba(255,255,255,0.04)', padding: '6px 8px', borderRadius: '4px' }}>
              <div className="text-8px" style={{ color: 'rgba(255,255,255,0.5)' }}>
                Tasks
              </div>
              <div className="font-mono text-xs font-semibold">{stats.total_tasks}</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.04)', padding: '6px 8px', borderRadius: '4px' }}>
              <div className="text-8px" style={{ color: 'rgba(255,255,255,0.5)' }}>
                Success
              </div>
              <div className="font-mono text-xs font-semibold">
                {Math.round(stats.success_rate)}%
              </div>
            </div>
          </div>
        )}

        {/* Filter */}
        <div className="flex gap-1">
          {['all', 'done', 'failed'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="font-mono text-8px px-2 py-1 flex-1"
              style={{
                background: filter === f ? 'rgba(212,175,55,0.2)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${filter === f ? 'rgba(212,175,55,0.4)' : 'rgba(255,255,255,0.1)'}`,
                color: filter === f ? 'var(--gold)' : 'rgba(255,255,255,0.5)',
                borderRadius: '3px',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {f.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Task List */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {loading ? (
          <div className="text-8px text-center py-4" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Loading history...
          </div>
        ) : tasks.length === 0 ? (
          <div className="text-8px text-center py-4" style={{ color: 'rgba(255,255,255,0.3)' }}>
            No tasks yet
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {tasks.map((task, idx) => (
              <motion.div
                key={task.task_id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ delay: idx * 0.02 }}
                onClick={() => setSelectedTask(task)}
                style={{
                  background: selectedTask?.task_id === task.task_id ? 'rgba(212,175,55,0.1)' : 'transparent',
                  border: `1px solid ${selectedTask?.task_id === task.task_id ? 'rgba(212,175,55,0.3)' : 'transparent'}`,
                  padding: '8px',
                  marginBottom: '4px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                  <span
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: getStatusColor(task.status),
                      flexShrink: 0,
                    }}
                  />
                  <span className="font-mono text-8px flex-1 truncate" style={{ color: 'rgba(255,255,255,0.8)' }}>
                    {task.input.substring(0, 30)}...
                  </span>
                  <span className="text-8px" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    {formatDate(task.timestamp)}
                  </span>
                </div>
                <div className="flex gap-2 items-center text-8px">
                  <span style={{ color: 'rgba(255,255,255,0.4)' }}>
                    {formatTime(task.duration_ms)}
                  </span>
                  {task.confidence > 0 && (
                    <span style={{ color: 'rgba(255,255,255,0.4)' }}>
                      ${task.cost_estimate_usd.toFixed(2)}
                    </span>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>

      {/* Detail View */}
      {selectedTask && (
        <div
          className="p-3 flex-shrink-0"
          style={{
            background: 'rgba(0,0,0,0.4)',
            borderTop: '1px solid var(--border-subtle)',
            maxHeight: '200px',
            overflow: 'y-auto',
          }}
        >
          <div className="font-mono text-8px mb-2" style={{ color: 'var(--gold)' }}>
            DETAILS
          </div>
          <div className="space-y-1 text-8px">
            <div>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>ID: </span>
              <span style={{ fontFamily: 'monospace', fontSize: '7px' }}>
                {selectedTask.task_id}
              </span>
            </div>
            <div>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>Agents: </span>
              <span>{selectedTask.agent_sequence.join(', ')}</span>
            </div>
            <div>
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>Confidence: </span>
              <span>{Math.round(selectedTask.confidence * 100)}%</span>
            </div>
            {selectedTask.error && (
              <div>
                <span style={{ color: 'rgba(255,255,255,0.5)' }}>Error: </span>
                <span style={{ color: '#FF3B3B' }}>{selectedTask.error}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
