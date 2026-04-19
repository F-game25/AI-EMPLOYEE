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

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <motion.button onClick={() => nav('/')} whileHover={{ scale: 1.05 }} className="btn-outline">
          ← BACK
        </motion.button>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700 }} className="metallic-text">
            ⚗ ASCEND FORGE
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>Self-Improvement System</p>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <ToggleSwitch value={forgeMode} onChange={setForgeMode} />
          <motion.button
            onClick={execute}
            whileHover={{ scale: 1.02, boxShadow: 'var(--glow-gold)' }}
            whileTap={{ scale: 0.97 }}
            className="btn-gold"
          >
            ⚡ EXECUTE IMPROVEMENT
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
    </motion.div>
  )
}
