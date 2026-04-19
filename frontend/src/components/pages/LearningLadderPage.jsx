import { useState, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import PageHeader from '../layout/PageHeader'
import { API_URL } from '../../config/api'

const BASE = API_URL

const LEVEL_COLORS = {
  1: 'var(--text-muted)',
  2: '#6ea8fe',
  3: 'var(--warning)',
  4: '#e07b39',
  5: 'var(--gold)',
}

const STATUS_COLORS = {
  not_started: 'var(--text-muted)',
  failed: 'var(--error)',
  completed: 'var(--success)',
}

const GRADE_COLORS = {
  Ungraded: 'var(--text-muted)',
  Beginner: '#6ea8fe',
  Basic: '#52d9b2',
  Mature: '#f7c948',
  Advanced: '#e07b39',
  Pro: 'var(--gold)',
}

// ── Agent Assignment Panel ─────────────────────────────────────────────────────

function AgentAssignPanel({ currentTopic, onAssigned }) {
  const [agentId, setAgentId] = useState('')
  const [assignTopic, setAssignTopic] = useState(currentTopic || '')
  const [submitting, setSubmitting] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [profiles, setProfiles] = useState([])

  useEffect(() => {
    setAssignTopic(currentTopic || '')
  }, [currentTopic])

  const fetchProfiles = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/agents/grades`)
      const data = await res.json()
      if (data.ok) setProfiles(data.profiles || [])
    } catch (_) {}
  }, [])

  useEffect(() => { fetchProfiles() }, [fetchProfiles])

  const handleAssign = useCallback(async () => {
    const aid = agentId.trim()
    const top = assignTopic.trim()
    if (!aid || !top) return
    setSubmitting(true)
    setMsg('')
    setErr('')
    try {
      const res = await fetch(`${BASE}/api/agents/${encodeURIComponent(aid)}/ladder/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: top }),
      })
      const data = await res.json()
      if (data.ok) {
        setMsg(`Ladder '${top}' assigned to ${aid} — grade: ${data.grade}`)
        setAgentId('')
        await fetchProfiles()
        onAssigned && onAssigned()
      } else {
        setErr(data.error || 'Failed to assign')
      }
    } catch (e) {
      setErr(e.message)
    } finally {
      setSubmitting(false)
    }
  }, [agentId, assignTopic, fetchProfiles, onAssigned])

  return (
    <div className="ds-card" style={{ padding: 'var(--space-4)' }}>
      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 'var(--space-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        Assign to Agent
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        <input
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          placeholder="Agent ID (e.g. lead-hunter)"
          style={{
            background: 'var(--bg-base)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-2) var(--space-3)',
            color: 'var(--text-primary)',
            fontSize: '12px',
            outline: 'none',
          }}
        />
        <input
          value={assignTopic}
          onChange={(e) => setAssignTopic(e.target.value)}
          placeholder="Topic"
          style={{
            background: 'var(--bg-base)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-2) var(--space-3)',
            color: 'var(--text-primary)',
            fontSize: '12px',
            outline: 'none',
          }}
        />
        <button
          className="btn-primary"
          style={{ fontSize: '12px' }}
          disabled={submitting || !agentId.trim() || !assignTopic.trim()}
          onClick={handleAssign}
        >
          {submitting ? 'Assigning…' : 'Assign Ladder'}
        </button>
      </div>

      {(msg || err) && (
        <div style={{
          fontSize: '11px',
          color: err ? 'var(--error)' : 'var(--success)',
          marginBottom: 'var(--space-3)',
        }}>
          {err || msg}
        </div>
      )}

      {/* Agent grade list */}
      {profiles.length > 0 && (
        <div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 'var(--space-2)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
            Graded Agents
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '240px', overflowY: 'auto' }}>
            {profiles.map((p) => (
              <div key={p.agent_id} style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: 'var(--space-2) var(--space-3)',
                background: 'var(--bg-base)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12px',
              }}>
                <div>
                  <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{p.agent_id}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: '10px', marginTop: '1px' }}>{p.topic}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  <div style={{ display: 'flex', gap: '2px' }}>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <span key={n} style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: '1px',
                        background: n <= (p.levels_completed || 0) ? GRADE_COLORS[p.grade] || 'var(--success)' : 'var(--border-subtle)',
                      }} />
                    ))}
                  </div>
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '8px',
                    background: `${GRADE_COLORS[p.grade] || 'var(--text-muted)'}18`,
                    color: GRADE_COLORS[p.grade] || 'var(--text-muted)',
                    border: `1px solid ${GRADE_COLORS[p.grade] || 'var(--text-muted)'}30`,
                    fontWeight: 600,
                  }}>
                    {p.grade}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Level Card ────────────────────────────────────────────────────────────────

function LevelCard({ levelData, progressRec, onComplete, topic, isNext, disabled }) {
  const [showComplete, setShowComplete] = useState(false)
  const [output, setOutput] = useState('')
  const [score, setScore] = useState('0.8')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const status = progressRec?.status || 'not_started'
  const learned = progressRec?.learned || false
  const attempts = progressRec?.attempts?.length || 0
  const color = LEVEL_COLORS[levelData.level]

  const handleComplete = useCallback(async (success) => {
    setSubmitting(true)
    try {
      await onComplete({
        topic,
        level: levelData.level,
        success,
        milestone_output: output,
        score: parseFloat(score) || 0,
        notes,
      })
      setShowComplete(false)
      setOutput('')
      setNotes('')
    } finally {
      setSubmitting(false)
    }
  }, [topic, levelData.level, output, score, notes, onComplete])

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: (levelData.level - 1) * 0.06 }}
      className="ds-card"
      style={{
        padding: 'var(--space-4)',
        borderLeft: `3px solid ${learned ? 'var(--success)' : isNext ? color : 'var(--border-subtle)'}`,
        opacity: disabled && !learned ? 0.55 : 1,
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={{
          width: '28px',
          height: '28px',
          borderRadius: '50%',
          background: learned ? 'var(--success)' : isNext ? color : 'var(--bg-base)',
          border: `2px solid ${learned ? 'var(--success)' : color}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '12px',
          fontWeight: 600,
          color: learned ? '#fff' : color,
          flexShrink: 0,
        }}>
          {learned ? '✓' : levelData.level}
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>
              Level {levelData.level} — {levelData.name}
            </span>
            {status !== 'not_started' && (
              <span style={{
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '4px',
                background: `${STATUS_COLORS[status]}20`,
                color: STATUS_COLORS[status],
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}>
                {learned ? 'LEARNED' : status}
              </span>
            )}
            {isNext && !learned && (
              <span style={{
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '4px',
                background: `${color}20`,
                color,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}>
                NEXT
              </span>
            )}
          </div>
          {attempts > 0 && (
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
              {attempts} attempt{attempts !== 1 ? 's' : ''}
              {progressRec?.best_score ? ` · best score: ${(progressRec.best_score * 100).toFixed(0)}%` : ''}
            </div>
          )}
        </div>
      </div>

      {/* Description */}
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)', lineHeight: 1.5 }}>
        {levelData.description}
      </p>

      {/* Skills */}
      <div style={{ marginBottom: 'var(--space-3)' }}>
        <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 'var(--space-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Core Skills
        </div>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {levelData.skills.map((skill, idx) => (
            <li key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-2)', fontSize: '12px', color: 'var(--text-secondary)' }}>
              <span style={{ color, flexShrink: 0, marginTop: '1px' }}>▸</span>
              {skill}
            </li>
          ))}
        </ul>
      </div>

      {/* Milestone */}
      <div style={{
        padding: 'var(--space-3)',
        background: 'var(--bg-base)',
        borderRadius: 'var(--radius-md)',
        marginBottom: 'var(--space-3)',
        fontSize: '12px',
        color: 'var(--text-secondary)',
        lineHeight: 1.5,
      }}>
        <span style={{ fontWeight: 600, color, marginRight: '6px' }}>Milestone:</span>
        {levelData.milestone}
      </div>

      {/* Skill gaps */}
      {progressRec?.skill_gaps?.length > 0 && (
        <div style={{ marginBottom: 'var(--space-3)', fontSize: '12px', color: 'var(--error)' }}>
          <span style={{ fontWeight: 600 }}>Skill gaps: </span>
          {progressRec.skill_gaps.join(' · ')}
        </div>
      )}

      {/* Complete/Fail buttons */}
      {!disabled && !learned && (
        <div>
          {!showComplete ? (
            <button
              className="btn-secondary"
              style={{ fontSize: '12px' }}
              onClick={() => setShowComplete(true)}
            >
              Record Milestone Attempt
            </button>
          ) : (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}
            >
              <textarea
                placeholder="Describe what was produced / executed..."
                value={output}
                onChange={(e) => setOutput(e.target.value)}
                rows={3}
                style={{
                  width: '100%',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: 'var(--space-2) var(--space-3)',
                  color: 'var(--text-primary)',
                  fontSize: '12px',
                  resize: 'vertical',
                  fontFamily: 'inherit',
                  boxSizing: 'border-box',
                }}
              />
              <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
                <label style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Score:
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={score}
                    onChange={(e) => setScore(e.target.value)}
                    style={{
                      width: '64px',
                      marginLeft: '6px',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '2px 6px',
                      color: 'var(--text-primary)',
                      fontSize: '12px',
                    }}
                  />
                </label>
                <input
                  placeholder="Skill gaps / notes (optional)"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  style={{
                    flex: 1,
                    minWidth: '120px',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-2) var(--space-3)',
                    color: 'var(--text-primary)',
                    fontSize: '12px',
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                <button
                  className="btn-primary"
                  style={{ fontSize: '12px' }}
                  disabled={submitting}
                  onClick={() => handleComplete(true)}
                >
                  {submitting ? 'Saving…' : '✓ Milestone Completed'}
                </button>
                <button
                  className="btn-danger"
                  style={{ fontSize: '12px' }}
                  disabled={submitting}
                  onClick={() => handleComplete(false)}
                >
                  ✕ Milestone Failed
                </button>
                <button
                  className="btn-secondary"
                  style={{ fontSize: '12px' }}
                  onClick={() => setShowComplete(false)}
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          )}
        </div>
      )}
    </motion.div>
  )
}

// ── Topic row ─────────────────────────────────────────────────────────────────

function TopicRow({ item, onSelect, isActive }) {
  return (
    <button
      onClick={() => onSelect(item.topic)}
      style={{
        width: '100%',
        textAlign: 'left',
        padding: 'var(--space-3) var(--space-4)',
        background: isActive ? 'rgba(212, 175, 55, 0.08)' : 'transparent',
        border: 'none',
        borderLeft: `2px solid ${isActive ? 'var(--gold)' : 'transparent'}`,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 'var(--space-3)',
      }}
    >
      <div>
        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
          {item.topic}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
          {item.levels_completed}/5 levels
        </div>
      </div>
      <div style={{ display: 'flex', gap: '3px' }}>
        {[1, 2, 3, 4, 5].map((n) => (
          <span key={n} style={{
            width: '8px',
            height: '8px',
            borderRadius: '2px',
            background: n <= item.levels_completed ? 'var(--success)' : 'var(--border-subtle)',
          }} />
        ))}
      </div>
    </button>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LearningLadderPage() {
  const [topic, setTopic] = useState('')
  const [ladder, setLadder] = useState(null)
  const [progress, setProgress] = useState({})
  const [nextLevel, setNextLevel] = useState(null)
  const [allTopics, setAllTopics] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/learning-ladder/all`)
      const data = await res.json()
      if (data.ok) {
        setAllTopics(data.topics || [])
        setMetrics(data.metrics || null)
      }
    } catch (_) {}
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const fetchProgress = useCallback(async (t) => {
    if (!t) return
    try {
      const res = await fetch(`${BASE}/api/learning-ladder/progress?topic=${encodeURIComponent(t)}`)
      const data = await res.json()
      if (data.ok) {
        setLadder(data.ladder)
        setProgress(data.progress || {})
        setNextLevel(data.next_level)
      }
    } catch (_) {}
  }, [])

  const handleBuild = useCallback(async () => {
    const t = topic.trim()
    if (!t) return
    setLoading(true)
    setError('')
    setStatus('')
    try {
      const res = await fetch(`${BASE}/api/learning-ladder/build`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: t }),
      })
      const data = await res.json()
      if (data.ok) {
        setLadder(data.ladder)
        setProgress({})
        setNextLevel(1)
        setStatus('Ladder built. Start at Level 1.')
        await fetchAll()
      } else {
        setError(data.error || 'Failed to build ladder')
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [topic, fetchAll])

  const handleSelectTopic = useCallback(async (t) => {
    setTopic(t)
    setError('')
    setStatus('')
    await fetchProgress(t)
  }, [fetchProgress])

  const handleComplete = useCallback(async (payload) => {
    setError('')
    try {
      const res = await fetch(`${BASE}/api/learning-ladder/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (data.ok) {
        const r = data.result
        setNextLevel(r.next_level)
        setStatus(
          r.learned
            ? `✓ Level ${r.level} marked as LEARNED (score: ${(r.best_score * 100).toFixed(0)}%). ${r.adaptation?.reason || ''}`
            : `✕ Level ${r.level} NOT LEARNED — Anti-Illusion Protocol active. ${r.adaptation?.reason || ''}`
        )
        await fetchProgress(payload.topic)
        await fetchAll()
      } else {
        setError(data.error || 'Failed to record completion')
      }
    } catch (e) {
      setError(e.message)
    }
  }, [fetchProgress, fetchAll])

  const activeTopic = ladder?.topic || ''

  return (
    <div className="page-enter">
      <PageHeader title="Learning Ladder" subtitle="Structured 5-level progression — Beginner · Basic · Mature · Advanced · Pro">
        {metrics && (
          <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: '12px', color: 'var(--text-muted)' }}>
            <span>{metrics.total_topics} topics</span>
            <span>{metrics.total_levels_completed} levels completed</span>
          </div>
        )}
      </PageHeader>

      {/* Build input */}
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleBuild()}
          placeholder="Enter a topic, skill, or domain…"
          style={{
            flex: '1 1 260px',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-2) var(--space-3)',
            color: 'var(--text-primary)',
            fontSize: '13px',
            outline: 'none',
          }}
        />
        <button className="btn-primary" onClick={handleBuild} disabled={loading || !topic.trim()}>
          {loading ? 'Building…' : 'Build Ladder'}
        </button>
      </div>

      {/* Status / error banner */}
      <AnimatePresence>
        {(status || error) && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="ds-card"
            style={{
              padding: 'var(--space-3) var(--space-4)',
              marginBottom: 'var(--space-4)',
              fontSize: '13px',
              color: error ? 'var(--error)' : 'var(--text-secondary)',
              borderLeft: `3px solid ${error ? 'var(--error)' : 'var(--gold)'}`,
            }}
          >
            {error || status}
          </motion.div>
        )}
      </AnimatePresence>

      <div style={{
        display: 'grid',
        gridTemplateColumns: allTopics.length > 0 ? '220px 1fr 220px' : '1fr 220px',
        gap: 'var(--space-4)',
        alignItems: 'start',
      }}>
        {/* Topic sidebar */}
        {allTopics.length > 0 && (
          <div className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{
              padding: 'var(--space-3) var(--space-4)',
              borderBottom: '1px solid var(--border-subtle)',
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}>
              Topics
            </div>
            {allTopics.map((item) => (
              <TopicRow
                key={item.id}
                item={item}
                onSelect={handleSelectTopic}
                isActive={item.topic === activeTopic}
              />
            ))}
          </div>
        )}

        {/* Ladder view */}
        <div>
          {!ladder ? (
            <div className="ds-card" style={{
              padding: 'var(--space-8)',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '13px',
            }}>
              Enter a topic and click <strong style={{ color: 'var(--text-secondary)' }}>Build Ladder</strong> to generate your 5-level learning progression.
            </div>
          ) : (
            <>
              <div style={{ marginBottom: 'var(--space-4)' }}>
                <h2 style={{ fontSize: '16px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '4px' }}>
                  {ladder.topic}
                </h2>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  ID: {ladder.id} · Built: {ladder.built_at ? new Date(ladder.built_at).toLocaleDateString() : '—'}
                  {nextLevel ? ` · Next: Level ${nextLevel}` : ' · All levels completed'}
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {ladder.levels.map((lvl) => {
                  const isPreviousLevelLearned = lvl.level === 1 || (progress[String(lvl.level - 1)] || {}).learned
                  const isNext = lvl.level === nextLevel
                  const blocked = !isPreviousLevelLearned && !(progress[String(lvl.level)] || {}).learned
                  return (
                    <LevelCard
                      key={lvl.level}
                      levelData={lvl}
                      progressRec={progress[String(lvl.level)]}
                      topic={ladder.topic}
                      onComplete={handleComplete}
                      isNext={isNext}
                      disabled={blocked}
                    />
                  )
                })}
              </div>
            </>
          )}
        </div>

        {/* Agent assignment panel */}
        <AgentAssignPanel
          currentTopic={activeTopic}
          onAssigned={fetchAll}
        />
      </div>
    </div>
  )
}
