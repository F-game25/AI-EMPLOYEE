'use strict'

/**
 * Forge → AgentController dispatcher.
 *
 * Closes the open loop between the approval queue and the real engine:
 *   forge_submit (MCP) → forge_queue_item (pending)
 *     → human approval (POST /api/forge/approve/:id → status 'approved')
 *       → THIS worker drains 'approved' items → POST /api/tasks/run (run_goal)
 *         → result + proof written back to the action + broadcast over WS.
 *
 * Design notes:
 *  - Single in-process worker on a setInterval, mirroring updateStabilityScore.
 *  - Bounded concurrency (default 1) so we never overload the Python engine.
 *  - Reuses forge.js's action-store helpers (single source of truth); no new
 *    persistence format.
 *  - Honors the existing reliabilityState.forgeFrozen circuit breaker.
 *  - Treats run_goal output strictly as data (no eval / shell / interpolation).
 *  - Bounded retries; an item that keeps failing is marked 'failed' (never loops).
 *  - Fully reversible: not starting the interval (FORGE_DISPATCH_ENABLED=0)
 *    reverts the queue to approve-only behavior.
 */

const QUEUE_KIND = 'forge_queue'

// Config — all from env, no hardcoded magic numbers.
function _int(name, def) {
  const v = parseInt(process.env[name], 10)
  return Number.isFinite(v) && v > 0 ? v : def
}

/**
 * @param {object} deps
 * @param {object} deps.store               forge.js action-store API (loadActions, updateAction, appendAudit, broadcastForge, emitForgeRuntimeSnapshot, nowIso)
 * @param {function} deps.requestPythonJSON (pathname, method, payload, options) => Promise
 * @param {object} [deps.reliabilityState]  { forgeFrozen, freezeReason } circuit breaker (read-only here)
 * @param {function} [deps.recordAuditEvent] ({ actor, action, outputData, riskScore }) => void
 * @param {function} [deps.log]             logger fn (default console.log)
 */
function createForgeDispatcher(deps = {}) {
  const {
    store,
    requestPythonJSON,
    reliabilityState = null,
    recordAuditEvent = null,
    log = (...a) => console.log('[forge-dispatch]', ...a),
  } = deps

  if (!store || typeof store.loadActions !== 'function' || typeof store.updateAction !== 'function') {
    throw new Error('createForgeDispatcher: deps.store with loadActions/updateAction is required')
  }
  if (typeof requestPythonJSON !== 'function') {
    throw new Error('createForgeDispatcher: deps.requestPythonJSON is required')
  }

  const enabled = String(process.env.FORGE_DISPATCH_ENABLED ?? '1') !== '0'
  const concurrency = _int('FORGE_DISPATCH_CONCURRENCY', 1)
  const intervalMs = _int('FORGE_DISPATCH_INTERVAL_MS', 5000)
  const maxRetries = _int('FORGE_DISPATCH_MAX_RETRIES', 2)
  const taskTimeoutMs = _int('FORGE_DISPATCH_TASK_TIMEOUT_MS', 180000)

  const { loadActions, updateAction, appendAudit, broadcastForge, emitForgeRuntimeSnapshot, nowIso } = store
  const _now = typeof nowIso === 'function' ? nowIso : () => new Date().toISOString()
  const _audit = typeof appendAudit === 'function' ? appendAudit : () => {}
  const _broadcast = typeof broadcastForge === 'function' ? broadcastForge : () => {}
  const _snapshot = typeof emitForgeRuntimeSnapshot === 'function' ? emitForgeRuntimeSnapshot : () => {}

  const _inFlight = new Set() // action ids currently executing — double-dispatch guard
  let _timer = null

  function isFrozen() {
    return !!(reliabilityState && reliabilityState.forgeFrozen)
  }

  function pendingApproved() {
    return loadActions().filter(
      (a) => a && a.queue_kind === QUEUE_KIND && a.status === 'approved' && !_inFlight.has(a.id),
    )
  }

  function broadcastItem(item) {
    _broadcast('forge:action_updated', { action: item, project_id: item?.project_id || null })
    _broadcast('forge:queue_update', { item })
  }

  // Map the Python /api/tasks/run response into a compact result + proof we persist.
  function buildResult(action, resp) {
    const httpOk = !resp || resp._http_status == null || (resp._http_status >= 200 && resp._http_status < 300)
    const ok = httpOk && resp && resp.ok === true
    const proof = Array.isArray(resp?.proof) ? resp.proof : []
    return {
      ok,
      run_id: resp?.run_id || null,
      proof,
      result: {
        source: resp?.source || 'agent_controller',
        run_id: resp?.run_id || null,
        scores: resp?.scores || null,
        task_count: Array.isArray(resp?.tasks) ? resp.tasks.length : 0,
        error: resp?.error || null,
        http_status: resp?._http_status ?? null,
      },
    }
  }

  async function dispatch(action) {
    const id = action.id
    _inFlight.add(id)
    const attempts = (action.dispatch_attempts || 0) + 1
    const goal = String(action.description || action.label || '').trim()

    // Flip to 'executing' synchronously before the await so the next tick skips it.
    const executing = updateAction(id, {
      status: 'executing',
      dispatch_attempts: attempts,
      dispatch_started_at: _now(),
      dispatch_error: null,
    })
    broadcastItem(executing || { id, status: 'executing' })
    _audit('forge_dispatch_started', { id, attempts, project_id: action.project_id || null })

    try {
      if (!goal) throw new Error('queue item has no goal/description to execute')
      const resp = await requestPythonJSON('/api/tasks/run', 'POST', { task: goal, goal }, { timeoutMs: taskTimeoutMs })
      const { ok, run_id, proof, result } = buildResult(action, resp)
      const finished = updateAction(id, {
        status: ok ? 'completed' : 'failed',
        dispatch_finished_at: _now(),
        dispatch_run_id: run_id,
        result,
        proof,
        dispatch_error: ok ? null : (result.error || 'engine reported failure'),
      })
      broadcastItem(finished || { id, status: ok ? 'completed' : 'failed' })
      _audit(ok ? 'forge_dispatch_completed' : 'forge_dispatch_failed', { id, run_id, project_id: action.project_id || null })
      if (recordAuditEvent) {
        try {
          recordAuditEvent({ actor: 'forge-dispatch', action: ok ? 'forge_dispatch_completed' : 'forge_dispatch_failed', outputData: { id, run_id }, riskScore: ok ? 0.2 : 0.5 })
        } catch (_) { /* best-effort */ }
      }
    } catch (err) {
      const reason = (err && err.message) || 'dispatch error'
      // Retry while under the cap by returning the item to 'approved'; otherwise fail it.
      const willRetry = attempts < maxRetries
      const patched = updateAction(id, {
        status: willRetry ? 'approved' : 'failed',
        dispatch_finished_at: willRetry ? null : _now(),
        dispatch_error: reason,
      })
      broadcastItem(patched || { id, status: willRetry ? 'approved' : 'failed' })
      _audit('forge_dispatch_error', { id, reason, attempts, will_retry: willRetry })
      log(`dispatch ${willRetry ? 'retry-scheduled' : 'failed'} for ${id}: ${reason}`)
    } finally {
      _inFlight.delete(id)
    }
  }

  async function tick() {
    if (!enabled || isFrozen()) return
    const slots = concurrency - _inFlight.size
    if (slots <= 0) return
    let queue
    try {
      queue = pendingApproved()
    } catch (err) {
      log('failed to read queue:', err.message)
      return
    }
    const batch = queue.slice(0, slots)
    for (const action of batch) {
      // Fire-and-forget; dispatch() manages its own _inFlight slot + status.
      dispatch(action).catch((e) => log('unexpected dispatch rejection:', e?.message))
    }
    if (batch.length) _snapshot('queue_dispatch', {})
  }

  function start() {
    if (_timer) return api
    if (!enabled) {
      log('disabled via FORGE_DISPATCH_ENABLED=0 — queue stays approve-only')
      return api
    }
    log(`started — concurrency=${concurrency} interval=${intervalMs}ms maxRetries=${maxRetries} taskTimeout=${taskTimeoutMs}ms`)
    _timer = setInterval(() => { tick().catch((e) => log('tick error:', e?.message)) }, intervalMs)
    if (typeof _timer.unref === 'function') _timer.unref()
    return api
  }

  function stop() {
    if (_timer) { clearInterval(_timer); _timer = null }
    return api
  }

  const api = { start, stop, tick, get inFlight() { return _inFlight.size }, config: { enabled, concurrency, intervalMs, maxRetries, taskTimeoutMs } }
  return api
}

module.exports = { createForgeDispatcher }
