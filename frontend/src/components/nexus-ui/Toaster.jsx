import { useEffect, useRef, useState } from 'react'
import './Toaster.css'

/* ─── singleton event bus ─────────────────────────────────────────────── */
const _listeners = new Set()
let _nextId = 0

export function toast(message, { type = 'info', duration = 4000 } = {}) {
  const id = ++_nextId
  const entry = { id, message, type, duration }
  _listeners.forEach(fn => fn(entry))
  return id
}
export const toastSuccess = (msg, opts) => toast(msg, { type: 'success', ...opts })
export const toastError   = (msg, opts) => toast(msg, { type: 'error',   ...opts })
export const toastWarn    = (msg, opts) => toast(msg, { type: 'warn',    ...opts })

/* ─── icons ────────────────────────────────────────────────────────────── */
const ICONS = { success: '✓', error: '✕', warn: '⚠', info: 'i' }

/* ─── Toast item ─────────────────────────────────────────────────────── */
function ToastItem({ entry, onDone }) {
  const [leaving, setLeaving] = useState(false)
  const timerRef = useRef(null)

  const dismiss = () => {
    setLeaving(true)
    setTimeout(onDone, 300)
  }

  useEffect(() => {
    timerRef.current = setTimeout(dismiss, entry.duration)
    return () => clearTimeout(timerRef.current)
  }, [])

  return (
    <div className={`nx-toast nx-toast--${entry.type} ${leaving ? 'nx-toast--out' : ''}`} onClick={dismiss}>
      <span className="nx-toast__icon">{ICONS[entry.type]}</span>
      <span className="nx-toast__msg">{entry.message}</span>
    </div>
  )
}

/* ─── Toaster (mount once in App.jsx) ──────────────────────────────── */
export default function Toaster() {
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    const handler = entry => setToasts(prev => [...prev.slice(-4), entry])
    _listeners.add(handler)
    return () => _listeners.delete(handler)
  }, [])

  const remove = id => setToasts(prev => prev.filter(t => t.id !== id))

  return (
    <div className="nx-toaster">
      {toasts.map(t => <ToastItem key={t.id} entry={t} onDone={() => remove(t.id)} />)}
    </div>
  )
}
