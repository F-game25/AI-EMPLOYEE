import { motion } from 'framer-motion'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ProgressBar } from '../components/ProgressBar'
import { SystemResponseWindow } from '../components/SystemResponseWindow'
import { ChatWindow } from '../components/ChatWindow'
import { useStore } from '../store/ascendStore'

const QUICK_TASKS = [
  'Improve Money Mode automation',
  'Optimize agent routing speed',
  'Add print-on-demand skill',
  'Reduce RAM usage by 20%',
]

const SAFEGUARDS = [
  'Sandbox isolation — all tasks run in isolated environment',
  'Auto-rollback — automatic revert on failure',
  'Human approval required for HIGH risk tasks',
  'Rate limiting — max 3 concurrent forge tasks',
]

type ForgeButtonMode = 'start' | 'stop' | 'auto'

export function AscendForge() {
  const nav = useNavigate()
  const { forgeMode, setForgeMode, forgeLines, addForgeLine, forgeChat, addForgeChat } = useStore()
  const [progress, setProgress] = useState(0)
  const [risk, setRisk] = useState(1)
  const [activeBtn, setActiveBtn] = useState<ForgeButtonMode | null>(null)
  const [loadingBtn, setLoadingBtn] = useState<ForgeButtonMode | null>(null)
  const [toast, setToast] = useState('')

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const callMode = async (btn: ForgeButtonMode) => {
    setLoadingBtn(btn)
    const mode = btn === 'stop' ? 'off' : 'on'
    try {
      const r = await fetch('/api/forge/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: '', mode }),
      })
      const d = await r.json()
      if (d.success) {
        setForgeMode(mode)
        setActiveBtn(btn === 'stop' ? null : btn)
        addForgeLine(`[${new Date().toLocaleTimeString()}] ${btn.toUpperCase()} — Forge mode: ${mode}`)
        showToast(`✓ Forge ${btn.toUpperCase()} activated`)
        if (btn !== 'stop') setProgress(10)
        else setProgress(0)
      }
    } catch {
      addForgeLine('ERROR: Backend connection failed')
      showToast('✗ Connection error')
    } finally {
      setLoadingBtn(null)
    }
  }

  const rollback = async () => {
    addForgeLine(`[${new Date().toLocaleTimeString()}] 🔄 Rolling back to previous state...`)
    try {
      await fetch('/api/forge/rollback', { method: 'POST' })
      addForgeLine(`[${new Date().toLocaleTimeString()}] Rollback complete.`)
      setProgress(0)
      setActiveBtn(null)
      setForgeMode('off')
      showToast('✓ Rolled back')
    } catch {
      addForgeLine('ERROR: Rollback failed')
      showToast('✗ Rollback failed')
    }
  }

  const modeActive = forgeMode === 'on'

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      {/* Header */}
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

      {/* START / STOP / AUTO + ROLLBACK */}
      <div className="panel" style={{ padding: 16, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        {(['start', 'stop', 'auto'] as ForgeButtonMode[]).map((btn) => (
          <motion.button
            key={btn}
            onClick={() => callMode(btn)}
            disabled={loadingBtn !== null}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            style={{
              padding: '8px 20px',
              background: activeBtn === btn ? 'var(--gold)' : 'transparent',
              border: activeBtn === btn ? '1px solid var(--gold)' : 'var(--border-gold)',
              borderRadius: 8,
              color: activeBtn === btn ? '#0A0A0A' : 'var(--gold)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 700,
              cursor: loadingBtn !== null ? 'not-allowed' : 'pointer',
              boxShadow: activeBtn === btn ? '0 0 12px rgba(212,175,55,0.4)' : undefined,
              opacity: loadingBtn !== null ? 0.7 : 1,
              letterSpacing: 1,
            }}
          >
            {loadingBtn === btn ? '...' : btn.toUpperCase()}
          </motion.button>
        ))}
        <motion.button
          onClick={rollback}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          className="btn-outline"
          style={{ color: 'var(--warning)', borderColor: 'rgba(245,158,11,0.3)', marginLeft: 'auto' }}
        >
          🔄 ROLLBACK
        </motion.button>
        {toast && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: toast.startsWith('✓') ? 'var(--online)' : 'var(--offline)' }}>
            {toast}
          </span>
        )}
      </div>

      {/* Two-column layout: chat + log */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Chat window */}
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', letterSpacing: 2, marginBottom: 8 }}>
            FORGE AI CHAT
          </div>
          <ChatWindow
            messages={forgeChat}
            context="forge"
            placeholder="Describe what to improve..."
            height={340}
            onNewMessage={addForgeChat}
          />
          {/* Quick task pills */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            {QUICK_TASKS.map((p) => (
              <button
                key={p}
                onClick={() => addForgeChat({ role: 'user', content: p })}
                style={{
                  padding: '4px 10px',
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
        </div>

        {/* Activity log */}
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', letterSpacing: 2, marginBottom: 8 }}>
            LIVE ACTIVITY LOG
          </div>
          <SystemResponseWindow title="FORGE LOG" lines={forgeLines} active={modeActive} accentColor="bronze" />
        </div>
      </div>

      {/* Progress + Risk */}
      <div className="panel" style={{ padding: 20, marginBottom: 20 }}>
        <ProgressBar value={progress} label="TASK PROGRESS" variant="gold" />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1 }}>RISK LEVEL:</span>
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
              {r === 1 ? 'LOW' : r === 2 ? 'MEDIUM' : 'HIGH'}
            </span>
          ))}
        </div>
      </div>

      {/* Safeguards */}
      <div className="panel" style={{ padding: 20 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 12 }}>
          SAFEGUARDS STATUS
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
