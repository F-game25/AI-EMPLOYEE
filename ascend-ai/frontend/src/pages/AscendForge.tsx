import { motion } from 'framer-motion'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ToggleSwitch } from '../components/ToggleSwitch'
import { ProgressBar } from '../components/ProgressBar'
import { SystemResponseWindow } from '../components/SystemResponseWindow'
import { useStore } from '../store/ascendStore'

const PILLS = [
  'Improve Money Mode automation',
  'Optimize agent routing speed',
  'Add print-on-demand skill',
  'Reduce RAM usage by 20%',
]

const SAFEGUARDS = [
  'Sandbox execution — all tasks run in isolated environment',
  'Risk assessment — automatic threat analysis before execution',
  'Rollback support — one-click revert to previous state',
  'Permission gates — manual approval for HIGH risk tasks',
  'Rate limiting — max 3 concurrent forge tasks',
]

export function AscendForge() {
  const nav = useNavigate()
  const { forgeMode, setForgeMode, forgeLines, addForgeLine } = useStore()
  const [task, setTask] = useState('')
  const [progress, setProgress] = useState(0)
  const [risk, setRisk] = useState(1)

  const execute = async () => {
    if (!task.trim()) return
    addForgeLine(`[${new Date().toLocaleTimeString()}] Initializing: ${task}`)
    setProgress(10)
    try {
      await fetch('/api/forge/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, mode: forgeMode }),
      })
      addForgeLine(`[${new Date().toLocaleTimeString()}] Task queued — mode: ${forgeMode}`)
      setProgress(50)
    } catch {
      addForgeLine('ERROR: Backend connection failed')
      setProgress(0)
    }
  }

  const askPermission = () => {
    addForgeLine(`[${new Date().toLocaleTimeString()}] ⚠ Requesting manual approval for task...`)
    addForgeLine(`[${new Date().toLocaleTimeString()}] Awaiting operator confirmation...`)
  }

  const rollback = async () => {
    addForgeLine(`[${new Date().toLocaleTimeString()}] 🔄 Rolling back to previous state...`)
    try {
      await fetch('/api/forge/rollback', { method: 'POST' })
      addForgeLine(`[${new Date().toLocaleTimeString()}] Rollback complete.`)
      setProgress(0)
    } catch {
      addForgeLine('ERROR: Rollback failed')
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
            ⚗ ASCEND FORGE — Self-Improvement System
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>Sandbox execution • Risk-based behavior • Auto-optimization</p>
        </div>
      </div>

      <div className="panel" style={{ padding: 20, marginBottom: 20 }}>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={3}
          placeholder="Describe what to improve..."
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
                background: 'rgba(205,127,50,0.1)',
                border: '1px solid rgba(205,127,50,0.3)',
                borderRadius: 20,
                color: 'var(--bronze)',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                cursor: 'pointer',
              }}
            >
              {p}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <ToggleSwitch value={forgeMode} onChange={setForgeMode} />
          <motion.button
            onClick={execute}
            whileHover={{ scale: 1.02, boxShadow: 'var(--glow-gold)' }}
            whileTap={{ scale: 0.97 }}
            className="btn-gold"
          >
            ⚡ EXECUTE IMPROVEMENT
          </motion.button>
          <motion.button
            onClick={askPermission}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            className="btn-outline"
          >
            🛡 ASK PERMISSION
          </motion.button>
          <motion.button
            onClick={rollback}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            className="btn-outline"
            style={{ color: 'var(--warning)', borderColor: 'rgba(245,158,11,0.3)' }}
          >
            🔄 ROLLBACK
          </motion.button>
        </div>
      </div>

      <SystemResponseWindow title="FORGE RESPONSE" lines={forgeLines} active={forgeMode === 'on'} accentColor="bronze" />

      <div className="panel" style={{ padding: 20, marginTop: 20 }}>
        <ProgressBar value={progress} label="TASK PROGRESS" variant="gold" />
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          {[1, 2, 3].map((r) => (
            <span
              key={r}
              onClick={() => setRisk(r)}
              style={{
                padding: '4px 12px',
                borderRadius: 4,
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                fontWeight: 700,
                background: risk === r ? (r === 1 ? 'var(--online)' : r === 2 ? 'var(--bronze)' : 'var(--offline)') : 'transparent',
                border: 'var(--border-gold)',
                color: risk === r ? '#0A0A0A' : 'var(--text-dim)',
                cursor: 'pointer',
              }}
            >
              RISK {r} {r === 1 ? 'LOW' : r === 2 ? 'MED' : 'HIGH'}
            </span>
          ))}
        </div>
      </div>

      {/* Safeguards */}
      <div className="panel" style={{ padding: 20, marginTop: 20 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 12 }}>
          SAFEGUARDS
        </div>
        {SAFEGUARDS.map((s, i) => (
          <div key={i} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 0',
            borderBottom: i < SAFEGUARDS.length - 1 ? 'var(--border-subtle)' : 'none',
            fontFamily: 'var(--font-body)',
            fontSize: 12,
            color: 'var(--text-secondary)',
          }}>
            <span style={{ color: 'var(--online)', fontSize: 10 }}>✓</span>
            {s}
          </div>
        ))}
      </div>
    </motion.div>
  )
}
