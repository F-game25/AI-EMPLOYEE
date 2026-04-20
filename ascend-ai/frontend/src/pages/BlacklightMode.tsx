import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SystemResponseWindow } from '../components/SystemResponseWindow'
import { ChatWindow } from '../components/ChatWindow'
import { useStore } from '../store/ascendStore'

interface Connection {
  name: string
  status: string
  latency: number
}

interface BreachAlert {
  id: number
  message: string
  severity: string
  ts: number
}

type ModeBtn = 'start' | 'stop' | 'auto'

export function BlacklightMode() {
  const nav = useNavigate()
  const { blacklightActive, setBlacklightActive, blacklightLines, addBlacklightLine, blacklightChat, addBlacklightChat } = useStore()
  const [mode, setMode] = useState('off')
  const [connections, setConnections] = useState<Connection[]>([])
  const [breachAlerts, setBreachAlerts] = useState<BreachAlert[]>([])
  const [activeBtn, setActiveBtn] = useState<ModeBtn | null>(null)
  const [loadingBtn, setLoadingBtn] = useState<ModeBtn | null>(null)
  const [toast, setToast] = useState('')

  const loadStatus = () =>
    fetch('/api/blacklight/status')
      .then((r) => r.json())
      .then((d) => {
        if (d.connections) setConnections(d.connections)
        if (d.status) {
          setMode(d.status.mode || 'off')
          setBlacklightActive(d.status.active || false)
        }
      })
      .catch(() => {})

  const loadAlerts = () =>
    fetch('/api/blacklight/alerts')
      .then((r) => r.json())
      .then((d) => setBreachAlerts(Array.isArray(d) ? d : []))
      .catch(() => {})

  useEffect(() => {
    loadStatus()
    loadAlerts()
    const t = setInterval(() => { loadStatus(); loadAlerts() }, 15000)
    return () => clearInterval(t)
  }, [setBlacklightActive])

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const callMode = async (btn: ModeBtn) => {
    setLoadingBtn(btn)
    const newMode = btn === 'stop' ? 'off' : 'on'
    const active = newMode === 'on'
    try {
      const r = await fetch('/api/blacklight/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode }),
      })
      const d = await r.json()
      if (d.success) {
        setMode(newMode)
        setBlacklightActive(active)
        setActiveBtn(btn === 'stop' ? null : btn)
        addBlacklightLine(`[${new Date().toLocaleTimeString()}] ${btn.toUpperCase()} — Blacklight mode: ${newMode}`)
        showToast(`✓ Blacklight ${btn.toUpperCase()} activated`)
      }
    } catch {
      addBlacklightLine('ERROR: Backend connection failed')
      showToast('✗ Connection error')
    } finally {
      setLoadingBtn(null)
    }
  }

  const runScan = async () => {
    addBlacklightLine(`[${new Date().toLocaleTimeString()}] Running full security scan...`)
    try {
      const r = await fetch('/api/blacklight/scan', { method: 'POST' })
      const d = await r.json()
      if (d.results) {
        d.results.forEach((res: { target: string; status: string; issues: number }) => {
          addBlacklightLine(`  ${res.status === 'secure' ? '✅' : '⚠️'} ${res.target}: ${res.status} (${res.issues} issues)`)
        })
      }
      addBlacklightLine(`[${new Date().toLocaleTimeString()}] Scan complete.`)
      loadAlerts()
    } catch {
      addBlacklightLine('ERROR: Scan failed — backend unreachable')
    }
  }

  const modeActive = mode === 'on' || blacklightActive

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      style={modeActive ? { boxShadow: '0 0 0 2px rgba(239,68,68,0.25) inset', borderRadius: 12 } : undefined}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <motion.button onClick={() => nav('/')} whileHover={{ scale: 1.05 }} className="btn-outline">
          ← BACK
        </motion.button>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700 }} className="metallic-text">
            🔒 BLACKLIGHT MODE — Ultra Safe &amp; Security
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>API monitoring • Encryption state • Connection stability</p>
        </div>
        {modeActive && (
          <span style={{
            marginLeft: 'auto',
            padding: '4px 12px',
            background: 'rgba(239,68,68,0.15)',
            border: '1px solid rgba(239,68,68,0.4)',
            borderRadius: 6,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: '#EF4444',
            fontWeight: 700,
            letterSpacing: 1,
          }}>
            ● ACTIVE
          </span>
        )}
      </div>

      {/* START / STOP / AUTO + FULL SCAN */}
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
        <motion.button
          onClick={runScan}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          className="btn-gold"
          style={{ marginLeft: 'auto' }}
        >
          🔍 FULL SCAN
        </motion.button>
        {toast && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: toast.startsWith('✓') ? 'var(--online)' : 'var(--offline)' }}>
            {toast}
          </span>
        )}
      </div>

      {/* Chat + Log */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', letterSpacing: 2, marginBottom: 8 }}>
            SECURITY AI CHAT
          </div>
          <ChatWindow
            messages={blacklightChat}
            context="blacklight"
            placeholder="Ask about security status..."
            height={300}
            onNewMessage={addBlacklightChat}
          />
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', letterSpacing: 2, marginBottom: 8 }}>
            SECURITY LOG
          </div>
          <SystemResponseWindow title="SECURITY STATUS" lines={blacklightLines} active={modeActive} accentColor="bronze" />
        </div>
      </div>

      {/* Connection grid */}
      {connections.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
          {connections.map((c) => (
            <div key={c.name} className="panel" style={{ padding: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span className={`dot ${c.status === 'online' ? 'online' : c.status === 'standby' ? 'starting' : 'offline'}`} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>
                  {c.name}
                </span>
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
                {c.latency > 0 ? `${c.latency}ms` : c.status.toUpperCase()}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Breach alerts */}
      <div className="panel" style={{ padding: 20 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', letterSpacing: 2, marginBottom: 12 }}>
          BREACH ALERTS
        </div>
        {breachAlerts.length === 0 && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>No breach alerts — system secure</div>
        )}
        {breachAlerts.map((alert) => (
          <div key={alert.id} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '8px 12px',
            marginBottom: 8,
            background: 'rgba(239,68,68,0.06)',
            border: '1px solid rgba(239,68,68,0.2)',
            borderRadius: 8,
          }}>
            <span style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: alert.severity === 'high' ? 'var(--offline)' : 'var(--bronze)',
              boxShadow: `0 0 6px ${alert.severity === 'high' ? 'var(--offline)' : 'var(--bronze)'}`,
              flexShrink: 0,
            }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-primary)' }}>
                {alert.message}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', marginTop: 2 }}>
                {new Date(alert.ts * 1000).toLocaleTimeString()} • {alert.severity.toUpperCase()}
              </div>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  )
}
