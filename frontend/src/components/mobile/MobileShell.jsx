/* NEXUS OS — Mobile Shell: lock screen, tab bar, command palette, notifications, toast */
import { useState, useEffect, useCallback, useRef } from 'react'
import MobileDashboard from './screens/MobileDashboard'
import MobileAgents from './screens/MobileAgents'
import MobileChat from './screens/MobileChat'
import MobileSecurity from './screens/MobileSecurity'
import MobileMore from './screens/MobileMore'
import MobileTasks from './screens/MobileTasks'
import MobileBlacklight from './screens/MobileBlacklight'
import MobileForge from './screens/MobileForge'
import MobileApprovals from './screens/MobileApprovals'
import './MobileShell.css'

// ── Constants ─────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'cmd',    icon: '◈', label: 'CMD' },
  { id: 'agents', icon: '◉', label: 'Agents' },
  { id: 'chat',   icon: '▷', label: 'Chat' },
  { id: 'secure', icon: '⬡', label: 'Secure' },
  { id: 'more',   icon: '≡', label: 'More' },
]

const COMMANDS = [
  { id: 'cmd',    label: 'Go to Dashboard',    icon: '◈' },
  { id: 'agents', label: 'Go to Agents',        icon: '◉' },
  { id: 'chat',   label: 'Open Chat',           icon: '▷' },
  { id: 'secure', label: 'Security Overview',   icon: '⬡' },
  { id: 'tasks',  label: 'View Tasks',          icon: '▣' },
  { id: 'more',   label: 'More Pages',          icon: '≡' },
]

const MOCK_NOTIFS = [
  { id: '1', title: 'Research complete', body: 'Market analysis finished successfully.', ts: '2m ago', read: false },
  { id: '2', title: 'Agent deployed', body: 'Content agent is now running.', ts: '8m ago', read: false },
  { id: '3', title: 'System status', body: 'All systems nominal.', ts: '22m ago', read: true },
]

// ── LockScreen ────────────────────────────────────────────────────────────────
function LockScreen({ onUnlock }) {
  const [attempts, setAttempts] = useState(0)
  const [scanning, setScanning] = useState(false)
  const [message, setMessage] = useState('Touch to authenticate')
  const [shaking, setShaking] = useState(false)

  const handleTap = useCallback(() => {
    if (scanning) return
    setScanning(true)
    setMessage('Scanning…')
    setTimeout(() => {
      if (attempts === 0 && Math.random() < 0.18) {
        setScanning(false)
        setShaking(true)
        setMessage('Not recognized — try again')
        setAttempts(1)
        setTimeout(() => { setShaking(false); setMessage('Touch to authenticate') }, 1000)
      } else {
        setMessage('Authenticated ✓')
        setTimeout(onUnlock, 300)
      }
    }, 800)
  }, [attempts, scanning, onUnlock])

  return (
    <div className="nxm-lock" onClick={handleTap}>
      <div className="nxm-lock__bg" />
      <div className="nxm-lock__content">
        <div className="nxm-lock__logo">◆</div>
        <div className="nxm-lock__title">NEXUS OS</div>
        <div className="nxm-lock__sub">Secure AI Operating System</div>
        <div className={`nxm-lock__ring ${scanning ? 'nxm-lock__ring--scanning' : ''} ${shaking ? 'nxm-lock__ring--shake' : ''}`}>
          <div className="nxm-lock__ring-inner">
            {scanning ? (
              <div className="nxm-lock__ring-pulse" />
            ) : (
              <span style={{ fontSize: 24, color: 'var(--gold)' }}>◈</span>
            )}
          </div>
        </div>
        <div className="nxm-lock__hint">{message}</div>
      </div>
    </div>
  )
}

// ── CommandPalette ────────────────────────────────────────────────────────────
function CommandPalette({ open, onClose, onSelect }) {
  const [query, setQuery] = useState('')
  const [idx, setIdx] = useState(0)
  const inputRef = useRef(null)

  useEffect(() => {
    if (open) { setQuery(''); setIdx(0); setTimeout(() => inputRef.current?.focus(), 50) }
  }, [open])

  const filtered = COMMANDS.filter(c => c.label.toLowerCase().includes(query.toLowerCase()))

  const onKey = useCallback(e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(i + 1, filtered.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(i => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter') { if (filtered[idx]) onSelect(filtered[idx].id) }
    else if (e.key === 'Escape') onClose()
  }, [filtered, idx, onSelect, onClose])

  if (!open) return null
  return (
    <div className="nxm-palette-overlay" onClick={onClose}>
      <div className="nxm-palette" onClick={e => e.stopPropagation()}>
        <div className="nxm-palette__bar">
          <span style={{ color: 'var(--gold)', fontSize: 14 }}>⌕</span>
          <input ref={inputRef} className="nxm-palette__input" placeholder="Type a command…"
            value={query} onChange={e => { setQuery(e.target.value); setIdx(0) }}
            onKeyDown={onKey} />
          <button className="nxm-palette__esc" onClick={onClose}>ESC</button>
        </div>
        <div className="nxm-palette__list">
          {filtered.length === 0 ? (
            <div className="nxm-palette__empty">No commands found</div>
          ) : filtered.map((c, i) => (
            <button key={c.id} className={`nxm-palette__item ${i === idx ? 'nxm-palette__item--active' : ''}`}
              onClick={() => onSelect(c.id)} onMouseEnter={() => setIdx(i)}>
              <span style={{ fontSize: 16, color: 'var(--gold)', width: 24 }}>{c.icon}</span>
              <span style={{ flex: 1, fontSize: 13 }}>{c.label}</span>
              {i === idx && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>↵</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── NotificationDrawer ────────────────────────────────────────────────────────
function NotificationDrawer({ open, onClose, notifications, onMarkAll }) {
  if (!open) return null
  const unread = notifications.filter(n => !n.read).length
  return (
    <>
      <div className="nxm-notif-overlay" onClick={onClose} />
      <div className="nxm-notif-drawer">
        <div className="nxm-notif-header">
          <span>Notifications</span>
          {unread > 0 && <span className="nxm-notif-badge">{unread} new</span>}
          {onMarkAll && <button className="nxm-notif-markall" onClick={onMarkAll}>Mark all read</button>}
        </div>
        <div className="nxm-notif-list">
          {notifications.length === 0 ? (
            <div className="nxm-notif-empty">No notifications</div>
          ) : notifications.map(n => (
            <div key={n.id} className={`nxm-notif-item ${!n.read ? 'nxm-notif-item--unread' : ''}`}>
              <div className="nxm-notif-item-title">{n.title}</div>
              <div className="nxm-notif-item-body">{n.body}</div>
              <div className="nxm-notif-item-ts">{n.ts}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function Toast({ message, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 2400)
    return () => clearTimeout(t)
  }, [onDone])
  return <div className="nxm-toast">{message}</div>
}

// ── MobileShell ───────────────────────────────────────────────────────────────
export default function MobileShell() {
  const [locked, setLocked] = useState(true)
  const [tab, setTab] = useState('cmd')
  const [subScreen, setSubScreen] = useState(null) // 'tasks' etc
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifications, setNotifications] = useState(MOCK_NOTIFS)
  const [toast, setToast] = useState(null)
  const [selectedAgent, setSelectedAgent] = useState(null)

  const unread = notifications.filter(n => !n.read).length

  const markAllRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
  }, [])

  const showToast = useCallback((msg) => { setToast(msg) }, [])

  const handleCommand = useCallback((id) => {
    setPaletteOpen(false)
    if (id === 'tasks') { setTab('more'); setSubScreen('tasks') }
    else { setTab(id); setSubScreen(null) }
  }, [])

  // Listen for WS notification events
  useEffect(() => {
    const handler = e => {
      const d = e.detail || {}
      if (d.title || d.message) {
        setNotifications(prev => [
          { id: Date.now().toString(), title: d.title || 'Notification', body: d.message || '', ts: 'now', read: false },
          ...prev.slice(0, 19),
        ])
      }
    }
    window.addEventListener('ws:notification', handler)
    window.addEventListener('ws:task:completed', handler)
    return () => {
      window.removeEventListener('ws:notification', handler)
      window.removeEventListener('ws:task:completed', handler)
    }
  }, [])

  if (locked) return <LockScreen onUnlock={() => setLocked(false)} />

  const handleNavigate = useCallback((id) => {
    if (id === 'tasks') { setSubScreen('tasks') }
    else if (id === 'forge' || id === 'ascendforge') { setSubScreen('forge') }
    else if (id === 'blacklight' || id === 'recon' || id === 'security') { setSubScreen('blacklight') }
    else if (id === 'approvals') { setSubScreen('approvals') }
  }, [])

  // HITL toast notification
  useEffect(() => {
    const handler = e => {
      const d = e.detail || {}
      setNotifications(prev => [
        { id: Date.now().toString(), title: '⚠ Approval needed', body: d.message || 'Action requires your approval', ts: 'now', read: false, type: 'hitl' },
        ...prev.slice(0, 19),
      ])
      showToast('⚠ Approval needed — tap MORE → Approvals')
    }
    window.addEventListener('ws:hitl_request', handler)
    return () => window.removeEventListener('ws:hitl_request', handler)
  }, [showToast])

  const renderScreen = () => {
    if (subScreen === 'tasks') return <MobileTasks onBack={() => setSubScreen(null)} />
    if (subScreen === 'forge') return <MobileForge onBack={() => setSubScreen(null)} />
    if (subScreen === 'blacklight') return <MobileBlacklight onBack={() => setSubScreen(null)} />
    if (subScreen === 'approvals') return <MobileApprovals onBack={() => setSubScreen(null)} />
    switch (tab) {
      case 'cmd':    return <MobileDashboard onBell={() => setNotifOpen(true)} unread={unread} onAgentTap={setSelectedAgent} />
      case 'agents': return <MobileAgents />
      case 'chat':   return <MobileChat />
      case 'secure': return <MobileSecurity />
      case 'more':   return <MobileMore onNavigate={handleNavigate} />
      default:       return <MobileDashboard onBell={() => setNotifOpen(true)} unread={unread} />
    }
  }

  return (
    <div className="nxm-shell">
      {/* HUD grid backdrop */}
      <div className="nxm-hud-grid" />

      {/* Status bar */}
      <div className="nxm-statusbar">
        <div className="nxm-statusbar-left">
          <span className="nxm-statusbar-secure">
            <span className="nxm-statusbar-secure-dot" />SECURE
          </span>
        </div>
        <div className="nxm-statusbar-center">NEXUS OS</div>
        <div className="nxm-statusbar-right">
          <button className="nxm-statusbar-btn" onClick={() => setPaletteOpen(true)} aria-label="Search">⌕</button>
          <button className="nxm-statusbar-btn" onClick={() => setNotifOpen(true)} aria-label="Notifications" style={{ position: 'relative' }}>
            🔔{unread > 0 && <span className="nxm-statusbar-badge">{unread}</span>}
          </button>
        </div>
      </div>

      {/* Screen content */}
      <div className="nxm-content">
        {renderScreen()}
      </div>

      {/* Tab bar */}
      <nav className="nxm-tabbar">
        {TABS.map(t => (
          <button key={t.id}
            className={`nxm-tab ${tab === t.id && !subScreen ? 'nxm-tab--active' : ''}`}
            onClick={() => { setTab(t.id); setSubScreen(null) }}>
            {t.id === 'more' && unread > 0 && <span className="nxm-tab-badge">{unread}</span>}
            <span className="nxm-tab-icon">{t.icon}</span>
            <span className="nxm-tab-label">{t.label}</span>
          </button>
        ))}
      </nav>

      {/* Command palette */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onSelect={handleCommand} />

      {/* Notification drawer */}
      <NotificationDrawer open={notifOpen} onClose={() => setNotifOpen(false)}
        notifications={notifications} onMarkAll={markAllRead} />

      {/* Toast */}
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    </div>
  )
}
