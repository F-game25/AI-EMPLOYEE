import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../../store/appStore'
import './CommandPalette.css'

// ── Item definitions ─────────────────────────────────────────────────────────

const PAGES = [
  { id: 'nexus',         label: 'Dashboard',        icon: '⬡' },
  { id: 'cognition',     label: 'Cognition',         icon: '◈' },
  { id: 'agents',        label: 'Agents',            icon: '◉' },
  { id: 'memory',        label: 'Memory',            icon: '▦' },
  { id: 'economy',       label: 'Economy',           icon: '◇' },
  { id: 'tasks',         label: 'Tasks',             icon: '▣' },
  { id: 'workflows',     label: 'Workflows',         icon: '▷' },
  { id: 'workspace',     label: 'Workspace',         icon: '⊞' },
  { id: 'infrastructure',label: 'Infrastructure',    icon: '▤' },
  { id: 'setup',         label: 'Setup Center',      icon: '⚙' },
  { id: 'approvals',     label: 'Approval Inbox',    icon: '✓' },
  { id: 'proof',         label: 'Proof Center',      icon: '▥' },
  { id: 'neural-graph',  label: 'Neural Graph',      icon: '◈' },
  { id: 'knowledge',     label: 'Knowledge',         icon: '▩' },
  { id: 'trends',        label: 'Trends',            icon: '△' },
  { id: 'research',      label: 'Research',          icon: '◎' },
  { id: 'recon',         label: 'Recon',             icon: '⌕' },
  { id: 'policies',      label: 'Policies',          icon: '▦' },
  { id: 'permissions',   label: 'Permissions',       icon: '▧' },
  { id: 'sandboxes',     label: 'Sandboxes',         icon: '▨' },
  { id: 'audit',         label: 'Audit',             icon: '▥' },
  { id: 'models',        label: 'Models',            icon: '◑' },
  { id: 'model-fabric',  label: 'Model Fabric',      icon: '▦' },
  { id: 'runtime',       label: 'Runtime',           icon: '▶' },
  { id: 'integrations',  label: 'Integrations',      icon: '◫' },
  { id: 'api-catalog',   label: 'API Catalog',       icon: '▤' },
  { id: 'user-views',    label: 'Perspectives',      icon: '◌' },
  { id: 'settings',      label: 'Settings',          icon: '◎' },
]

const ACTIONS = [
  { id: 'action:chat',          label: 'Ask AI Teammate',        icon: '↵', event: 'nx:chat:open', page: 'nexus', badge: 'CHAT' },
  { id: 'action:new-task',      label: 'Run New Task',           icon: '+', event: 'nx:task:new', page: 'tasks', badge: 'TASK' },
  { id: 'action:setup-check',   label: 'Run Setup Check',        icon: '✓', page: 'setup', badge: 'ADMIN' },
  { id: 'action:review-proof',  label: 'Review Latest Proof',    icon: '▥', page: 'proof', badge: 'PROOF' },
  { id: 'action:approvals',     label: 'Open Approval Queue',    icon: '!', page: 'approvals', badge: 'SAFETY' },
  { id: 'action:user-views',    label: 'Choose Perspective',     icon: '◌', page: 'user-views', badge: 'ROLES' },
  { id: 'action:models',        label: 'Test Model Providers',   icon: '◑', page: 'models', badge: 'LLM' },
  { id: 'action:integrations',  label: 'Check Integrations',     icon: '◫', page: 'integrations', badge: 'SETUP' },
  { id: 'action:api-catalog',   label: 'Inspect API Catalog',    icon: '▤', page: 'api-catalog', badge: 'ADMIN' },
  { id: 'action:system-health', label: 'Open System Health',     icon: '▨', page: 'system', badge: 'OPS' },
  { id: 'action:spawn-agent',   label: 'Spawn Agent',            icon: '◉', event: 'nx:agent:spawn', page: 'agents', badge: 'AGENT' },
  { id: 'action:stop',          label: 'Emergency Stop',         icon: '■', event: 'nx:system:stop', page: 'settings', badge: 'SAFETY' },
  { id: 'action:scan',          label: 'System Scan',            icon: '◈', event: 'nx:system:scan', page: 'security', badge: 'SECURITY' },
]

const GROUPS = [
  { key: 'pages',   label: 'Pages',          items: PAGES,   kind: 'page' },
  { key: 'actions', label: 'Quick Actions',  items: ACTIONS, kind: 'action' },
]

// ── Fuzzy match ───────────────────────────────────────────────────────────────

function matches(item, query) {
  return !query || item.label.toLowerCase().includes(query.toLowerCase())
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CommandPalette() {
  const [open, setOpen]   = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef(null)
  const listRef  = useRef(null)
  const setActiveSection = useAppStore(s => s.setActiveSection)

  // Build flat navigable list from filtered groups
  const flatItems = GROUPS.flatMap(g =>
    g.items.filter(i => matches(i, query)).map(i => ({ ...i, kind: g.kind }))
  )

  const openPalette = useCallback(() => {
    setQuery('')
    setCursor(0)
    setOpen(true)
  }, [])

  const closePalette = useCallback(() => setOpen(false), [])

  // Event listener + Ctrl/Cmd+K global hotkey
  useEffect(() => {
    const onOpen = () => openPalette()
    const onKey  = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        openPalette()
      }
    }
    window.addEventListener('nx:command-palette:open', onOpen)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('nx:command-palette:open', onOpen)
      window.removeEventListener('keydown', onKey)
    }
  }, [openPalette])

  // Auto-focus on open
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  // Reset cursor when query changes
  useEffect(() => { setCursor(0) }, [query])

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.querySelector('[data-active="true"]')
    el?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  const selectItem = useCallback((item) => {
    if (item.kind === 'page') {
      setActiveSection(item.id)
    } else {
      if (item.page) setActiveSection(item.page)
      if (item.event) window.dispatchEvent(new CustomEvent(item.event))
    }
    closePalette()
  }, [setActiveSection, closePalette])

  const onKeyDown = useCallback((e) => {
    if (e.key === 'Escape') { closePalette(); return }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor(c => Math.min(c + 1, flatItems.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor(c => Math.max(c - 1, 0))
    } else if (e.key === 'Enter' && flatItems[cursor]) {
      e.preventDefault()
      selectItem(flatItems[cursor])
    }
  }, [flatItems, cursor, closePalette, selectItem])

  if (!open) return null

  // Rebuild group-aware render list
  let globalIdx = 0
  const renderedGroups = GROUPS.map(g => {
    const filtered = g.items.filter(i => matches(i, query))
    const rendered = filtered.map(item => {
      const idx = globalIdx++
      const isActive = idx === cursor
      return (
        <button
          key={item.id}
          type="button"
          className={`cp-item${isActive ? ' cp-item--active' : ''}`}
          data-active={isActive}
          onMouseEnter={() => setCursor(idx)}
          onClick={() => selectItem({ ...item, kind: g.kind })}
          tabIndex={-1}
        >
          <span className="cp-item__icon">{item.icon}</span>
          <span className="cp-item__label">{item.label}</span>
          {g.kind === 'action' && (
            <span className="cp-item__badge">{item.badge || 'ACTION'}</span>
          )}
        </button>
      )
    })
    return { key: g.key, label: g.label, rendered }
  })

  return (
    <div className="cp-overlay" onClick={closePalette} aria-modal="true" role="dialog">
      <div className="cp-modal" onClick={e => e.stopPropagation()} onKeyDown={onKeyDown}>
        {/* Search input */}
        <div className="cp-search">
          <span className="cp-search__icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </span>
          <input
            ref={inputRef}
            className="cp-search__input"
            type="text"
            placeholder="Search commands, pages, actions…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          <span className="cp-search__hint">ESC</span>
        </div>

        {/* Results */}
        <div className="cp-list" ref={listRef}>
          {flatItems.length === 0 ? (
            <div className="cp-empty">No results for "{query}"</div>
          ) : (
            renderedGroups.map(g =>
              g.rendered.length > 0 && (
                <div key={g.key} className="cp-group">
                  <div className="cp-group__label">{g.label}</div>
                  {g.rendered}
                </div>
              )
            )
          )}
        </div>

        {/* Footer hint */}
        <div className="cp-footer">
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> select</span>
          <span><kbd>ESC</kbd> close</span>
        </div>
      </div>
    </div>
  )
}
