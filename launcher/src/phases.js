const { EventEmitter } = require('events')

/**
 * Canonical boot phases — the launcher renderer renders one dot per phase,
 * filling as each one completes. The phase order is the canonical path; a
 * phase that fails surfaces the *last successful* phase + the failing one
 * on the diagnostics screen.
 */
const PHASES = [
  'preflight',          // Env vars + Python binary check (fast, always runs first)
  'deps-check',         // Verify node, python, npm modules
  'backend-spawn',      // start.sh launched
  'node-port-bound',    // TCP :8787 accepting connections
  'python-port-bound',  // TCP :18790 accepting connections (optional — degraded if missing)
  'health-ok',          // /api/health returns 200
  'window-create',      // BrowserWindow created
  'html-loaded',        // did-finish-load fired on the dashboard URL
  'react-rendered',     // First paint signal from frontend/src/main.jsx (early)
  'react-mounted',      // Full Dashboard mount signal (rich, optional)
]

const PHASE_LABELS = {
  'preflight':         'Pre-flight checks',
  'deps-check':        'Verifying dependencies',
  'backend-spawn':     'Spawning backend services',
  'node-port-bound':   'Node gateway listening',
  'python-port-bound': 'Python AI backend listening',
  'health-ok':         'Health probes passing',
  'window-create':     'Dashboard window opened',
  'html-loaded':       'Dashboard HTML received',
  'react-rendered':    'React first paint',
  'react-mounted':     'Dashboard fully mounted',
}

class PhaseTracker extends EventEmitter {
  constructor() {
    super()
    this.completed = new Set()
    this.current = null
    this.failed = null
    this.failedReason = null
    this.history = []
    // Per-phase timing records: { [phase]: { startedAt, endedAt, durationMs, status } }
    this.records = {}
    this.bootStartedAt = 0
    this.bootEndedAt = 0
  }

  reset() {
    this.completed.clear()
    this.current = null
    this.failed = null
    this.failedReason = null
    this.history = []
    this.records = {}
    this.bootStartedAt = Date.now()
    this.bootEndedAt = 0
    this.emit('reset')
  }

  /** Mark a phase as started (begins duration timer). Idempotent. */
  start(phase) {
    if (!PHASES.includes(phase)) return
    if (!this.bootStartedAt) this.bootStartedAt = Date.now()
    const rec = this.records[phase] || { startedAt: 0, endedAt: 0, durationMs: 0, status: 'pending' }
    if (rec.startedAt) return // already started
    rec.startedAt = Date.now()
    rec.status = 'running'
    this.records[phase] = rec
    this.current = phase
  }

  /** Mark a phase as completed (advances the rail). */
  complete(phase, meta = {}) {
    if (!PHASES.includes(phase)) return
    if (this.completed.has(phase)) return
    const rec = this.records[phase] || { startedAt: 0, endedAt: 0, durationMs: 0, status: 'pending' }
    if (!rec.startedAt) rec.startedAt = Date.now() // implicit start if complete called solo
    rec.endedAt = Date.now()
    rec.durationMs = rec.endedAt - rec.startedAt
    rec.status = 'ok'
    this.records[phase] = rec
    this.completed.add(phase)
    this.current = phase
    if (phase === PHASES[PHASES.length - 1]) this.bootEndedAt = rec.endedAt
    const entry = { phase, label: PHASE_LABELS[phase] || phase, ts: rec.endedAt, durationMs: rec.durationMs, meta }
    this.history.push(entry)
    this.emit('phase', entry)
  }

  /** Mark a phase as failed. Includes the reason text shown on diagnostics. */
  fail(phase, reason) {
    this.failed = phase
    this.failedReason = String(reason || 'Unknown failure')
    const rec = this.records[phase] || { startedAt: 0, endedAt: 0, durationMs: 0, status: 'pending' }
    if (!rec.startedAt) rec.startedAt = Date.now()
    rec.endedAt = Date.now()
    rec.durationMs = rec.endedAt - rec.startedAt
    rec.status = 'fail'
    this.records[phase] = rec
    const entry = { phase, reason: this.failedReason, ts: rec.endedAt, durationMs: rec.durationMs }
    this.history.push({ ...entry, failed: true })
    this.emit('fail', entry)
  }

  /** Snapshot for the diagnostics screen + IPC payloads. */
  snapshot() {
    return {
      phases: PHASES,
      labels: PHASE_LABELS,
      completed: Array.from(this.completed),
      current: this.current,
      failed: this.failed,
      failedReason: this.failedReason,
      history: this.history.slice(-50),
      records: this.records,
    }
  }

  /** Aggregate timing summary for boot_metrics.json. */
  summary() {
    const phases = PHASES.map(name => {
      const r = this.records[name] || { durationMs: 0, status: 'skipped' }
      return { name, durationMs: r.durationMs || 0, status: r.status || 'skipped' }
    })
    const total_ms = this.bootEndedAt && this.bootStartedAt
      ? this.bootEndedAt - this.bootStartedAt
      : phases.reduce((s, p) => s + (p.durationMs || 0), 0)
    return { total_ms, phases }
  }
}

const tracker = new PhaseTracker()

module.exports = { PHASES, PHASE_LABELS, PhaseTracker, tracker }
