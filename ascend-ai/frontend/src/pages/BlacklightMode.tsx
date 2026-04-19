import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ToggleSwitch } from '../components/ToggleSwitch'
import { SystemResponseWindow } from '../components/SystemResponseWindow'
import { useStore } from '../store/ascendStore'

interface Connection {
  name: string
  status: string
  latency: number
}

export function BlacklightMode() {
  const nav = useNavigate()
  const { blacklightActive, setBlacklightActive, blacklightLines, addBlacklightLine } = useStore()
  const [mode, setMode] = useState('off')
  const [connections, setConnections] = useState<Connection[]>([])
  const [breachAlerts] = useState<{ id: number; message: string; severity: string; ts: string }[]>([
    { id: 1, message: 'Unusual API access pattern detected', severity: 'low', ts: new Date().toISOString() },
    { id: 2, message: 'Rate limit threshold approaching for external endpoints', severity: 'medium', ts: new Date().toISOString() },
  ])

  useEffect(() => {
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
  }, [setBlacklightActive])

  const toggleMode = (v: string) => {
    setMode(v)
    const active = v === 'on'
    setBlacklightActive(active)
    fetch('/api/blacklight/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: v }),
    }).catch(() => {})
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
    } catch {
      addBlacklightLine('ERROR: Scan failed — backend unreachable')
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
            🔒 BLACKLIGHT MODE — Ultra Safe &amp; Security
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>API monitoring • Encryption state • Connection stability</p>
        </div>
      </div>

      <div className="panel" style={{ padding: 20, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 16 }}>
        <ToggleSwitch value={mode} onChange={toggleMode} />
        <motion.button
          onClick={runScan}
          whileHover={{ scale: 1.02, boxShadow: 'var(--glow-gold)' }}
          whileTap={{ scale: 0.97 }}
          className="btn-gold"
        >
          🔍 RUN FULL SCAN
        </motion.button>
      </div>

      <SystemResponseWindow title="SECURITY STATUS" lines={blacklightLines} active={blacklightActive} accentColor="bronze" />

      {/* Connection grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 20 }}>
        {connections.map((c) => (
          <div key={c.name} className="panel" style={{ padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className={`dot ${c.status === 'online' ? 'online' : 'offline'}`} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>
                {c.name}
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
              Latency: {c.latency}ms
            </div>
          </div>
        ))}
      </div>

      {/* Breach alerts */}
      <div className="panel" style={{ padding: 20, marginTop: 20 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', letterSpacing: 2, marginBottom: 12 }}>
          BREACH ALERTS
        </div>
        {breachAlerts.length === 0 && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>No breach alerts</div>
        )}
        {breachAlerts.map((alert) => (
          <div key={alert.id} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '8px 12px',
            marginBottom: 8,
            background: 'rgba(205,127,50,0.06)',
            border: '1px solid rgba(205,127,50,0.15)',
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
                {new Date(alert.ts).toLocaleTimeString()} • {alert.severity.toUpperCase()}
              </div>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  )
}
