import { useCallback, useEffect, useState } from 'react'
import { ensureOperatorToken } from '../api/auth'

export default function LoginPage({ onSuccess }) {
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // 'auto' while attempting the localhost auto-token; 'manual' once it fails
  // and an operator secret is genuinely required (non-localhost access).
  const [phase, setPhase] = useState('auto')

  const tryAuto = useCallback(() => {
    let cancelled = false
    setPhase('auto')
    setError('')
    ensureOperatorToken({ force: true }).then(token => {
      if (cancelled) return
      if (token) onSuccess(token)
      else setPhase('manual')
    })
    return () => { cancelled = true }
  }, [onSuccess])

  // On localhost the operator never needs a secret — the app self-unlocks.
  useEffect(() => tryAuto(), [tryAuto])

  const submit = async (e) => {
    e.preventDefault()
    if (!secret.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      const res = await fetch('/api/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ secret: secret.trim() }),
        signal: AbortSignal.timeout(8000),
      })
      const d = await res.json().catch(() => ({}))
      if (!res.ok || !d.token) {
        setError(d.error || 'Invalid secret — check ~/.ai-employee/.env for JWT_SECRET_KEY')
        return
      }
      onSuccess(d.token)
    } catch (e) {
      setError(e.message || 'Connection failed — is the server running?')
    } finally {
      setBusy(false)
    }
  }

  if (phase === 'auto') {
    return (
      <div style={styles.overlay}>
        <div style={styles.card}>
          <div style={{ ...styles.logo, animation: 'nxLoginPulse 1.4s ease-in-out infinite' }}>◆</div>
          <h1 style={styles.title}>NEXUS OS</h1>
          <p style={styles.sub}>Connecting to local instance…</p>
          <style>{'@keyframes nxLoginPulse{0%,100%{opacity:.5}50%{opacity:1}}'}</style>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.overlay}>
      <form onSubmit={submit} style={styles.card}>
        <div style={styles.logo}>◆</div>
        <h1 style={styles.title}>NEXUS OS</h1>
        <p style={styles.sub}>Remote access — enter your operator secret to continue</p>
        <input
          type="password"
          autoFocus
          placeholder="Operator secret key"
          value={secret}
          onChange={e => { setSecret(e.target.value); setError('') }}
          style={styles.input}
          disabled={busy}
          autoComplete="current-password"
        />
        {error && <div style={styles.error}>{error}</div>}
        <button type="submit" style={styles.btn} disabled={busy || !secret.trim()}>
          {busy ? 'Authenticating…' : 'Unlock'}
        </button>
        <button type="button" onClick={tryAuto} style={styles.linkBtn} disabled={busy}>
          Retry automatic unlock
        </button>
        <p style={styles.hint}>
          On this machine no secret is needed. From another device, the secret is in
          {' '}<code style={styles.code}>~/.ai-employee/.env</code> as <code style={styles.code}>JWT_SECRET_KEY</code>
        </p>
      </form>
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: '#050608',
  },
  card: {
    width: 380,
    background: 'rgba(14,16,32,0.98)',
    border: '1px solid rgba(229,199,107,0.3)',
    borderRadius: 12,
    padding: '40px 36px',
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
    boxShadow: '0 24px 64px rgba(0,0,0,0.8)',
  },
  logo: {
    fontSize: 32, color: '#e5c76b',
    filter: 'drop-shadow(0 0 12px rgba(229,199,107,0.6))',
  },
  title: {
    margin: 0, fontSize: 18, fontWeight: 800,
    letterSpacing: '0.18em', color: '#e5c76b',
    fontFamily: 'var(--nx-font-mono, monospace)',
  },
  sub: {
    margin: 0, fontSize: 12, color: '#6b7280',
    letterSpacing: '0.06em', textAlign: 'center',
  },
  input: {
    width: '100%', padding: '10px 14px',
    background: '#070a10', border: '1px solid rgba(229,199,107,0.2)',
    borderRadius: 6, color: '#e5e7eb', fontSize: 14,
    fontFamily: 'monospace', outline: 'none', boxSizing: 'border-box',
  },
  error: {
    width: '100%', padding: '8px 12px',
    background: 'rgba(127,29,29,0.3)', border: '1px solid rgba(239,68,68,0.4)',
    borderRadius: 6, color: '#ef4444', fontSize: 12,
    textAlign: 'center',
  },
  btn: {
    width: '100%', padding: '11px 0',
    background: 'linear-gradient(135deg, #c9a227, #e5c76b)',
    border: 'none', borderRadius: 6,
    color: '#14110a', fontSize: 13, fontWeight: 700,
    letterSpacing: '0.1em', textTransform: 'uppercase',
    cursor: 'pointer',
  },
  linkBtn: {
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#9ca3af', fontSize: 11, letterSpacing: '0.08em',
    textDecoration: 'underline', padding: 0,
  },
  hint: {
    margin: 0, fontSize: 11, color: '#374151', textAlign: 'center',
  },
  code: {
    color: '#9ca3af', fontFamily: 'monospace', fontSize: 10,
  },
}
