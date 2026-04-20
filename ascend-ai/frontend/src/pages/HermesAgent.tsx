import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChatWindow } from '../components/ChatWindow'
import { useStore } from '../store/ascendStore'

type ModeBtn = 'start' | 'stop' | 'auto'

interface RoutedTask {
  id: number
  task: string
  agent: string
  status: string
  result: string
  ts: number
}

interface NotifSettings {
  whatsapp: boolean
  telegram: boolean
  triggers: {
    task_complete: boolean
    lead_generated: boolean
    error_occurred: boolean
  }
}

export function HermesAgent() {
  const nav = useNavigate()
  const { hermesChat, addHermesChat } = useStore()
  const [activeBtn, setActiveBtn] = useState<ModeBtn | null>(null)
  const [loadingBtn, setLoadingBtn] = useState<ModeBtn | null>(null)
  const [toast, setToast] = useState('')
  const [routedTasks, setRoutedTasks] = useState<RoutedTask[]>([])
  const [notifs, setNotifs] = useState<NotifSettings>({
    whatsapp: false,
    telegram: false,
    triggers: { task_complete: true, lead_generated: true, error_occurred: true },
  })
  const [broadcastMsg, setBroadcastMsg] = useState('')
  const [broadcasting, setBroadcasting] = useState(false)

  const loadStatus = () =>
    fetch('/api/hermes/status')
      .then((r) => r.json())
      .then((d) => {
        if (d.routed_tasks) setRoutedTasks(d.routed_tasks)
      })
      .catch(() => {})

  const loadNotifs = () =>
    fetch('/api/hermes/notifications')
      .then((r) => r.json())
      .then((d) => setNotifs(d))
      .catch(() => {})

  useEffect(() => {
    loadStatus()
    loadNotifs()
    const t = setInterval(loadStatus, 10000)
    return () => clearInterval(t)
  }, [])

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const callMode = async (btn: ModeBtn) => {
    setLoadingBtn(btn)
    const mode = btn === 'stop' ? 'off' : 'on'
    try {
      const r = await fetch('/api/hermes/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: '', mode }),
      })
      const d = await r.json()
      if (d.success) {
        setActiveBtn(btn === 'stop' ? null : btn)
        showToast(`✓ Hermes ${btn.toUpperCase()} activated`)
      }
    } catch {
      showToast('✗ Connection error')
    } finally {
      setLoadingBtn(null)
    }
  }

  const broadcast = async () => {
    if (!broadcastMsg.trim()) return
    setBroadcasting(true)
    try {
      const r = await fetch('/api/hermes/broadcast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: broadcastMsg }),
      })
      const d = await r.json()
      showToast(`✓ Broadcast sent to ${d.broadcast_to?.join(', ')}`)
      setBroadcastMsg('')
      loadStatus()
    } catch {
      showToast('✗ Broadcast failed')
    } finally {
      setBroadcasting(false)
    }
  }

  const toggleNotif = async (key: 'whatsapp' | 'telegram') => {
    const updated = { ...notifs, [key]: !notifs[key] }
    setNotifs(updated)
    try {
      await fetch('/api/hermes/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: updated[key] }),
      })
    } catch { /* ignore */ }
  }

  const toggleTrigger = async (key: keyof NotifSettings['triggers']) => {
    const updated = {
      ...notifs,
      triggers: { ...notifs.triggers, [key]: !notifs.triggers[key] },
    }
    setNotifs(updated)
    try {
      await fetch('/api/hermes/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ triggers: { [key]: updated.triggers[key] } }),
      })
    } catch { /* ignore */ }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <motion.button onClick={() => nav('/')} whileHover={{ scale: 1.05 }} className="btn-outline">
          ← BACK
        </motion.button>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700 }} className="metallic-text">
            ⚡ HERMES — Coordination &amp; Communication Agent
          </h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>Task routing • Agent coordination • Notification hub</p>
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

      {/* Chat + Routing panel */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Chat */}
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--gold)', letterSpacing: 2, marginBottom: 8 }}>
            HERMES AI CHAT
          </div>
          <ChatWindow
            messages={hermesChat}
            context="hermes"
            placeholder="Route a task or ask Hermes..."
            height={360}
            onNewMessage={addHermesChat}
          />
        </div>

        {/* Routing panel */}
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--gold)', letterSpacing: 2, marginBottom: 8 }}>
            RECENT ROUTING
          </div>
          <div className="panel" style={{ height: 360, overflowY: 'auto', padding: 12 }}>
            {routedTasks.length === 0 && (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)', padding: 8 }}>
                No tasks routed yet
              </div>
            )}
            {routedTasks.map((task) => (
              <div key={task.id} style={{
                padding: '10px 12px',
                marginBottom: 8,
                background: 'rgba(212,175,55,0.04)',
                border: 'var(--border-subtle)',
                borderRadius: 8,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{
                    padding: '2px 8px',
                    background: 'rgba(205,127,50,0.15)',
                    borderRadius: 4,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    color: 'var(--bronze)',
                  }}>
                    {task.agent}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    color: task.status === 'routed' ? 'var(--online)' : 'var(--gold)',
                  }}>
                    {task.status.toUpperCase()}
                  </span>
                  <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>
                    {new Date(task.ts * 1000).toLocaleTimeString()}
                  </span>
                </div>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-secondary)' }}>
                  {task.task}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Broadcast + Notifications */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Broadcast */}
        <div className="panel" style={{ padding: 20 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 12 }}>
            BROADCAST TO ALL AGENTS
          </div>
          <input
            value={broadcastMsg}
            onChange={(e) => setBroadcastMsg(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && broadcast()}
            placeholder="Send a message to all agents..."
            className="input-dark"
            style={{ marginBottom: 10 }}
          />
          <motion.button
            onClick={broadcast}
            disabled={broadcasting || !broadcastMsg.trim()}
            whileTap={{ scale: 0.97 }}
            className="btn-gold"
            style={{ opacity: broadcasting ? 0.6 : 1 }}
          >
            {broadcasting ? '...' : '📡 BROADCAST'}
          </motion.button>
        </div>

        {/* Notifications */}
        <div className="panel" style={{ padding: 20 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 12 }}>
            NOTIFICATION SETTINGS
          </div>
          {/* Channel toggles */}
          {(['whatsapp', 'telegram'] as const).map((ch) => (
            <label key={ch} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              marginBottom: 10,
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
              fontSize: 13,
              color: 'var(--text-secondary)',
            }}>
              <input
                type="checkbox"
                checked={notifs[ch]}
                onChange={() => toggleNotif(ch)}
                style={{ accentColor: 'var(--gold)', width: 16, height: 16 }}
              />
              {ch.charAt(0).toUpperCase() + ch.slice(1)} notifications
            </label>
          ))}
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1, margin: '12px 0 8px' }}>
            TRIGGERS
          </div>
          {(Object.keys(notifs.triggers) as (keyof NotifSettings['triggers'])[]).map((key) => (
            <label key={key} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              marginBottom: 8,
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
              fontSize: 12,
              color: 'var(--text-secondary)',
            }}>
              <input
                type="checkbox"
                checked={notifs.triggers[key]}
                onChange={() => toggleTrigger(key)}
                style={{ accentColor: 'var(--gold)', width: 14, height: 14 }}
              />
              {key.replace(/_/g, ' ')}
            </label>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
