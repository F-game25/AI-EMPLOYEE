import { motion } from 'framer-motion'
import { useState } from 'react'
import { useStore } from '../store/ascendStore'
import { ProgressBar } from '../components/ProgressBar'
import { ModeButton } from '../components/ModeButton'

const page = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.25 } }

export function Dashboard() {
  const { systemStats, mainChat, addMainChat, agents } = useStore()
  const [input, setInput] = useState('')

  const send = async () => {
    if (!input.trim()) return
    addMainChat({ role: 'user', content: input })
    setInput('')
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input }),
      })
      const d = await r.json()
      addMainChat({ role: 'ai', content: d.content })
    } catch {
      addMainChat({ role: 'ai', content: 'Connection error. Check backend.' })
    }
  }

  const forgeStatus = (agents.find((a) => a.name.includes('forge'))?.status || 'offline') as 'online' | 'offline' | 'starting'
  const moneyStatus = (agents.find((a) => a.name.includes('money'))?.status || 'offline') as 'online' | 'offline' | 'starting'
  const blackStatus = (agents.find((a) => a.name.includes('black'))?.status || 'offline') as 'online' | 'offline' | 'starting'

  return (
    <motion.div {...page} style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, height: '100%' }}>
      {/* Chat */}
      <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)' }}>
        <div style={{ padding: '12px 16px', borderBottom: 'var(--border-subtle)', fontFamily: 'var(--font-heading)', fontSize: 13 }} className="metallic-text">
          MAIN AI CHAT
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {mainChat.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: m.role === 'user' ? 20 : -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                background: m.role === 'user' ? 'rgba(212,175,55,0.08)' : 'rgba(205,127,50,0.06)',
                borderLeft: m.role === 'ai' ? '2px solid var(--bronze)' : undefined,
                borderRight: m.role === 'user' ? '2px solid var(--gold)' : undefined,
                padding: '10px 14px',
                borderRadius: 8,
                fontFamily: 'var(--font-body)',
                fontSize: 14,
                lineHeight: 1.6,
                color: m.role === 'system' ? 'var(--text-secondary)' : 'var(--text-primary)',
                fontStyle: m.role === 'system' ? 'italic' : undefined,
              }}
            >
              {m.tag && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--bronze)', marginRight: 8 }}>
                  [{m.tag}]
                </span>
              )}
              {m.content}
            </motion.div>
          ))}
        </div>
        <div style={{ padding: 16, borderTop: 'var(--border-subtle)', display: 'flex', gap: 8 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Send a task or ask anything..."
            className="input-dark"
            style={{ flex: 1 }}
          />
          <motion.button
            onClick={send}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            className="btn-gold"
          >
            SEND
          </motion.button>
        </div>
      </div>

      {/* Right column */}
      <div>
        <div className="panel" style={{ padding: 20, marginBottom: 16 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 16 }}>
            SYSTEM STATS
          </div>
          <ProgressBar value={systemStats.cpu_percent} label="CPU" variant="bronze" />
          <ProgressBar value={Math.round(systemStats.ram_used_gb / (systemStats.ram_total_gb || 1) * 100)} label={`RAM ${systemStats.ram_used_gb}/${systemStats.ram_total_gb}GB`} variant="bronze" />
          <ProgressBar value={systemStats.gpu_percent} label="GPU" variant="bronze" />
          <ProgressBar value={Math.min(systemStats.temp_celsius, 100)} label="TEMP" unit="°C" variant={systemStats.temp_celsius > 70 ? 'gold' : 'bronze'} />
        </div>
        <ModeButton icon="⚗" name="ASCEND FORGE" description="Self-Improvement Engine" status={forgeStatus} route="/forge" />
        <ModeButton icon="💰" name="MONEY MODE" description="Optimization & Revenue" status={moneyStatus} route="/money" />
        <ModeButton icon="🔒" name="BLACKLIGHT" description="Security & Safe Mode" status={blackStatus} route="/blacklight" />
      </div>
    </motion.div>
  )
}
