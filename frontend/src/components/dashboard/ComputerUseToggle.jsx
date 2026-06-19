import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useAppStore } from '../../store/appStore'
import api from '../../api/client'

/**
 * ComputerUseToggle — master switch that lets the teammate drive a sandboxed
 * browser (and, later, a desktop) via voice/chat. OFF by default. When ON,
 * read-only browser actions run freely and side-effecting ones still require
 * approval (high-risk-only safety model). When OFF, all browser/desktop
 * capabilities are refused by the companion broker + RPA API.
 */
export default function ComputerUseToggle() {
  const status = useAppStore((s) => s.computerUseStatus)
  const setStatus = useAppStore((s) => s.setComputerUseStatus)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const enabled = !!status?.enabled

  useEffect(() => {
    let alive = true
    api.computerUse.getMode()
      .then((d) => { if (alive && d) setStatus(d) })
      .catch(() => {})
    return () => { alive = false }
  }, [setStatus])

  const apply = useCallback(async (next) => {
    setBusy(true)
    setConfirming(false)
    try {
      const d = await api.computerUse.setMode(next)
      setStatus(d || { enabled: next })
    } catch (e) {
      console.error('Failed to set computer-use mode', e)
    }
    setBusy(false)
  }, [setStatus])

  const onClick = useCallback(() => {
    if (enabled) { apply(false); return }      // turning OFF is always safe
    setConfirming(true)                         // turning ON asks for confirmation
  }, [enabled, apply])

  const color = enabled ? 'var(--success, #00e676)' : 'var(--text-dim, #888)'

  return (
    <div className="ds-card p-3" style={{ position: 'relative' }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <motion.div
            animate={enabled ? { opacity: [1, 0.3, 1] } : { opacity: 0.3 }}
            transition={{ duration: 1.4, repeat: Infinity }}
            className="w-2 h-2 rounded-full"
            style={{ background: color }}
          />
          <span className="font-mono text-xs tracking-widest" style={{ color }}>
            🖥 COMPUTER USE — {enabled ? 'ON' : 'OFF'}
          </span>
        </div>
        <button
          onClick={onClick}
          disabled={busy}
          className="font-mono text-xs px-3 py-1 rounded"
          style={{
            border: `1px solid ${enabled ? 'rgba(0,230,118,0.4)' : 'rgba(255,255,255,0.18)'}`,
            background: enabled ? 'rgba(0,230,118,0.10)' : 'transparent',
            color, cursor: busy ? 'wait' : 'pointer',
          }}
        >
          {busy ? '…' : enabled ? 'DISABLE' : 'ENABLE'}
        </button>
      </div>

      <p className="font-mono" style={{ fontSize: 11, color: 'var(--text-dim,#888)', lineHeight: 1.5 }}>
        {enabled
          ? 'Teammate can browse the web and act on pages. Side-effecting actions (submit, send, purchase) still require your approval.'
          : 'Off — the teammate cannot use a browser. Enable to let it open pages, read, and act (with approval gates).'}
      </p>

      {confirming && (
        <div style={{
          position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.86)',
          display: 'flex', flexDirection: 'column', gap: 10, padding: 14,
          borderRadius: 8, justifyContent: 'center',
        }}>
          <span className="font-mono" style={{ fontSize: 12, color: 'var(--warning,#ffaa00)' }}>
            Enable Computer Use?
          </span>
          <span className="font-mono" style={{ fontSize: 11, color: 'var(--text-dim,#aaa)', lineHeight: 1.5 }}>
            The teammate will be able to open and read web pages and act on them. High-risk
            actions remain approval-gated; you can disable this anytime.
          </span>
          <div className="flex gap-2">
            <button onClick={() => apply(true)} className="font-mono text-xs px-3 py-1 rounded"
              style={{ border: '1px solid rgba(0,230,118,0.4)', background: 'rgba(0,230,118,0.12)', color: 'var(--success,#00e676)' }}>
              ENABLE
            </button>
            <button onClick={() => setConfirming(false)} className="font-mono text-xs px-3 py-1 rounded"
              style={{ border: '1px solid rgba(255,255,255,0.18)', color: 'var(--text-dim,#888)' }}>
              CANCEL
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
