import { motion } from 'framer-motion'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ToggleSwitch } from '../components/ToggleSwitch'
import { ProgressBar } from '../components/ProgressBar'
import { SystemResponseWindow } from '../components/SystemResponseWindow'
import { useStore } from '../store/ascendStore'

const PILLS = [
  'Launch POD store automation',
  'Generate 10 leads today',
  'Write cold email campaign',
  'Optimize pricing strategy',
]

export function MoneyMode() {
  const nav = useNavigate()
  const { moneyMode, setMoneyMode, moneyLines, addMoneyLine, moneyRevenue } = useStore()
  const [task, setTask] = useState('')
  const [progress, setProgress] = useState(0)

  const execute = async () => {
    if (!task.trim()) return
    addMoneyLine(`[${new Date().toLocaleTimeString()}] Initializing: ${task}`)
    setProgress(10)
    try {
      await fetch('/api/money/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, mode: moneyMode }),
      })
      addMoneyLine(`[${new Date().toLocaleTimeString()}] Task queued — mode: ${moneyMode}`)
      setProgress(50)
    } catch {
      addMoneyLine('ERROR: Backend connection failed')
      setProgress(0)
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <motion.button onClick={() => nav('/')} whileHover={{ scale: 1.05 }} className="btn-outline">
          ← BACK
        </motion.button>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700 }} className="metallic-text">
            💰 MONEY MODE
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>Optimization & Revenue Generation</p>
        </div>
      </div>

      <div className="panel" style={{ padding: 20, marginBottom: 20 }}>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={3}
          placeholder="Describe revenue task..."
          className="input-dark"
          style={{ resize: 'vertical', marginBottom: 12 }}
        />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
          {PILLS.map((p) => (
            <button
              key={p}
              onClick={() => setTask(p)}
              style={{
                padding: '4px 12px',
                background: 'rgba(212,175,55,0.1)',
                border: '1px solid rgba(212,175,55,0.3)',
                borderRadius: 20,
                color: 'var(--gold)',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                cursor: 'pointer',
              }}
            >
              {p}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <ToggleSwitch value={moneyMode} onChange={setMoneyMode} />
          <motion.button
            onClick={execute}
            whileHover={{ scale: 1.02, boxShadow: 'var(--glow-gold)' }}
            whileTap={{ scale: 0.97 }}
            className="btn-gold"
          >
            💰 EXECUTE TASK
          </motion.button>
        </div>
      </div>

      <SystemResponseWindow title="MONEY MODE RESPONSE" lines={moneyLines} active={moneyMode === 'on'} accentColor="gold" />

      <div className="panel" style={{ padding: 20, marginTop: 20 }}>
        <ProgressBar value={progress} label="TASK PROGRESS" variant="gold" />
        <div style={{
          marginTop: 16,
          padding: '12px 16px',
          background: 'rgba(212,175,55,0.06)',
          borderRadius: 8,
          border: 'var(--border-gold)',
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
          color: 'var(--gold)',
        }}>
          💶 Estimated revenue: +€{moneyRevenue} this week
        </div>
      </div>
    </motion.div>
  )
}
