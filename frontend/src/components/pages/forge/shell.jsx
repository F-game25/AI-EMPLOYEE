/**
 * AscendForge Shell — TopBar, LeftRail, Footer, ForgePanel, 8 View components
 * Implements the bronze-luxury operator cockpit from the Claude Design handoff.
 */
import { useState, useEffect, useRef } from 'react'
import { StatusPill, SectionLabel } from '../../nexus-ui'
import api from '../../../api/client'
import { DiffViewer, FileEditor, ChatPane, FileTree, ProjectPicker, ActionQueue, Terminal, PolicyPreview, ForgeSystemPanel, RunTimeline, UnderstandPane, AgenticPane, RunHistoryPane, RunMetricsPane, BacklogPane, DecomposerPane, SkillsLibraryPane, ModelRouterPane, CyclesPane, RoadmapPane, SuggestionsPane, MemoryV3Pane, SafetyPane } from './components'

// ── SVG Icon system ─────────────────────────────────────────────────────────
const ICONS = {
  compose:  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12.5V14h1.5L11 6.5 9.5 5 2 12.5z"/><path d="M10 4.5 11.5 3 13 4.5 11.5 6"/></svg>,
  activity: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M1 8h3l2-5 4 10 2-5h3"/></svg>,
  diff:     <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="4" cy="4" r="2"/><circle cx="12" cy="12" r="2"/><path d="M4 6v4a2 2 0 0 0 2 2h4"/><path d="M12 10V6a2 2 0 0 0-2-2H6"/></svg>,
  check:    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 8 3 3 7-7"/></svg>,
  pipeline: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="3" cy="4" r="1.5"/><circle cx="13" cy="4" r="1.5"/><circle cx="3" cy="12" r="1.5"/><circle cx="13" cy="12" r="1.5"/><circle cx="8" cy="8" r="1.5"/><path d="M4.5 4 6.5 7M11.5 4 9.5 7M6.5 9 4.5 12M9.5 9l2 3"/></svg>,
  files:    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h4l1.5 1.5H14V13H2V3z"/></svg>,
  history:  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l2.5 2"/></svg>,
  agents:   <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="5" cy="6" r="2"/><circle cx="11" cy="6" r="2"/><path d="M2 13c0-2 1.5-3 3-3s3 1 3 3M8 13c0-2 1.5-3 3-3s3 1 3 3"/></svg>,
  search:   <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/></svg>,
  pause:    <svg viewBox="0 0 14 14" fill="currentColor"><rect x="3" y="2" width="3" height="10" rx="0.5"/><rect x="8" y="2" width="3" height="10" rx="0.5"/></svg>,
  play:     <svg viewBox="0 0 14 14" fill="currentColor"><path d="M3 2v10l9-5z"/></svg>,
  bell:     <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3.5 12h9l-1-2V7a3.5 3.5 0 0 0-7 0v3l-1 2zM6.5 13.5a1.5 1.5 0 0 0 3 0"/></svg>,
  settings: <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="2"/><path d="M8 1v2M8 13v2M3 8H1M15 8h-2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/></svg>,
  send:     <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M1.5 7 13 1.5 7.5 13 6 8z"/></svg>,
  branch:   <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="3" cy="3" r="1.5"/><circle cx="3" cy="11" r="1.5"/><circle cx="11" cy="5.5" r="1.5"/><path d="M3 4.5v5M4 5.5c0 2 4 1.5 6 0"/></svg>,
  spark:    <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M7 1v3M7 10v3M1 7h3M10 7h3M2.5 2.5l2 2M9.5 9.5l2 2M2.5 11.5l2-2M9.5 4.5l2-2"/></svg>,
  zap:      <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="m7 1-4 7h3l-1 5 4-7H6z" fillOpacity="0.15" fill="currentColor"/></svg>,
  cross:    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M3 3l10 10M13 3 3 13"/></svg>,
  folder:   <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M1.5 2.5h3l1 1H10.5v6h-9z"/></svg>,
  file:     <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 1.5h4.5L9.5 3.5V10.5h-6.5z"/></svg>,
  chevron:  <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 2 7 5 3 8"/></svg>,
  more:     <svg viewBox="0 0 14 14" fill="currentColor"><circle cx="3" cy="7" r="1"/><circle cx="7" cy="7" r="1"/><circle cx="11" cy="7" r="1"/></svg>,
}

function Icon({ name, size = 16 }) {
  const ic = ICONS[name]
  if (!ic) return null
  return <svg width={size} height={size} viewBox={ic.props.viewBox} fill={ic.props.fill} stroke={ic.props.stroke} strokeWidth={ic.props.strokeWidth} strokeLinecap={ic.props.strokeLinecap} strokeLinejoin={ic.props.strokeLinejoin}>{ic.props.children}</svg>
}

// ── Spark mini-chart ─────────────────────────────────────────────────────────
function Spark({ data, color = '#CD7F32', w = 60, h = 14, fill }) {
  if (!data?.length) return null
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 2) - 1}`).join(' ')
  return (
    <svg width={w} height={h}>
      {fill && <polygon points={`0,${h} ${pts} ${w},${h}`} fill={color} fillOpacity="0.14" />}
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── ForgePanel — design's .af-panel with corner ticks ───────────────────────
export function ForgePanel({ title, sub, tone, actions, footer, flush, children, style, bodyStyle }) {
  const cls = ['af-panel', tone ? `af-panel--${tone}` : ''].filter(Boolean).join(' ')
  return (
    <div className={cls} style={style}>
      <span className="af-tick af-tick--tl" /><span className="af-tick af-tick--tr" />
      <span className="af-tick af-tick--bl" /><span className="af-tick af-tick--br" />
      {(title || actions) && (
        <div className="af-panel__head">
          <div className="af-flex" style={{ gap: 8, minWidth: 0 }}>
            {title && <span className="af-label">{title}</span>}
            {sub && <span style={{ font: '500 9.5px monospace', letterSpacing: '0.10em', color: 'var(--af-text-dim)', marginLeft: 4 }}>{sub}</span>}
          </div>
          {actions && <div className="af-flex" style={{ gap: 6 }}>{actions}</div>}
        </div>
      )}
      <div className={`af-panel__body ${flush ? 'af-panel__body--flush' : ''}`} style={bodyStyle}>{children}</div>
      {footer && <div className="af-panel__foot">{footer}</div>}
    </div>
  )
}

// ── ForgeSystemsNav — always-visible pill strip for direct section access ─────
const FORGE_SECTIONS = [
  { id: 'run',         label: 'Run',       icon: '▶' },
  { id: 'backlog',     label: 'Backlog',   icon: '◈' },
  { id: 'roadmap',     label: 'Roadmap',   icon: '⊞' },
  { id: 'cycles',      label: 'Cycles',    icon: '↺' },
  { id: 'decompose',   label: 'Decompose', icon: '⊛' },
  { id: 'skills',      label: 'Skills',    icon: '✦' },
  { id: 'models',      label: 'Models',    icon: '⬡' },
  { id: 'suggestions', label: 'Suggest',   icon: '⊕' },
  { id: 'memory',      label: 'Memory',    icon: '◉' },
  { id: 'metrics',     label: 'Metrics',   icon: '≡' },
  { id: 'history',     label: 'History',   icon: '⊚' },
  { id: 'safety',      label: 'Safety',    icon: '⊘' },
]

export function ForgeSystemsNav({ activeSection, onSection, suggestionCount, backlogCount }) {
  return (
    <div className="af-forge-nav">
      {FORGE_SECTIONS.map(s => (
        <button
          key={s.id}
          className={`af-forge-nav__pill${activeSection === s.id ? ' af-forge-nav__pill--active' : ''}`}
          onClick={() => onSection(activeSection === s.id ? null : s.id)}
          title={s.label}
        >
          <span className="af-forge-nav__icon">{s.icon}</span>
          <span className="af-forge-nav__label">{s.label}</span>
          {s.id === 'suggestions' && suggestionCount > 0 && (
            <span className="af-forge-nav__badge">{suggestionCount}</span>
          )}
          {s.id === 'backlog' && backlogCount > 0 && (
            <span className="af-forge-nav__badge af-forge-nav__badge--bronze">{backlogCount}</span>
          )}
        </button>
      ))}
    </div>
  )
}

// ── ForgeSectionView — full-workspace panel router ────────────────────────────
export function ForgeSectionView({ section, project, activeRun, onApprove, onReject, onContinue, onRefreshSummary }) {
  const map = {
    backlog:     <BacklogPane project={project} onRefreshSummary={onRefreshSummary} />,
    roadmap:     <RoadmapPane project={project} />,
    cycles:      <CyclesPane project={project} />,
    decompose:   <DecomposerPane project={project} onRefreshSummary={onRefreshSummary} />,
    skills:      <SkillsLibraryPane project={project} />,
    models:      <ModelRouterPane project={project} />,
    suggestions: <SuggestionsPane project={project} onRefreshSummary={onRefreshSummary} />,
    memory:      <MemoryV3Pane project={project} />,
    metrics:     <RunMetricsPane project={project} />,
    history:     <RunHistoryPane project={project} />,
    safety:      <SafetyPane project={project} activeRun={activeRun} onApprove={onApprove} onReject={onReject} onContinue={onContinue} />,
  }
  const content = map[section]
  if (!content) return null
  return <div className="af-section-view">{content}</div>
}

// ── LeftRail ─────────────────────────────────────────────────────────────────
const RAIL_VIEWS = [
  { id: 'compose',   icon: 'compose',   label: 'Compose' },
  { id: 'activity',  icon: 'activity',  label: 'Activity' },
  { id: 'review',    icon: 'diff',      label: 'Review' },
  { id: 'approvals', icon: 'check',     label: 'Approvals' },
  { id: 'pipeline',  icon: 'pipeline',  label: 'Pipeline' },
  { id: 'files',     icon: 'files',     label: 'Files' },
  { id: 'history',   icon: 'history',   label: 'History' },
  { id: 'agents',    icon: 'agents',    label: 'Agents' },
]

export function LeftRail({ active, onChange, pendingCount }) {
  return (
    <nav className="af-rail">
      {RAIL_VIEWS.map((v, i) => (
        <button
          key={v.id}
          className={`af-rail__item ${active === v.id ? 'af-rail__item--active' : ''}`}
          onClick={() => onChange(v.id)}
          title={v.label}
        >
          <Icon name={v.icon} size={16} />
          {v.id === 'approvals' && pendingCount > 0 && (
            <span className="af-rail__badge">{pendingCount}</span>
          )}
          <span className="af-rail__tip">{v.label} <span style={{ marginLeft: 6, opacity: 0.5, fontSize: 8 }}>{i + 1}</span></span>
        </button>
      ))}
      <div style={{ flex: 1 }} />
      <button className="af-rail__item" title="Help" style={{ font: '600 13px monospace' }}>?</button>
    </nav>
  )
}

// ── ForgeTopBar ──────────────────────────────────────────────────────────────
export function ForgeTopBar({ project, provider, onProviderChange, runState, onToggleRun, actions, suggestions }) {
  const pendingCount = actions.filter(a => {
    const s = (a.status || '').toLowerCase()
    return s === 'pending' || s === 'awaiting_approval'
  }).length
  const suggestionCount = Array.isArray(suggestions) ? suggestions.length : 0

  return (
    <header className="af-topbar">
      {/* Brand */}
      <div className="af-topbar__brand">
        <div className="af-topbar__mark">◆</div>
        <div>
          <div className="af-topbar__name">ASCEND FORGE</div>
          <div className="af-topbar__sub">Agentic Build Surface</div>
        </div>
      </div>

      <div className="af-topbar__divider" />

      {/* Project */}
      {project && (
        <div className="af-flex" style={{ gap: 8 }}>
          <span style={{ font: '500 9px monospace', letterSpacing: '0.18em', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>PROJECT</span>
          <div className="af-flex" style={{
            gap: 6, padding: '4px 10px',
            background: 'rgba(205,127,50,0.06)', border: '1px solid rgba(205,127,50,0.18)',
            borderRadius: 4,
          }}>
            <Icon name="branch" size={11} />
            <span style={{ font: '600 11.5px Inter, sans-serif', color: 'var(--af-text)', letterSpacing: '0.04em' }}>{project.name}</span>
          </div>
        </div>
      )}

      {/* Search pill */}
      <div className="af-topbar__search">
        <Icon name="search" size={12} />
        <span style={{ flex: 1 }}>Ask · build · search code…</span>
        <span className="af-topbar__search-kbd">⌘K</span>
      </div>

      {/* Live status */}
      <div className="af-topbar__kpis">
        {pendingCount > 0 && (
          <>
            <div className="af-topbar__kpi">
              <div className="af-topbar__kpi-label">Pending</div>
              <div className="af-topbar__kpi-value" style={{ color: 'var(--af-amber)' }}>{pendingCount}</div>
            </div>
            <div className="af-topbar__divider" />
          </>
        )}
        {suggestionCount > 0 && (
          <>
            <div className="af-topbar__kpi" title="Open self-improvement suggestions">
              <div className="af-topbar__kpi-label">Suggestions</div>
              <div className="af-topbar__kpi-value" style={{ color: 'var(--af-teal, #2dd4bf)' }}>{suggestionCount}</div>
            </div>
            <div className="af-topbar__divider" />
          </>
        )}
      </div>

      {/* Controls */}
      <div className="af-topbar__controls">
        <div className={`af-pill ${runState === 'running' ? 'af-pill--success' : runState === 'paused' ? 'af-pill--warn' : 'af-pill--idle'}`}
          style={{ cursor: 'default' }}>
          <span className="af-pill__dot" style={{ animation: runState === 'running' ? undefined : 'none' }} />
          {runState === 'running' ? 'LIVE' : runState === 'paused' ? 'PAUSED' : 'IDLE'}
        </div>
        <button className="af-iconbtn" onClick={onToggleRun} title={runState === 'running' ? 'Pause' : 'Resume'}>
          <Icon name={runState === 'running' ? 'pause' : 'play'} size={13} />
        </button>
        <select className="af-select" value={provider} onChange={e => onProviderChange(e.target.value)} style={{ fontSize: 11 }}>
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
          <option value="ollama">Ollama</option>
        </select>
        <button className="af-iconbtn" title="Notifications"><Icon name="bell" size={14} /></button>
        <button className="af-iconbtn" title="Settings"><Icon name="settings" size={14} /></button>
        <div className="af-topbar__operator">
          <div className="af-topbar__avatar">OP</div>
          <div>
            <div style={{ font: '600 10.5px Inter, sans-serif', color: 'var(--af-text)', lineHeight: 1 }}>Operator</div>
            <div style={{ font: '500 8.5px monospace', color: 'var(--af-text-dim)', marginTop: 2, letterSpacing: '0.08em' }}>ADMIN</div>
          </div>
        </div>
      </div>
    </header>
  )
}

// ── ForgeFooter ──────────────────────────────────────────────────────────────
export function ForgeFooter({ runState, activeRun }) {
  return (
    <footer className="af-footer">
      <div className="af-flex" style={{ gap: 12 }}>
        <span className="af-flex" style={{ gap: 6 }}>
          <span className="af-footer__dot" style={{
            background: runState === 'running' ? 'var(--af-green)' : 'var(--af-amber)',
            boxShadow: `0 0 8px ${runState === 'running' ? 'rgba(34,197,94,0.6)' : 'rgba(245,158,11,0.6)'}`,
          }} />
          <span style={{ color: runState === 'running' ? 'var(--af-green)' : 'var(--af-amber)' }}>
            {runState === 'running' ? 'FORGE ACTIVE' : 'IDLE'}
          </span>
        </span>
        {activeRun?.id && (
          <>
            <span style={{ color: 'var(--af-text-dim)' }}>·</span>
            <span>RUN <span style={{ color: 'var(--af-text-muted)' }}>{activeRun.id.slice(-8)}</span></span>
            <span style={{ color: 'var(--af-text-dim)' }}>·</span>
            <span style={{ color: String(activeRun.status || '').includes('fail') ? 'var(--af-red)' : 'var(--af-bronze-bright)' }}>
              {String(activeRun.status || 'pending').toUpperCase()}
            </span>
          </>
        )}
      </div>
      <div style={{ flex: 1 }} />
      <span style={{ color: 'var(--af-text-dim)' }}>ASCEND FORGE v2 · AI Operating System</span>
    </footer>
  )
}

// ── TEMPLATES ────────────────────────────────────────────────────────────────
const QUICK_TEMPLATES = [
  { icon: 'spark',    label: 'New feature',    sub: 'Plan → scaffold → test',      prompt: 'Add a new feature: [describe the feature here]. Include unit tests and documentation.' },
  { icon: 'zap',      label: 'Bug hunt',       sub: 'Repro → root cause → fix',    prompt: 'Find and fix the bug causing [describe the issue]. Add a regression test to prevent recurrence.' },
  { icon: 'branch',   label: 'Refactor',       sub: 'Map blast radius first',       prompt: 'Refactor [describe the code area] to improve readability, maintainability, and performance without changing behavior.' },
  { icon: 'pipeline', label: 'Migration',      sub: 'Schema + data + rollback',     prompt: 'Migrate [from X] to [Y] with a full rollback plan and data integrity validation checks.' },
  { icon: 'send',     label: 'API endpoint',   sub: 'Auth + validation + docs',     prompt: 'Create a REST API endpoint for [describe the resource] with authentication, input validation, error handling, and OpenAPI documentation.' },
  { icon: 'agents',   label: 'AI Agent',       sub: 'Capability + approval gate',   prompt: 'Build a new autonomous agent that can [describe the capability]. Include approval gating for consequential actions and proper logging.' },
  { icon: 'files',    label: 'Landing page',   sub: 'Dark theme + responsive',      prompt: 'Build a responsive landing page for [describe the product/service] with a dark theme, hero section, features, and CTA.' },
  { icon: 'compose',  label: 'Database',       sub: 'Schema + migrations',          prompt: 'Design and implement a database schema for [describe the domain], including migrations, indexes, and seed data.' },
]

// ── ForgeOnboarding — shown when no project is selected ──────────────────────
function ForgeOnboarding({ onNew, onBrowse }) {
  return (
    <div className="af-onboarding">
      <div className="af-onboarding__mark">◆</div>
      <h2 className="af-onboarding__title">Start building with AscendForge</h2>
      <p className="af-onboarding__sub">
        Select or create a project, then describe what you want to build.
        AscendForge will plan, write code, and run tests — all with your approval.
      </p>
      <div className="af-onboarding__actions">
        <button className="af-btn af-btn--primary af-btn--lg" onClick={onNew}>+ Create Project</button>
        <button className="af-btn af-btn--ghost af-btn--lg" onClick={onBrowse}>Open Existing</button>
      </div>
      <div className="af-onboarding__hint">Or type a goal below — we'll create a Workspace project automatically.</div>
    </div>
  )
}

// ── Phase5StatusCard — sidebar card surfacing P5 features ────────────────────
function Phase5StatusCard({ project, backlogCount, autopilot, suggestions, onNavigate, onRefreshSummary }) {
  const [apBusy, setApBusy] = useState(false)

  const isWaitingApproval = !autopilot?.active && autopilot?.consecutiveFails === 0 && autopilot?.runsCompleted > 0 && autopilot?.current_run?.status === 'waiting_approval'

  const handleAutopilot = async () => {
    if (!project?.id) return
    setApBusy(true)
    try {
      if (autopilot?.active) {
        await api.forge.stopAutopilot(project.id)
      } else if (isWaitingApproval) {
        await api.forge.resumeAutopilot(project.id)
      } else {
        await api.forge.startAutopilot(project.id, {})
      }
      onRefreshSummary?.()
    } catch { /* summary refreshes on next poll */ }
    finally { setApBusy(false) }
  }

  const currentRun = autopilot?.current_run
  const apLabel = autopilot?.active ? 'RUNNING' : isWaitingApproval ? 'PAUSED' : 'IDLE'
  const apColor = autopilot?.active ? 'var(--af-green)' : isWaitingApproval ? '#f59e0b' : 'var(--af-text-dim)'
  const apBtnLabel = apBusy ? '...' : autopilot?.active ? 'Stop' : isWaitingApproval ? 'Resume' : 'Start'
  const apBtnClass = autopilot?.active ? 'af-btn--danger' : isWaitingApproval ? 'af-btn--primary' : 'af-btn--ghost'

  const rows = [
    { label: 'Backlog', value: `${backlogCount} active`, tab: 'backlog', accent: backlogCount > 0 ? 'var(--af-bronze-bright)' : 'var(--af-text-dim)' },
    { label: 'Cycles', value: 'manage', tab: 'cycles', accent: 'var(--af-text-muted)' },
    { label: 'Roadmap', value: 'view', tab: 'roadmap', accent: 'var(--af-text-muted)' },
    { label: 'Decompose', value: 'plan task', tab: 'decompose', accent: 'var(--af-text-muted)' },
    { label: 'Skills', value: 'library', tab: 'skills', accent: 'var(--af-text-muted)' },
    { label: 'Models', value: 'router', tab: 'models', accent: 'var(--af-text-muted)' },
    { label: 'Suggestions', value: suggestions?.length > 0 ? `${suggestions.length} open` : 'none', tab: 'suggestions', accent: suggestions?.length > 0 ? 'var(--af-teal,#2dd4bf)' : 'var(--af-text-dim)' },
    { label: 'Metrics', value: 'stats', tab: 'metrics', accent: 'var(--af-text-muted)' },
    { label: 'History', value: 'runs', tab: 'runhistory', accent: 'var(--af-text-muted)' },
  ]

  return (
    <ForgePanel title="Intelligence" sub="phase 6">
      <div style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 0 }}>
        {/* Autopilot row */}
        <div className="af-p5-row" style={{ paddingBottom: 8, marginBottom: 6, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <span style={{ font: '500 10px monospace', color: 'var(--af-text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Autopilot</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ font: '600 10px monospace', color: apColor }}>{apLabel}</span>
            <button
              className={`af-btn af-btn--sm ${apBtnClass}`}
              style={{ fontSize: 9, padding: '2px 7px' }}
              onClick={handleAutopilot}
              disabled={apBusy || !project}
            >
              {apBtnLabel}
            </button>
          </div>
        </div>
        {/* Current run status when autopilot is active */}
        {currentRun && (
          <div style={{ marginBottom: 6, padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <div style={{ font: '400 9.5px monospace', color: 'var(--af-text-dim)', marginBottom: 2 }}>
              {autopilot?.runsCompleted || 0}/{autopilot?.maxRuns || 10} runs · {autopilot?.consecutiveFails || 0} fails
            </div>
            <div style={{ font: '400 10px monospace', color: 'var(--af-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {currentRun.status?.toUpperCase()} · {(currentRun.goal || '').slice(0, 40)}
            </div>
          </div>
        )}
        {/* Navigation links */}
        {rows.map(r => (
          <button key={r.tab} className="af-p5-link" onClick={() => onNavigate(r.tab)}>
            <span style={{ font: '400 10.5px Inter, sans-serif', color: 'var(--af-text-muted)' }}>{r.label}</span>
            <span style={{ font: '500 10px monospace', color: r.accent }}>{r.value}</span>
          </button>
        ))}
      </div>
    </ForgePanel>
  )
}

// ── ComposeView ──────────────────────────────────────────────────────────────
export function ComposeView({ project, messages, sending, onSend, selectedSkillIds, onSkillChange, tab, setTab, showTools, setShowTools, onNewProject, onSelectProject, draftGoal, setDraftGoal, onTemplateSelect, backlogCount, autopilot, suggestions, onSection, onRefreshSummary }) {
  const handleTemplateClick = (t) => {
    setDraftGoal?.(t.prompt)
    setTab('chat')
    onTemplateSelect?.(t.prompt)
  }

  return (
    <div className={`af-compose ${project ? '' : 'af-compose--no-project'}`}>
      <div className="af-compose__main">
        <ForgePanel title="Goal" sub={project ? project.name : 'no project'} actions={
          <button className="af-btn af-btn--ghost af-btn--sm"><Icon name="more" size={12} /> Saved prompts</button>
        }>
          <div style={{ padding: '12px 14px' }}>
            {!project && <ForgeOnboarding onNew={onNewProject} onBrowse={() => setTab('projects')} />}

            <div className="af-pane__tabs" style={{ marginBottom: 10, background: 'transparent', border: 'none' }}>
              {[['chat', 'Chat'], ['tree', 'Files'], ['projects', 'Projects']].map(([id, label]) => (
                <button key={id} className={`af-tab ${tab === id ? 'af-tab--active' : ''}`} onClick={() => setTab(id)}>{label}</button>
              ))}
              <div className="af-tab-extras">
                <button className="af-tab-extras__btn" onClick={() => setShowTools(p => !p)}>⋯</button>
                {showTools && (
                  <div className="af-tab-extras__dropdown">
                    {[['understand','Understand'],['autobuild','Auto-build'],['runhistory','Run History'],['metrics','Metrics'],['backlog','Backlog'],['decompose','Decompose'],['skills','Skills'],['models','Models'],['cycles','Cycles'],['roadmap','Roadmap'],['suggestions','Suggestions']].map(([id, label]) => (
                      <button key={id} className={`af-tab-extras__item ${tab === id ? 'af-tab-extras__item--active' : ''}`}
                        onClick={() => { setTab(id); setShowTools(false) }}>{label}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {tab === 'chat' && <ChatPane project={project} messages={messages} onSend={onSend} sending={sending} selectedSkillIds={selectedSkillIds} onSkillChange={onSkillChange} draftGoal={draftGoal} setDraftGoal={setDraftGoal} />}
            {tab === 'tree' && <FileTree project={project} selectedFile={null} onSelect={() => {}} />}
            {tab === 'understand' && <UnderstandPane project={project} />}
            {tab === 'autobuild' && <AgenticPane project={project} />}
            {tab === 'runhistory' && <RunHistoryPane project={project} />}
            {tab === 'metrics' && <RunMetricsPane project={project} />}
            {tab === 'backlog' && <BacklogPane project={project} />}
            {tab === 'decompose' && <DecomposerPane project={project} />}
            {tab === 'skills' && <SkillsLibraryPane project={project} />}
            {tab === 'models' && <ModelRouterPane project={project} />}
            {tab === 'cycles' && <CyclesPane project={project} />}
            {tab === 'roadmap' && <RoadmapPane project={project} />}
            {tab === 'suggestions' && <SuggestionsPane project={project} />}
            {tab === 'projects' && <ProjectPicker project={project} onSelect={p => { onSelectProject?.(p); setTab('chat') }} onNew={() => onNewProject?.()} />}
          </div>
        </ForgePanel>

        {/* Template shortcuts — 8 in 2-col grid */}
        <ForgePanel title="Quick start" sub="8 templates">
          <div style={{ padding: '12px 14px' }}>
            <div className="af-template-grid">
              {QUICK_TEMPLATES.map(t => (
                <button key={t.label} className="af-template-card" onClick={() => handleTemplateClick(t)}>
                  <div className="af-hex af-hex--sm" style={{ background: 'rgba(205,127,50,0.10)', color: 'var(--af-bronze-bright)', border: '1px solid rgba(205,127,50,0.28)' }}>
                    <Icon name={t.icon} size={12} />
                  </div>
                  <div style={{ font: '600 11.5px Inter, sans-serif', color: 'var(--af-text)' }}>{t.label}</div>
                  <div style={{ font: '500 10px monospace', color: 'var(--af-text-dim)' }}>{t.sub}</div>
                </button>
              ))}
            </div>
          </div>
        </ForgePanel>
      </div>

      {project && (
        <div className="af-compose__sidebar">
          <ForgePanel title="Project" sub={project.name} actions={
            <button className="af-btn af-btn--ghost af-btn--sm" onClick={() => setTab('projects')}>Change</button>
          }>
            <div style={{ padding: '10px 12px' }}>
              <div className="af-flex" style={{ gap: 8, marginBottom: 6 }}>
                <Icon name="branch" size={11} />
                <span style={{ font: '600 11px monospace', color: 'var(--af-text)' }}>{project.name}</span>
              </div>
              {project.path && (
                <div style={{ font: '400 10px monospace', color: 'var(--af-text-dim)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project.path}</div>
              )}
              {project.description && (
                <div style={{ font: '400 11px/1.5 Inter, sans-serif', color: 'var(--af-text-muted)', marginTop: 6 }}>{project.description}</div>
              )}
            </div>
          </ForgePanel>

          <ForgePanel title="Skill packs" sub="active">
            <div style={{ padding: '10px 12px' }}>
              {selectedSkillIds.length === 0 ? (
                <div style={{ color: 'var(--af-text-dim)', fontSize: 11 }}>No skills selected — they'll be auto-recommended when you send a goal.</div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                  {selectedSkillIds.map(id => (
                    <span key={id} style={{ padding: '2px 8px', background: 'rgba(205,127,50,0.10)', border: '1px solid rgba(205,127,50,0.22)', borderRadius: 4, font: '500 10px monospace', color: 'var(--af-bronze-bright)' }}>{id}</span>
                  ))}
                </div>
              )}
            </div>
          </ForgePanel>

          <Phase5StatusCard
            project={project}
            backlogCount={backlogCount || 0}
            autopilot={autopilot || { active: false }}
            suggestions={suggestions || []}
            onNavigate={onSection || (t => setTab(t))}
            onRefreshSummary={onRefreshSummary}
          />
          <ForgePanel title="Hotkeys" sub="cheat sheet">
            <div style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 5 }}>
              {[['↵', 'Send goal'], ['⌘↵', 'Send goal'], ['1–8', 'Switch view'], ['A', 'Approve action'], ['X', 'Reject action']].map(([k, d]) => (
                <div key={k} className="af-flex" style={{ justifyContent: 'space-between' }}>
                  <span style={{ font: '400 10.5px Inter, sans-serif', color: 'var(--af-text-muted)' }}>{d}</span>
                  <span style={{ padding: '1px 6px', background: 'rgba(205,127,50,0.08)', border: '1px solid rgba(205,127,50,0.18)', borderRadius: 3, font: '600 9px monospace', color: 'var(--af-bronze-bright)' }}>{k}</span>
                </div>
              ))}
            </div>
          </ForgePanel>
        </div>
      )}
    </div>
  )
}

// ── ActivityView ─────────────────────────────────────────────────────────────
const PIPELINE_STAGES = [
  { id: 'context',  label: 'Context',  icon: '◎' },
  { id: 'plan',     label: 'Plan',     icon: '⊞' },
  { id: 'build',    label: 'Build',    icon: '⌘' },
  { id: 'test',     label: 'Test',     icon: '✓' },
  { id: 'review',   label: 'Review',   icon: '⊡' },
  { id: 'approval', label: 'Approval', icon: '◆' },
  { id: 'done',     label: 'Done',     icon: '●' },
]

function RunStepper({ activeRun }) {
  if (!activeRun) {
    return (
      <div style={{ padding: '20px 12px', color: 'var(--af-text-dim)', fontSize: 11, textAlign: 'center' }}>
        <div style={{ fontSize: 20, marginBottom: 8, opacity: 0.3 }}>◆</div>
        No active run — send a goal to start
      </div>
    )
  }
  const statusToStage = {
    new: 'context', awaiting_approval: 'approval', pending_approval: 'approval',
    staged: 'review', verified: 'test', applied: 'done', blocked: 'approval',
    verify_failed: 'test', failed: 'build',
  }
  const currentStageId = statusToStage[activeRun.status] || 'plan'
  const currentIdx = PIPELINE_STAGES.findIndex(s => s.id === currentStageId)

  return (
    <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 0 }}>
      <div style={{ font: '500 9px monospace', letterSpacing: '0.15em', color: 'var(--af-text-dim)', textTransform: 'uppercase', marginBottom: 12 }}>Run progress</div>
      {PIPELINE_STAGES.map((s, i) => {
        const done = i < currentIdx
        const active = i === currentIdx
        const pending = i > currentIdx
        const color = done ? 'var(--af-green)' : active ? 'var(--af-bronze-bright)' : 'var(--af-text-dim)'
        return (
          <div key={s.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20 }}>
              <div style={{
                width: 20, height: 20, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: done ? 'rgba(34,197,94,0.15)' : active ? 'rgba(205,127,50,0.15)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${done ? 'rgba(34,197,94,0.5)' : active ? 'rgba(205,127,50,0.5)' : 'rgba(255,255,255,0.08)'}`,
                boxShadow: active ? '0 0 8px rgba(205,127,50,0.3)' : 'none',
                font: '600 9px monospace', color,
              }}>
                {done ? '✓' : s.icon}
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <div style={{ width: 1, height: 18, background: done ? 'rgba(34,197,94,0.3)' : 'rgba(255,255,255,0.06)', marginTop: 2 }} />
              )}
            </div>
            <div style={{ paddingBottom: 12 }}>
              <div style={{ font: `${active ? '700' : '500'} 11px Inter, sans-serif`, color, lineHeight: 1.2 }}>{s.label}</div>
              {active && (
                <div style={{ font: '400 9.5px monospace', color: 'var(--af-text-dim)', marginTop: 2 }}>
                  {activeRun.status?.toUpperCase()}
                </div>
              )}
            </div>
          </div>
        )
      })}
      {activeRun.ui_error && (
        <div style={{ marginTop: 8, padding: '6px 10px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 5, font: '400 10px monospace', color: 'var(--af-red)' }}>
          {activeRun.ui_error}
        </div>
      )}
    </div>
  )
}

// ── Phase5RunIntelPanel — shows P5 intelligence from active run ───────────────
function Phase5RunIntelPanel({ activeRun, onNavTab }) {
  if (!activeRun) return null
  const report = activeRun.final_report || {}
  const regression = report.regression_comparison
  const skillsUsed = activeRun.applied_skill ? [activeRun.applied_skill] : (report.skills_used || [])
  const modelLog = activeRun.model_routing_log || []
  const memUsed = report.memory_used
  const backlogId = activeRun.linked_backlog_id

  const hasAny = skillsUsed.length || modelLog.length || regression || memUsed || backlogId
  if (!hasAny) return null

  return (
    <div className="af-run-intel">
      <div className="af-run-intel__title">Run Intelligence</div>
      {backlogId && (
        <div className="af-run-intel__row">
          <span className="af-run-intel__label">Backlog</span>
          <button className="af-p5-link" style={{ display: 'inline-flex' }} onClick={() => onNavTab?.('backlog')}>
            {backlogId.slice(-8)} →
          </button>
        </div>
      )}
      {skillsUsed.length > 0 && (
        <div className="af-run-intel__row">
          <span className="af-run-intel__label">Skills</span>
          <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {skillsUsed.map(s => (
              <span key={s} style={{ padding: '1px 6px', background: 'rgba(205,127,50,0.10)', border: '1px solid rgba(205,127,50,0.2)', borderRadius: 3, font: '500 9px monospace', color: 'var(--af-bronze-bright)' }}>{s}</span>
            ))}
          </span>
        </div>
      )}
      {modelLog.length > 0 && (
        <div className="af-run-intel__row">
          <span className="af-run-intel__label">Models</span>
          <span style={{ font: '400 10px monospace', color: 'var(--af-text-muted)' }}>
            {[...new Set(modelLog.map(l => l.selected_model_id).filter(Boolean))].join(', ')}
          </span>
        </div>
      )}
      {memUsed != null && (
        <div className="af-run-intel__row">
          <span className="af-run-intel__label">Memory</span>
          <span style={{ font: '500 10px monospace', color: 'var(--af-text-muted)' }}>{memUsed} facts used</span>
        </div>
      )}
      {regression && (
        <div className="af-run-intel__row">
          <span className="af-run-intel__label">Regression</span>
          <span style={{ display: 'flex', gap: 8, font: '500 10px monospace' }}>
            {regression.fixed?.length > 0 && <span style={{ color: 'var(--af-green)' }}>+{regression.fixed.length} fixed</span>}
            {regression.newly_broken?.length > 0 && <span style={{ color: 'var(--af-red)' }}>-{regression.newly_broken.length} broken</span>}
            {!regression.fixed?.length && !regression.newly_broken?.length && <span style={{ color: 'var(--af-text-dim)' }}>no change</span>}
          </span>
        </div>
      )}
    </div>
  )
}

export function ActivityView({ termLines, activeRun, onNavTab }) {
  const logRef = useRef(null)
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [termLines])

  return (
    <div className="af-activity">
      <div className="af-activity__left">
        <ForgePanel title="Live activity" sub={`${termLines.length} events`} style={{ flex: 1 }} bodyStyle={{ padding: 0 }}>
          <div ref={logRef} className="af-log">
            {termLines.map((line, i) => {
              const isNew = i === termLines.length - 1
              const tone = line.type === 'err' ? 'danger' : line.type === 'warn' ? 'warn' : line.type === 'cmd' ? 'success' : ''
              return (
                <div key={i} className={`af-log__line ${isNew ? 'af-log__line--new' : ''} ${tone ? `af-log__line--${tone}` : ''}`}>
                  <span className="af-log__time">{new Date(line.ts || Date.now()).toLocaleTimeString('en', { hour12: false }).slice(0, 8)}</span>
                  <span className={`af-log__agent af-log__agent--${line.type === 'cmd' ? 'planner' : line.type === 'err' ? 'security' : 'coder'}`}>
                    {line.type === 'cmd' ? 'SYSTEM' : line.type === 'err' ? 'ERROR' : 'OUTPUT'}
                  </span>
                  <span className="af-log__msg">{line.text}</span>
                </div>
              )
            })}
            {termLines.length === 0 && (
              <div style={{ color: 'var(--af-text-dim)', fontSize: 11, padding: '16px 0' }}>
                No activity yet — send a goal to start
              </div>
            )}
            <div className="af-log__line">
              <span className="af-log__time">—</span>
              <span className="af-log__agent af-log__agent--coder">FORGE</span>
              <span className="af-log__msg" style={{ color: 'var(--af-bronze-bright)' }}>
                Ready<span className="af-caret" />
              </span>
            </div>
          </div>
        </ForgePanel>
        <Phase5RunIntelPanel activeRun={activeRun} onNavTab={onNavTab} />
      </div>

      <div className="af-activity__right">
        <ForgePanel title="Run stages" sub="progress" style={{ flex: 1 }} bodyStyle={{ padding: 0 }}>
          <RunStepper activeRun={activeRun} />
        </ForgePanel>
      </div>
    </div>
  )
}

// ── ReviewView ────────────────────────────────────────────────────────────────
export function ReviewView({ currentDiff, project, selectedFile, onSelectFile, fileViewTab, setFileViewTab, editorFile }) {
  return (
    <div className="af-review">
      <ForgePanel title="Files changed" bodyStyle={{ padding: 0 }}>
        <FileTree project={project} selectedFile={selectedFile} onSelect={onSelectFile} />
      </ForgePanel>

      <ForgePanel
        title={selectedFile ? selectedFile.path || selectedFile : 'Diff viewer'}
        sub="patch"
        actions={
          <div className="af-file-view-tabs">
            <button className={`af-file-view-tab ${fileViewTab === 'diff' ? 'af-file-view-tab--active' : ''}`}
              onClick={() => setFileViewTab('diff')}>DIFF</button>
            <button className={`af-file-view-tab ${fileViewTab === 'editor' ? 'af-file-view-tab--active' : ''}`}
              onClick={() => setFileViewTab('editor')}>EDITOR</button>
          </div>
        }
        bodyStyle={{ padding: 0 }}
      >
        {fileViewTab === 'diff'
          ? <DiffViewer diff={currentDiff} />
          : <FileEditor project={project} selectedFile={editorFile} />
        }
      </ForgePanel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
        <ForgePanel title="Reviewer notes" sub="automated">
          <div style={{ padding: '10px 12px', color: 'var(--af-text-muted)', fontSize: 12, lineHeight: 1.6 }}>
            {currentDiff ? 'Diff loaded. Use Approve/Reject buttons in the Approvals view.' : 'No diff available yet — run a Forge goal first.'}
          </div>
        </ForgePanel>
      </div>
    </div>
  )
}

// ── ApprovalsView ─────────────────────────────────────────────────────────────
export function ApprovalsView({ actions, busyActions, onApprove, onReject, onApproveSafeBatch, expandedActions, onToggleExpand, activeRun, onVerify, onApply, runBusy, onQueueItems }) {
  const [filter, setFilter] = useState('all')
  const counts = {
    all: actions.length,
    safe: actions.filter(a => (a.risk_level || a.risk || '').toLowerCase() === 'low').length,
    review: actions.filter(a => ['medium', 'review'].includes((a.risk_level || a.risk || '').toLowerCase())).length,
    gated: actions.filter(a => ['high', 'gated', 'critical'].includes((a.risk_level || a.risk || '').toLowerCase())).length,
  }

  const filtered = filter === 'all' ? actions
    : filter === 'safe' ? actions.filter(a => (a.risk_level || a.risk || '').toLowerCase() === 'low')
    : filter === 'review' ? actions.filter(a => ['medium', 'review'].includes((a.risk_level || a.risk || '').toLowerCase()))
    : actions.filter(a => ['high', 'gated', 'critical'].includes((a.risk_level || a.risk || '').toLowerCase()))

  return (
    <div className="af-approvals">
      <ForgePanel
        title="Approval queue"
        sub={`${actions.length} pending`}
        actions={
          <div className="af-tabs">
            {[['all', 'All'], ['safe', 'Safe'], ['review', 'Review'], ['gated', 'Gated']].map(([id, lbl]) => (
              <button key={id} className={`af-tab ${filter === id ? 'af-tab--active' : ''}`}
                onClick={() => setFilter(id)} style={{ padding: '5px 10px' }}>
                {lbl}<span className="af-tab__count">{counts[id]}</span>
              </button>
            ))}
          </div>
        }
        bodyStyle={{ padding: 0 }}
      >
        <RunTimeline run={activeRun} onVerify={onVerify} onApply={onApply} busy={runBusy} />
        <ActionQueue
          actions={filtered}
          busyActions={busyActions}
          onApprove={onApprove}
          onReject={onReject}
          onApproveSafeBatch={onApproveSafeBatch}
          expandedActions={expandedActions}
          onToggleExpand={onToggleExpand}
        />
      </ForgePanel>

      <div className="af-approvals__sidebar">
        <PolicyPreview actions={actions} />
        {onQueueItems && <ForgeSystemPanel onQueueItems={onQueueItems} />}
        <ForgePanel title="Run status" sub="live">
          {activeRun ? (
            <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                ['ID', activeRun.id?.slice(-12) || '—'],
                ['Status', activeRun.status || 'pending'],
                ['Actions', actions.length],
              ].map(([k, v]) => (
                <div key={k} className="af-flex" style={{ justifyContent: 'space-between' }}>
                  <span style={{ font: '500 10px monospace', letterSpacing: '0.10em', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>{k}</span>
                  <span style={{ font: '500 11.5px monospace', color: 'var(--af-text)' }}>{String(v)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: '12px', color: 'var(--af-text-dim)', fontSize: 11 }}>No active run</div>
          )}
        </ForgePanel>
      </div>
    </div>
  )
}

// ── PipelineView ─────────────────────────────────────────────────────────────
function DagNode({ node, x, y }) {
  const statusClass = {
    done: 'af-dag-node--done',
    running: 'af-dag-node--running',
    pending: 'af-dag-node--pending',
    failed: 'af-dag-node--failed',
  }[node.status] || 'af-dag-node--pending'

  const toneColor = node.status === 'done' ? 'var(--af-green)' : node.status === 'running' ? 'var(--af-bronze-bright)' : node.status === 'failed' ? 'var(--af-red)' : 'var(--af-text-dim)'

  return (
    <div className={`af-dag-node ${statusClass}`} style={{ left: x, top: y }}>
      <div style={{ font: '600 10.5px Inter, sans-serif', color: toneColor, letterSpacing: '0.04em' }}>{node.label}</div>
      {node.agent && <div style={{ font: '500 9px monospace', color: 'var(--af-text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{node.agent}</div>}
      {node.prog !== undefined && (
        <div className="af-progress" style={{ height: 2, marginTop: 4 }}>
          <div className="af-progress__fill" style={{ width: `${node.prog * 100}%`, background: 'var(--af-grad-bronze)' }} />
        </div>
      )}
      {node.dur && node.dur !== '—' && <div style={{ font: '500 9.5px monospace', color: 'var(--af-text-dim)', marginTop: 2 }}>{node.dur}</div>}
    </div>
  )
}

export function PipelineView({ activeRun, actions }) {
  const nodes = []
  const stageCols = { plan: 0, scaffold: 1, build: 2, test: 2, security: 2, review: 3, approval: 4, deploy: 5 }
  const stageRows = { plan: 1, scaffold: 1, build: 1, test: 2, security: 3, review: 2, approval: 2, deploy: 2 }

  const STAGES = [
    { id: 'plan', label: 'Plan', agent: 'planner', status: 'done' },
    { id: 'scaffold', label: 'Scaffold', agent: 'coder', status: actions.length > 0 ? 'done' : 'pending' },
    { id: 'build', label: 'Build', agent: 'coder', status: activeRun ? 'running' : 'pending', prog: activeRun ? 0.65 : 0 },
    { id: 'test', label: 'Tests', agent: 'tester', status: activeRun ? 'running' : 'pending', prog: activeRun ? 0.4 : 0 },
    { id: 'review', label: 'Review', agent: 'reviewer', status: 'pending' },
    { id: 'approval', label: 'Approval', agent: null, status: actions.length > 0 ? 'running' : 'pending' },
    { id: 'deploy', label: 'Deploy', agent: null, status: 'pending' },
  ]

  const COL_W = 210, ROW_H = 90, OFFSET_X = 30, OFFSET_Y = 20

  return (
    <div className="af-pipeline">
      <ForgePanel title="Execution pipeline" sub="DAG" bodyStyle={{ padding: 0, position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'relative', height: '100%', minHeight: 340 }}>
          <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
            <defs>
              <marker id="dag-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L0,6 L6,3 z" fill="rgba(205,127,50,0.4)" />
              </marker>
            </defs>
            {[
              ['plan', 'scaffold'], ['scaffold', 'build'], ['scaffold', 'test'],
              ['build', 'review'], ['test', 'review'], ['review', 'approval'], ['approval', 'deploy'],
            ].map(([from, to]) => {
              const s = STAGES.find(n => n.id === from), e = STAGES.find(n => n.id === to)
              if (!s || !e) return null
              const scol = stageCols[from] ?? 0, ecol = stageCols[to] ?? 1
              const srow = stageRows[from] ?? 1, erow = stageRows[to] ?? 1
              const x1 = OFFSET_X + scol * COL_W + 170
              const y1 = OFFSET_Y + (srow - 1) * ROW_H + 30
              const x2 = OFFSET_X + ecol * COL_W
              const y2 = OFFSET_Y + (erow - 1) * ROW_H + 30
              return (
                <line key={`${from}-${to}`} x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke={s.status === 'done' ? 'rgba(34,197,94,0.4)' : 'rgba(205,127,50,0.22)'}
                  strokeWidth="1.5" markerEnd="url(#dag-arrow)" strokeDasharray={e.status === 'pending' ? '4 3' : undefined} />
              )
            })}
          </svg>
          {STAGES.map(node => (
            <DagNode key={node.id} node={node}
              x={OFFSET_X + (stageCols[node.id] ?? 0) * COL_W}
              y={OFFSET_Y + ((stageRows[node.id] ?? 1) - 1) * ROW_H}
            />
          ))}
        </div>
      </ForgePanel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <ForgePanel title="Stage breakdown">
          <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {STAGES.map(s => (
              <div key={s.id}>
                <div className="af-flex" style={{ justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ font: '500 10.5px monospace', letterSpacing: '0.08em', color: s.status !== 'pending' ? 'var(--af-text)' : 'var(--af-text-dim)', textTransform: 'uppercase' }}>{s.label}</span>
                  <span style={{ font: '500 9.5px monospace', color: s.status === 'done' ? 'var(--af-green)' : s.status === 'running' ? 'var(--af-bronze-bright)' : 'var(--af-text-dim)' }}>
                    {s.status === 'done' ? 'DONE' : s.status === 'running' ? `${Math.round((s.prog || 0) * 100)}%` : '—'}
                  </span>
                </div>
                <div className="af-progress" style={{ height: 2 }}>
                  <div className="af-progress__fill" style={{
                    width: s.status === 'done' ? '100%' : `${(s.prog || 0) * 100}%`,
                    background: s.status === 'done' ? 'linear-gradient(90deg,var(--af-green),#4ADE80)' : 'var(--af-grad-bronze)',
                    boxShadow: s.status !== 'pending' ? '0 0 5px rgba(205,127,50,0.3)' : 'none',
                  }} />
                </div>
              </div>
            ))}
          </div>
        </ForgePanel>
      </div>
    </div>
  )
}

// ── FilesView ─────────────────────────────────────────────────────────────────
export function FilesView({ project, selectedFile, onSelectFile, currentDiff, fileViewTab, setFileViewTab, editorFile }) {
  return (
    <div className="af-files">
      <ForgePanel title="Project files" bodyStyle={{ padding: 0 }}>
        <FileTree project={project} selectedFile={selectedFile} onSelect={onSelectFile} />
      </ForgePanel>

      <ForgePanel
        title={selectedFile?.path || selectedFile || 'File viewer'}
        actions={
          <div className="af-file-view-tabs">
            <button className={`af-file-view-tab ${fileViewTab === 'diff' ? 'af-file-view-tab--active' : ''}`}
              onClick={() => setFileViewTab('diff')}>DIFF</button>
            <button className={`af-file-view-tab ${fileViewTab === 'editor' ? 'af-file-view-tab--active' : ''}`}
              onClick={() => setFileViewTab('editor')}>EDITOR</button>
          </div>
        }
        bodyStyle={{ padding: 0 }}
      >
        {fileViewTab === 'diff'
          ? <DiffViewer diff={currentDiff} />
          : <FileEditor project={project} selectedFile={editorFile} />
        }
      </ForgePanel>
    </div>
  )
}

// ── HistoryView ───────────────────────────────────────────────────────────────
export function HistoryView({ messages, activeRun, metrics }) {
  const runMessages = messages.filter(m => m.role === 'assistant' && m.run)
  return (
    <div className="af-history">
      <ForgePanel title="Run history" sub={`${runMessages.length} runs`} bodyStyle={{ padding: 0 }}>
      {metrics && (
        <div className="af-history__metrics-strip">
          <span><strong>{metrics.total_runs || 0}</strong> runs</span>
          <span className="af-history__metrics-sep">·</span>
          <span><strong>{Math.round((metrics.success_rate || 0) * 100)}%</strong> success</span>
          <span className="af-history__metrics-sep">·</span>
          <span><strong>{metrics.avg_duration_sec || 0}s</strong> avg</span>
          <span className="af-history__metrics-sep">·</span>
          <span><strong>{metrics.patch_stats?.applied || 0}</strong> patches</span>
        </div>
      )}
        {runMessages.length === 0 ? (
          <div style={{ padding: 20, color: 'var(--af-text-dim)', fontSize: 11, textAlign: 'center' }}>
            No runs yet — send a goal in the Compose view
          </div>
        ) : (
          <div>
            {runMessages.map((m, i) => {
              const run = m.run || {}
              const isActive = activeRun?.id && run.id === activeRun.id
              return (
                <div key={i} className={`af-row ${isActive ? 'af-row--active' : ''}`}>
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                    background: isActive ? 'var(--af-bronze-bright)' : run.status === 'applied' ? 'var(--af-green)' : 'var(--af-amber)',
                    boxShadow: '0 0 6px currentColor',
                    animation: isActive ? 'afPulse 2s ease-in-out infinite' : 'none',
                  }} />
                  <div className="af-grow">
                    <div className="af-truncate" style={{ font: '500 11.5px Inter, sans-serif', color: 'var(--af-text)' }}>
                      {m.content?.slice(0, 80) || 'Run created'}
                    </div>
                    <div style={{ font: '500 9.5px monospace', color: 'var(--af-text-dim)', marginTop: 2, letterSpacing: '0.06em' }}>
                      {run.id?.slice(-12) || '—'} · {run.status || 'pending'} · {m.actions?.length || 0} actions
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </ForgePanel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <ForgePanel title="Current run" sub="detail">
          {activeRun ? (
            <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {Object.entries({ ID: activeRun.id, Status: activeRun.status, Error: activeRun.ui_error }).filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="af-flex" style={{ justifyContent: 'space-between' }}>
                  <span style={{ font: '500 10px monospace', letterSpacing: '0.10em', color: 'var(--af-text-dim)', textTransform: 'uppercase' }}>{k}</span>
                  <span style={{ font: '500 11px monospace', color: k === 'Error' ? 'var(--af-red)' : 'var(--af-text)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{String(v)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: '12px', color: 'var(--af-text-dim)', fontSize: 11 }}>No active run</div>
          )}
        </ForgePanel>
      </div>
    </div>
  )
}

// ── AgentsView ────────────────────────────────────────────────────────────────
export function AgentsView() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    const headers = { Authorization: `Bearer ${localStorage.getItem('ai_jwt') || ''}` }
    fetch('/api/agents', { headers })
      .then(r => r.json())
      .then(d => setAgents(Array.isArray(d) ? d : d.agents || []))
      .catch(() => setAgents([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // Poll every 4s so forge agent statuses stay live during a run
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [])

  const display = agents

  const toneColors = { gold: '#E5C76B', info: '#60A5FA', purple: '#C084FC', teal: '#20D6C7', danger: '#FCA5A5', bronze: '#CD7F32' }

  return (
    <div className="af-agents-view">
      <ForgePanel title="Agent roster" sub={`${display.length}`} bodyStyle={{ padding: 0 }}>
        {loading ? (
          <div style={{ padding: 20, color: 'var(--af-text-dim)', fontSize: 11 }}>Loading agents…</div>
        ) : display.length === 0 ? (
          <div style={{ padding: 20, color: 'var(--af-text-dim)', fontSize: 11 }}>No agents active. Start an auto-build to see forge agents here.</div>
        ) : display.map(a => {
          const c = toneColors[a.tone] || '#CD7F32'
          return (
            <div key={a.id} className="af-row">
              <div className="af-hex" style={{ background: `rgba(${c.replace('#', '').match(/../g).map(x => parseInt(x, 16)).join(',')},0.10)`, color: c, border: `1px solid ${c}44`, width: 32, height: 32 }}>
                <span style={{ font: '700 11px Inter, sans-serif', color: c }}>{(a.name || 'A')[0]}</span>
              </div>
              <div className="af-grow">
                <div className="af-flex" style={{ gap: 6 }}>
                  <span style={{ font: '600 11.5px Inter, sans-serif', color: 'var(--af-text)' }}>{a.name}</span>
                  <span style={{ width: 5, height: 5, borderRadius: '50%', background: c, boxShadow: `0 0 6px ${c}`, animation: a.status !== 'idle' ? 'afPulse 2s ease-in-out infinite' : 'none' }} />
                </div>
                <div style={{ font: '500 9.5px monospace', color: 'var(--af-text-dim)', letterSpacing: '0.06em', marginTop: 1, textTransform: 'uppercase' }}>{a.model}</div>
                {a.task && <div className="af-truncate" style={{ font: '400 10.5px monospace', color: 'var(--af-text-muted)', marginTop: 3 }}>{a.task}</div>}
              </div>
              <div className={`af-pill af-pill--sm ${a.status === 'idle' ? 'af-pill--idle' : ''}`} style={{ flexShrink: 0 }}>
                {(a.status || 'idle').toUpperCase()}
              </div>
            </div>
          )
        })}
      </ForgePanel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <ForgePanel title="Forge system" sub="live">
          <ForgeSystemPanel onQueueItems={() => {}} />
        </ForgePanel>
      </div>
    </div>
  )
}
