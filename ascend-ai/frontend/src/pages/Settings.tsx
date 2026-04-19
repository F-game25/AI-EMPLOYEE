import { motion } from 'framer-motion'
import { useState, useEffect } from 'react'

type Category = 'general' | 'permissions' | 'apikeys' | 'appearance' | 'backup'

const CATEGORIES: { id: Category; label: string; icon: string }[] = [
  { id: 'general', label: 'General', icon: '⚙' },
  { id: 'permissions', label: 'Mode Permissions', icon: '🔐' },
  { id: 'apikeys', label: 'API Keys', icon: '🔑' },
  { id: 'appearance', label: 'Appearance', icon: '🎨' },
  { id: 'backup', label: 'Backup & Restore', icon: '💾' },
]

const KEY_FIELDS = [
  { name: 'ANTHROPIC_API_KEY', label: 'Anthropic API Key' },
  { name: 'OPENAI_API_KEY', label: 'OpenAI API Key' },
  { name: 'GATEWAY_TOKEN', label: 'Gateway Token' },
]

export function Settings() {
  const [cat, setCat] = useState<Category>('general')
  const [, setSettings] = useState<Record<string, unknown>>({})
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({})
  const [fontSize, setFontSize] = useState('normal')
  const [animation, setAnimation] = useState('full')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((d) => setSettings(d))
      .catch(() => {})
  }, [])

  const saveKey = async (name: string) => {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings: { api_keys: { [name]: keys[name] } } }),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const exportConfig = async () => {
    const r = await fetch('/api/settings')
    const data = await r.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'ascend-config.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const resetAll = async () => {
    if (!window.confirm('Reset ALL settings to defaults? This cannot be undone.')) return
    await fetch('/api/settings/reset', { method: 'POST' })
    window.location.reload()
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700, marginBottom: 20 }} className="metallic-text">
        ⚙ SETTINGS
      </h1>

      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 20 }}>
        {/* Category nav */}
        <div className="panel" style={{ padding: '12px 0' }}>
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              onClick={() => setCat(c.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: '10px 16px',
                background: cat === c.id ? 'rgba(212,175,55,0.06)' : 'transparent',
                border: 'none',
                borderLeft: cat === c.id ? '2px solid var(--gold)' : '2px solid transparent',
                color: cat === c.id ? 'var(--gold)' : 'var(--text-secondary)',
                fontFamily: 'var(--font-body)',
                fontSize: 13,
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <span>{c.icon}</span>
              {c.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="panel" style={{ padding: 24 }}>
          {cat === 'general' && (
            <div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 18, marginBottom: 16 }} className="metallic-text">General Settings</h2>
              <label style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text-secondary)', marginBottom: 12 }}>
                <input type="checkbox" defaultChecked={false} style={{ accentColor: 'var(--gold)' }} />
                Auto-start agents on launch
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text-secondary)' }}>
                <input type="checkbox" defaultChecked={true} style={{ accentColor: 'var(--gold)' }} />
                Enable WebSocket live updates
              </label>
            </div>
          )}

          {cat === 'permissions' && (
            <div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 18, marginBottom: 16 }} className="metallic-text">Mode Permissions</h2>
              {['Ascend Forge', 'Money Mode', 'Blacklight'].map((mode) => (
                <label key={mode} style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text-secondary)', marginBottom: 10 }}>
                  <input type="checkbox" defaultChecked={true} style={{ accentColor: 'var(--gold)' }} />
                  {mode} — Enabled
                </label>
              ))}
            </div>
          )}

          {cat === 'apikeys' && (
            <div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 18, marginBottom: 16 }} className="metallic-text">API Keys</h2>
              {saved && <div style={{ padding: '6px 12px', background: 'rgba(52,211,153,0.1)', borderRadius: 6, color: 'var(--online)', fontFamily: 'var(--font-mono)', fontSize: 11, marginBottom: 12 }}>✓ Saved</div>}
              {KEY_FIELDS.map((kf) => (
                <div key={kf.name} style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <span className={`dot ${keys[kf.name] ? 'online' : ''}`} style={{ opacity: keys[kf.name] ? 1 : 0.3 }} />
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{kf.label}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      type={showKeys[kf.name] ? 'text' : 'password'}
                      value={keys[kf.name] || ''}
                      onChange={(e) => setKeys({ ...keys, [kf.name]: e.target.value })}
                      placeholder="Enter key..."
                      className="input-dark"
                      style={{ flex: 1, border: '1px solid rgba(212,175,55,0.2)' }}
                    />
                    <button
                      onClick={() => setShowKeys({ ...showKeys, [kf.name]: !showKeys[kf.name] })}
                      className="btn-outline"
                    >
                      {showKeys[kf.name] ? 'HIDE' : 'SHOW'}
                    </button>
                    <motion.button onClick={() => saveKey(kf.name)} whileTap={{ scale: 0.96 }} className="btn-gold" style={{ padding: '8px 16px' }}>
                      SAVE
                    </motion.button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {cat === 'appearance' && (
            <div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 18, marginBottom: 16 }} className="metallic-text">Appearance</h2>
              <div style={{ marginBottom: 20 }}>
                <span style={{
                  display: 'inline-block',
                  padding: '6px 16px',
                  background: 'rgba(212,175,55,0.1)',
                  border: '1px solid var(--gold)',
                  borderRadius: 20,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--gold)',
                  fontWeight: 700,
                }}>
                  ASCEND THEME — LOCKED
                </span>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1, marginBottom: 8 }}>FONT SIZE</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {['normal', 'large'].map((s) => (
                    <button
                      key={s}
                      onClick={() => setFontSize(s)}
                      style={{
                        padding: '6px 16px',
                        background: fontSize === s ? 'var(--gold)' : 'transparent',
                        color: fontSize === s ? '#0A0A0A' : 'var(--text-dim)',
                        border: 'var(--border-gold)',
                        borderRadius: 6,
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        cursor: 'pointer',
                        textTransform: 'uppercase',
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1, marginBottom: 8 }}>ANIMATION INTENSITY</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {['full', 'reduced', 'off'].map((s) => (
                    <button
                      key={s}
                      onClick={() => setAnimation(s)}
                      style={{
                        padding: '6px 16px',
                        background: animation === s ? 'var(--gold)' : 'transparent',
                        color: animation === s ? '#0A0A0A' : 'var(--text-dim)',
                        border: 'var(--border-gold)',
                        borderRadius: 6,
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        cursor: 'pointer',
                        textTransform: 'uppercase',
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {cat === 'backup' && (
            <div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 18, marginBottom: 16 }} className="metallic-text">Backup & Restore</h2>
              <div style={{ display: 'flex', gap: 12 }}>
                <motion.button onClick={exportConfig} whileHover={{ scale: 1.02 }} className="btn-gold">
                  📤 EXPORT CONFIG
                </motion.button>
                <motion.button onClick={resetAll} whileHover={{ scale: 1.02 }} className="btn-outline" style={{ color: 'var(--offline)', borderColor: 'rgba(239,68,68,0.3)' }}>
                  🗑 RESET TO DEFAULTS
                </motion.button>
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
