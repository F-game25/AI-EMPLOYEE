import { useCallback, useEffect, useRef, useState } from 'react'
import './BootMenu.css'

/* ═══════════════════════════════════════════════════════════════════
   BOOT MENU — pre-boot control screen (before the BootSequence animation).

   Actions: BOOT · UPDATE · REFRESH · REBOOT · STOP
   - Auto-checks for updates on load (GET /api/system/update-status).
   - AUTO-UPDATE: when an update is detected it starts automatically after a
     short cancel window, streaming live progress from POST /api/system/run-update
     (SSE). On success the page reloads to pick up new assets.
   - AUTO-BOOT: when no update is needed, boots automatically after a countdown
     so unattended startups still come up; any interaction cancels it.
   ═══════════════════════════════════════════════════════════════════ */

const AUTO_BOOT_SECONDS = 8
const AUTO_UPDATE_SECONDS = 5

function getToken() {
  return localStorage.getItem('ai_jwt') || sessionStorage.getItem('ai_jwt') || null
}

async function acquireToken() {
  const existing = getToken()
  if (existing) return existing
  try {
    const r = await fetch('/api/auth/auto-token', { signal: AbortSignal.timeout(5000) })
    const d = r.ok ? await r.json() : null
    if (d?.token) {
      localStorage.setItem('ai_jwt', d.token)
      sessionStorage.setItem('ai_jwt', d.token)
      window.dispatchEvent(new CustomEvent('nx:auth-ready'))
      return d.token
    }
  } catch { /* offline or auth disabled — menu still renders */ }
  return null
}

export default function BootMenu({ onBoot }) {
  const [health, setHealth] = useState(null)          // {node, python}
  const [version, setVersion] = useState(null)        // version.json contents
  const [updateInfo, setUpdateInfo] = useState(null)  // {has_update, updater}
  const [busy, setBusy] = useState(null)              // 'updating'|'rebooting'|'halting'|null
  const [log, setLog] = useState([])
  const [stage, setStage] = useState(null)
  const [countdown, setCountdown] = useState(null)    // {kind:'boot'|'update', secs}
  const [armed, setArmed] = useState(null)            // 'stop'|'reboot' double-click confirm
  const cancelledRef = useRef(false)
  const countdownRef = useRef(null)

  const appendLog = useCallback((line) => {
    setLog(l => [...l.slice(-199), line])
  }, [])

  /* ── status checks ─────────────────────────────────────────────── */
  const refreshStatus = useCallback(async () => {
    const token = await acquireToken()
    const auth = token ? { Authorization: `Bearer ${token}` } : {}
    // health (public)
    try {
      const h = await fetch('/health', { signal: AbortSignal.timeout(4000) }).then(r => r.ok ? r.json() : null)
      setHealth({
        node: !!h,
        python: !!(h?.python_backend || h?.python_ok || h?.ai_backend),
      })
    } catch { setHealth({ node: false, python: false }) }
    // update status (auth)
    try {
      const u = await fetch('/api/system/update-status', { headers: auth, signal: AbortSignal.timeout(5000) })
        .then(r => r.ok ? r.json() : null)
      if (u) {
        setVersion(u.version || null)
        setUpdateInfo({ has_update: !!u.has_update, updater: u.updater || {} })
        return !!u.has_update
      }
    } catch { /* endpoint may be unavailable pre-backend */ }
    setUpdateInfo({ has_update: false, updater: {} })
    return false
  }, [])

  /* ── live update via SSE stream ────────────────────────────────── */
  const runUpdate = useCallback(async () => {
    setBusy('updating')
    setStage('starting')
    setLog([])
    appendLog('> Starting system update…')
    const token = await acquireToken()
    try {
      const res = await fetch('/api/system/run-update', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.error || `update endpoint ${res.status}`)
      }
      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const part of parts) {
          const line = part.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'log' && evt.line) { appendLog(`  ${evt.line}`); if (evt.stage) setStage(evt.stage) }
            if (evt.type === 'start') appendLog(`> ${evt.message || 'Update started'}`)
            if (evt.type === 'close' || evt.type === 'done') {
              const ok = evt.ok !== false && evt.code !== 1
              appendLog(ok ? '> Update finished — reloading interface…' : `> Update exited (code ${evt.code ?? '?'})`)
              setStage(ok ? 'done' : 'error')
              if (ok) setTimeout(() => window.location.reload(), 1600)
            }
          } catch { /* keepalive/partial frame */ }
        }
      }
      // Stream ended without explicit close event — treat as finished.
      if (stage !== 'error') {
        appendLog('> Update stream closed — reloading interface…')
        setTimeout(() => window.location.reload(), 1600)
      }
    } catch (e) {
      appendLog(`> Update failed: ${e.message}`)
      setStage('error')
      setBusy(null)
    }
  }, [appendLog, stage])

  /* ── power actions ─────────────────────────────────────────────── */
  const powerAction = useCallback(async (kind) => {
    if (armed !== kind) {            // first click arms; second within 4s executes
      setArmed(kind)
      setTimeout(() => setArmed(a => (a === kind ? null : a)), 4000)
      return
    }
    setArmed(null)
    const token = await acquireToken()
    const auth = token ? { Authorization: `Bearer ${token}` } : {}
    if (kind === 'stop') {
      setBusy('halting')
      appendLog('> Halting system…')
      try { await fetch('/api/system/halt', { method: 'POST', headers: auth }) } catch { /* server dies mid-response */ }
      appendLog('> System halted. You can close this window.')
    } else {
      setBusy('rebooting')
      appendLog('> Rebooting system…')
      try { await fetch('/api/system/restart', { method: 'POST', headers: auth }) } catch { /* expected during restart */ }
      // poll until the server is back, then reload
      const poll = setInterval(async () => {
        try {
          const r = await fetch('/health', { signal: AbortSignal.timeout(2000) })
          if (r.ok) { clearInterval(poll); window.location.reload() }
        } catch { /* still down */ }
      }, 2500)
    }
  }, [armed, appendLog])

  const cancelCountdown = useCallback(() => {
    cancelledRef.current = true
    if (countdownRef.current) clearInterval(countdownRef.current)
    setCountdown(null)
  }, [])

  /* ── mount: check status → auto-update or auto-boot countdown ──── */
  useEffect(() => {
    let alive = true
    ;(async () => {
      const hasUpdate = await refreshStatus()
      if (!alive || cancelledRef.current) return
      const kind = hasUpdate ? 'update' : 'boot'
      const total = hasUpdate ? AUTO_UPDATE_SECONDS : AUTO_BOOT_SECONDS
      let secs = total
      setCountdown({ kind, secs })
      countdownRef.current = setInterval(() => {
        secs -= 1
        if (cancelledRef.current) { clearInterval(countdownRef.current); return }
        if (secs <= 0) {
          clearInterval(countdownRef.current)
          setCountdown(null)
          if (kind === 'update') runUpdate()
          else onBoot?.()
          return
        }
        setCountdown({ kind, secs })
      }, 1000)
    })()
    return () => { alive = false; if (countdownRef.current) clearInterval(countdownRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const ver = version?.version || version?.tag || version?.commit?.slice?.(0, 8) || '—'
  const updating = busy === 'updating'
  const disabled = !!busy

  return (
    <div className="bootmenu" onPointerDown={countdown ? cancelCountdown : undefined}>
      <div className="bootmenu__grid" aria-hidden="true" />
      <div className="bootmenu__panel">
        <div className="bootmenu__brand">
          <span className="bootmenu__brand-title">AETERNUS&nbsp;NEXUS</span>
          <span className="bootmenu__brand-sub">SYSTEM CONTROL</span>
        </div>

        <div className="bootmenu__statusrow">
          <span className={`bootmenu__dot ${health?.node ? 'ok' : 'down'}`} /> NODE
          <span className={`bootmenu__dot ${health?.python ? 'ok' : 'down'}`} /> AI&nbsp;CORE
          <span className="bootmenu__ver">v{ver}</span>
          {updateInfo?.has_update && !updating && (
            <span className="bootmenu__update-badge">UPDATE AVAILABLE</span>
          )}
        </div>

        {countdown && (
          <button type="button" className="bootmenu__countdown" onClick={cancelCountdown}>
            {countdown.kind === 'update'
              ? `AUTO-UPDATE in ${countdown.secs}s — click to cancel`
              : `AUTO-BOOT in ${countdown.secs}s — click to cancel`}
          </button>
        )}

        <div className="bootmenu__actions">
          <button
            type="button" className="bootmenu__btn bootmenu__btn--primary"
            onClick={() => { cancelCountdown(); onBoot?.() }}
            disabled={disabled}
          >▶ BOOT SYSTEM</button>
          <button
            type="button" className="bootmenu__btn"
            onClick={() => { cancelCountdown(); runUpdate() }}
            disabled={disabled}
          >⟳ UPDATE SYSTEM{updateInfo?.has_update ? ' •' : ''}</button>
          <button
            type="button" className="bootmenu__btn"
            onClick={() => { cancelCountdown(); setLog([]); refreshStatus() }}
            disabled={updating}
          >⊙ REFRESH</button>
          <button
            type="button" className={`bootmenu__btn bootmenu__btn--warn${armed === 'reboot' ? ' armed' : ''}`}
            onClick={() => { cancelCountdown(); powerAction('reboot') }}
            disabled={updating}
          >{armed === 'reboot' ? 'CONFIRM REBOOT?' : '↻ REBOOT'}</button>
          <button
            type="button" className={`bootmenu__btn bootmenu__btn--danger${armed === 'stop' ? ' armed' : ''}`}
            onClick={() => { cancelCountdown(); powerAction('stop') }}
            disabled={updating}
          >{armed === 'stop' ? 'CONFIRM STOP?' : '◼ STOP'}</button>
        </div>

        {(log.length > 0 || updating) && (
          <div className="bootmenu__console" role="log" aria-live="polite">
            {stage && <div className="bootmenu__stage">STAGE: {String(stage).toUpperCase()}</div>}
            {log.map((l, i) => <div key={i} className="bootmenu__logline">{l}</div>)}
          </div>
        )}
      </div>
    </div>
  )
}
