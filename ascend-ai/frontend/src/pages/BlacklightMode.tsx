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
            🔒 BLACKLIGHT MODE
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>Ultra Safe & Security</p>
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
    </motion.div>
  )
}
