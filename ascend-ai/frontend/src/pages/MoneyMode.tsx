import { motion } from 'framer-motion'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ProgressBar } from '../components/ProgressBar'
import { SystemResponseWindow } from '../components/SystemResponseWindow'
import { ChatWindow } from '../components/ChatWindow'
import { useStore } from '../store/ascendStore'

const QUICK_ACTIONS = [
  { label: 'Find 10 Leads', task: 'Find 10 qualified leads for my business today' },
  { label: 'Write Sales Email', task: 'Write a high-converting cold sales email campaign' },
  { label: 'Analyse Competitor', task: 'Analyse my top competitor and find opportunities' },
  { label: 'Create Content Plan', task: 'Create a 30-day content plan to drive revenue' },
]

type ModeBtn = 'start' | 'stop' | 'auto'

interface AutomationFlow {
  name: string
  status: 'active' | 'idle' | 'paused'
  description: string
}

const DEMO_FLOWS: AutomationFlow[] = [
  { name: 'Lead Hunter', status: 'idle', description: 'Scrapes and qualifies prospects' },
  { name: 'Email Ninja', status: 'idle', description: 'Cold outreach campaigns' },
  { name: 'POD Automation', status: 'idle', description: 'Print-on-demand product creation' },
  { name: 'Content Master', status: 'idle', description: 'Social content generation' },
]

export function MoneyMode() {
  const nav = useNavigate()
  const { moneyMode, setMoneyMode, moneyLines, addMoneyLine, moneyRevenue, moneyChat, addMoneyChat } = useStore()
  const [progress, setProgress] = useState(0)
  const [activeBtn, setActiveBtn] = useState<ModeBtn | null>(null)
  const [loadingBtn, setLoadingBtn] = useState<ModeBtn | null>(null)
  const [toast, setToast] = useState('')
  const [flows, setFlows] = useState<AutomationFlow[]>(DEMO_FLOWS)

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const callMode = async (btn: ModeBtn) => {
    setLoadingBtn(btn)
    const mode = btn === 'stop' ? 'off' : 'on'
    try {
      const r = await fetch('/api/money/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: '', mode }),
      })
      const d = await r.json()
      if (d.success) {
        setMoneyMode(mode)
        setActiveBtn(btn === 'stop' ? null : btn)
        addMoneyLine(`[${new Date().toLocaleTimeString()}] ${btn.toUpperCase()} — Money Mode: ${mode}`)
        showToast(`✓ Money Mode ${btn.toUpperCase()} activated`)
        if (btn !== 'stop') {
          setProgress(15)
          setFlows((prev) => prev.map((f) => ({ ...f, status: 'active' as const })))
        } else {
          setProgress(0)
          setFlows((prev) => prev.map((f) => ({ ...f, status: 'idle' as const })))
        }
      }
    } catch {
      addMoneyLine('ERROR: Backend connection failed')
      showToast('✗ Connection error')
    } finally {
      setLoadingBtn(null)
    }
  }

  const modeActive = moneyMode === 'on'

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <motion.button onClick={() => nav('/')} whileHover={{ scale: 1.05 }} className="btn-outline">
          ← BACK
        </motion.button>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700 }} className="metallic-text">
            💰 MONEY MODE — Optimalisatie &amp; Geld Verdienen
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>Revenue generation • Lead automation • Business optimisation</p>
        </div>
      </div>

      {/* START / STOP / AUTO */}
      <div className="panel" style={{ padding: 16, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        {(['start', 'stop', 'auto'] as ModeBtn[]).map((btn) => (
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
        {toast && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: toast.startsWith('✓') ? 'var(--online)' : 'var(--offline)' }}>
            {toast}
          </span>
        )}
      </div>

      {/* Chat + Log */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--gold)', letterSpacing: 2, marginBottom: 8 }}>
            MONEY MODE AI CHAT
          </div>
          <ChatWindow
            messages={moneyChat}
            context="money"
            placeholder="Assign a revenue task..."
            height={320}
            onNewMessage={addMoneyChat}
          />
          {/* Quick action pills */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            {QUICK_ACTIONS.map(({ label, task }) => (
              <button
                key={label}
                onClick={() => addMoneyChat({ role: 'user', content: task })}
                style={{
                  padding: '4px 10px',
                  background: 'rgba(212,175,55,0.1)',
                  border: '1px solid rgba(212,175,55,0.3)',
                  borderRadius: 20,
                  color: 'var(--gold)',
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--gold)', letterSpacing: 2, marginBottom: 8 }}>
            ACTIVITY LOG
          </div>
          <SystemResponseWindow title="MONEY LOG" lines={moneyLines} active={modeActive} accentColor="gold" />
        </div>
      </div>

      {/* Revenue Dashboard */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Metrics row */}
        <div className="panel" style={{ padding: 20 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 16 }}>
            REVENUE METRICS
          </div>
          <ProgressBar value={progress} label="ACTIVE TASK PROGRESS" variant="gold" />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 16 }}>
            {[
              { label: 'Leads Generated', value: modeActive ? '12' : '0' },
              { label: 'Emails Sent', value: modeActive ? '48' : '0' },
              { label: 'Est. Revenue/week', value: `€${moneyRevenue || (modeActive ? 240 : 0)}` },
            ].map(({ label, value }) => (
              <div key={label} style={{
                padding: '10px 12px',
                background: 'rgba(212,175,55,0.05)',
                border: 'var(--border-gold)',
                borderRadius: 8,
                textAlign: 'center',
              }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--gold)' }}>{value}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Active flows */}
        <div className="panel" style={{ padding: 20 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 12 }}>
            AUTOMATION FLOWS
          </div>
          {flows.map((flow) => (
            <div key={flow.name} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 0',
              borderBottom: 'var(--border-subtle)',
            }}>
              <span className={`dot ${flow.status === 'active' ? 'online' : 'offline'}`} />
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>{flow.name}</div>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-dim)' }}>{flow.description}</div>
              </div>
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                color: flow.status === 'active' ? 'var(--online)' : 'var(--text-dim)',
                textTransform: 'uppercase',
              }}>
                {flow.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
