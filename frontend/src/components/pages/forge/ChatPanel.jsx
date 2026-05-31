import { useState, useEffect, useRef } from 'react'
import { EmptyState } from '../../nexus-ui'
import { toastSuccess, toastError } from '../../nexus-ui/Toaster'
import { JGET, JPOST_JSON, TEMPLATES, DEFAULT_SKILL_PACKS, titleize } from './helpers'
import { StructuredMessageBlock } from './primitives'

export function SkillPackSelector({ project, draftGoal, selectedSkillIds, onChange }) {
  const [skills, setSkills] = useState([])
  const [pack, setPack] = useState('all')
  const [loading, setLoading] = useState(false)
  const [recommending, setRecommending] = useState(false)
  const selected = new Set(selectedSkillIds)

  useEffect(() => {
    setLoading(true)
    JGET('/api/skills/library')
      .then(r => r.json())
      .then(d => setSkills(Array.isArray(d.skills) ? d.skills : []))
      .catch(() => setSkills([]))
      .finally(() => setLoading(false))
  }, [])

  const packs = [...new Map([
    ...DEFAULT_SKILL_PACKS,
    ...skills
      .filter(skill => skill.source_pack)
      .map(skill => ({ id: skill.source_pack, label: titleize(skill.source_pack) })),
  ].map(item => [item.id, item])).values()]

  const visible = skills
    .filter(skill => pack === 'all' || skill.source_pack === pack)
    .filter(skill => skill.compatible_agents?.includes('ascend-forge') || skill.source_pack || /agent|forge|policy|approval|code|build|workflow/i.test(`${skill.category || ''} ${skill.name || ''} ${skill.description || ''}`))
    .slice(0, 36)

  const toggle = (id) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(Array.from(next).slice(0, 12))
  }

  const recommend = async () => {
    setRecommending(true)
    try {
      const d = await JPOST_JSON('/api/forge/skills/recommend', {
        goal: draftGoal || project?.name || 'supervised build',
        target_type: project?.target_type || 'build_agent',
        limit: 8,
      })
      const ids = (d.recommendedSkills || []).map(skill => skill.id).filter(Boolean)
      if (ids.length) onChange(ids)
    } catch (e) {
      toastError(`Skill recommendation failed: ${e.message}`)
    } finally {
      setRecommending(false)
    }
  }

  return (
    <div className="af-skills">
      <div className="af-skills__header">
        <span>Skill Packs</span>
        <button className="af-btn af-btn--ghost af-btn--sm" disabled={recommending || loading} onClick={recommend}>
          {recommending ? '…' : 'Recommend'}
        </button>
      </div>
      <div className="af-skills__filters">
        <button className={`af-skill-filter ${pack === 'all' ? 'af-skill-filter--active' : ''}`} onClick={() => setPack('all')}>All</button>
        {packs.slice(0, 7).map(item => (
          <button key={item.id} className={`af-skill-filter ${pack === item.id ? 'af-skill-filter--active' : ''}`} onClick={() => setPack(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      {selectedSkillIds.length > 0 && (
        <div className="af-skills__selected">
          {selectedSkillIds.map(id => {
            const skill = skills.find(item => item.id === id)
            return <button key={id} onClick={() => toggle(id)}>{skill?.name || id}</button>
          })}
        </div>
      )}
      <div className="af-skills__list">
        {loading && <span className="af-skills__empty">Loading skill packs…</span>}
        {!loading && visible.length === 0 && <span className="af-skills__empty">No skills available</span>}
        {!loading && visible.map(skill => (
          <button
            key={skill.id}
            className={`af-skill ${selected.has(skill.id) ? 'af-skill--selected' : ''}`}
            onClick={() => toggle(skill.id)}
            title={skill.description || skill.id}
          >
            <span>{skill.name || skill.id}</span>
            <em>{skill.source_pack || skill.category || 'native'}</em>
          </button>
        ))}
      </div>
    </div>
  )
}

export function ProjectPicker({ project, onSelect, onNew }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    JGET('/api/forge/projects').then(r => r.json()).then(d => {
      setProjects(d.projects || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="af-picker__loading">Loading projects…</div>

  return (
    <div className="af-picker">
      <div className="af-picker__actions">
        <button className="af-btn af-btn--primary" onClick={onNew}>+ New Project</button>
      </div>
      {projects.length === 0
        ? <EmptyState icon="📁" title="No projects" sub="Create a new project to start building." />
        : projects.map(p => (
          <button key={p.id} className={`af-picker__item ${project?.id === p.id ? 'af-picker__item--active' : ''}`} onClick={() => onSelect(p)}>
            <span className="af-picker__item-name">{p.name}</span>
            <span className="af-picker__item-path">{p.path}</span>
          </button>
        ))
      }
    </div>
  )
}

export function NewProjectModal({ onClose, onCreate }) {
  const [name, setName] = useState('')
  const [template, setTemplate] = useState(TEMPLATES[0].id)
  const [creating, setCreating] = useState(false)

  const create = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const d = await JPOST_JSON('/api/forge/projects', { name, template })
      if (d.project) { onCreate(d); toastSuccess(`Project "${name}" scaffold staged`) }
      else toastError(d.error || 'Failed to create project')
    } catch (e) { toastError(e.message) }
    finally { setCreating(false) }
  }

  return (
    <div className="af-modal-overlay" onClick={onClose}>
      <div className="af-modal" onClick={e => e.stopPropagation()}>
        <h3 className="af-modal__title">New Project</h3>
        <label className="af-modal__label">Project Name</label>
        <input className="af-modal__input" value={name} onChange={e => setName(e.target.value)} placeholder="my-project" autoFocus />
        <label className="af-modal__label">Template</label>
        <div className="af-modal__templates">
          {TEMPLATES.map(t => (
            <button key={t.id} className={`af-tpl-btn ${template === t.id ? 'af-tpl-btn--active' : ''}`} onClick={() => setTemplate(t.id)}>
              <span>{t.icon}</span>
              <span className="af-tpl-btn__label">{t.label}</span>
              <span className="af-tpl-btn__stack">{t.stack}</span>
            </button>
          ))}
        </div>
        <div className="af-modal__actions">
          <button className="af-btn af-btn--ghost" onClick={onClose}>Cancel</button>
          <button className="af-btn af-btn--primary" onClick={create} disabled={creating || !name.trim()}>
            {creating ? 'Creating…' : 'Create Project'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function ChatPane({ project, messages, onSend, sending, selectedSkillIds, onSkillChange, draftGoal, setDraftGoal }) {
  const inputRef = useRef(null)
  const endRef   = useRef(null)
  const [text, setText] = useState('')

  useEffect(() => {
    if (draftGoal) {
      setText(draftGoal)
      setDraftGoal?.('')
      inputRef.current?.focus()
    }
  }, [draftGoal, setDraftGoal])

  const scrollTimer = useRef(null)
  useEffect(() => {
    clearTimeout(scrollTimer.current)
    scrollTimer.current = setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 80)
    return () => clearTimeout(scrollTimer.current)
  }, [messages])

  const send = () => {
    if (!text.trim() || sending) return
    onSend(text.trim())
    setText('')
  }

  const onKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }

  return (
    <div className="af-chat">
      {project && (
        <SkillPackSelector
          project={project}
          draftGoal={text}
          selectedSkillIds={selectedSkillIds}
          onChange={onSkillChange}
        />
      )}
      <div className="af-chat__msgs">
        {messages.length === 0 && (
          <div className="af-chat__welcome">
            <div className="af-chat__welcome-icon">◆</div>
            <p className="af-chat__welcome-title">AscendForge Vibecoder</p>
            <p className="af-chat__welcome-sub">
              Tell me what to build. I'll plan, write code, and run tests — all with your approval.
            </p>
            <div className="af-chat__tips">
              <span>"Add a REST API endpoint for user login"</span>
              <span>"Build a new agent that monitors stock prices"</span>
              <span>"Refactor the auth system to use JWT"</span>
              <span>"Create a landing page with a dark theme"</span>
            </div>
          </div>
        )}
        {messages.map((m, i) => {
          const bodyText = m.content
          return (
            <div key={i} className={`af-msg af-msg--${m.role}`}>
              <div className="af-msg__role">{m.role === 'user' ? 'YOU' : 'FORGE'}</div>
              <div className="af-msg__body">
                {typeof bodyText === 'string'
                  ? bodyText.split('\n').map((l, j) => <p key={j}>{l}</p>)
                  : bodyText}
              </div>
              <StructuredMessageBlock data={m} />
              {m.role === 'assistant' && m.actions?.length > 0 && (
                <div className="af-msg__actions-summary">
                  {m.actions.length} action{m.actions.length > 1 ? 's' : ''} proposed ↓
                </div>
              )}
            </div>
          )
        })}
        {sending && (
          <div className="af-msg af-msg--assistant">
            <div className="af-msg__role">FORGE</div>
            <div className="af-msg__body af-msg__body--thinking">
              <span className="af-thinking-dot" />
              <span className="af-thinking-dot" />
              <span className="af-thinking-dot" />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      {!project && (
        <div className="af-chat__no-project">Select or create a project first</div>
      )}
      <div className="af-chat__input-row">
        <textarea
          ref={inputRef}
          className="af-chat__input"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={project ? 'Tell me what to build…' : 'Select a project first'}
          disabled={!project || sending}
          rows={2}
        />
        <button className="af-btn af-btn--primary af-chat__send" onClick={send} disabled={!project || !text.trim() || sending}>
          {sending ? '…' : '▶'}
        </button>
      </div>
    </div>
  )
}
