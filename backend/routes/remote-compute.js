'use strict'

/**
 * Remote compute worker protocol routes (Phase 7).
 *
 * Server side of the worker fleet: owner mints pairing tokens, workers register
 * (with a valid pairing token), heartbeat, and the system assigns jobs to a
 * capable worker or falls back to local. Deny-by-default + scope-gated; remote
 * dispatch only when COMPUTE_FABRIC_LIVE=1.
 *
 * Pairs with backend/compute_fabric/* (provisioning + job artifact persistence).
 */
const { Router } = require('express')
const { getRemoteWorkerRegistry } = require('../services/remote_worker_registry')
const { dispatchJob } = require('../compute_fabric/remote_dispatch')

module.exports = function createRemoteComputeRouter(requireAuth, opts = {}) {
  // Falls back to plain requireAuth when requireScope isn't wired (never weakens to no-auth).
  const requireScope = typeof opts.requireScope === 'function' ? opts.requireScope : (() => requireAuth)
  const reg = getRemoteWorkerRegistry()
  const router = Router()

  // Owner mints a single-use, short-lived pairing token for a new worker.
  router.post('/pairing-token', requireScope('task-emit'), (req, res) => {
    res.json({ ok: true, ...reg.createPairingToken({ note: req.body?.note }) })
  })

  // A worker registers itself using a valid pairing token (deny-by-default).
  router.post('/workers/register', requireScope('task-emit'), (req, res) => {
    const out = reg.register(req.body || {})
    res.status(out.ok ? 200 : 400).json(out)
  })

  router.get('/workers', requireScope('read'), (_req, res) => res.json({ ok: true, workers: reg.list() }))

  router.get('/workers/:id', requireScope('read'), (req, res) => {
    const w = reg.get(req.params.id)
    return w ? res.json({ ok: true, worker: w }) : res.status(404).json({ ok: false, error: 'worker not found' })
  })

  router.post('/workers/:id/heartbeat', requireScope('task-emit'), (req, res) => {
    const out = reg.heartbeat(req.params.id, req.body || {})
    res.status(out.ok ? 200 : 404).json(out)
  })

  // Owner-only: promote/demote/block a worker (trust is never self-asserted).
  router.post('/workers/:id/trust', requireScope('task-emit'), (req, res) => {
    const out = reg.setTrust(req.params.id, String(req.body?.trust || ''))
    res.status(out.ok ? 200 : 400).json(out)
  })

  router.delete('/workers/:id', requireScope('task-emit'), (req, res) => {
    const out = reg.deregister(req.params.id)
    res.status(out.ok ? 200 : 404).json(out)
  })

  // Match a job to a capable worker, or fall back to local.
  router.post('/assign', requireScope('task-emit'), (req, res) => {
    res.json({ ok: true, assignment: reg.assign(req.body || {}) })
  })

  // Live dispatch: actually send the job to a trusted worker (peer or rented),
  // egress-gated + leak-scanned. Deny-by-default; refuses → caller runs local.
  router.post('/dispatch', requireScope('task-emit'), async (req, res) => {
    const out = await dispatchJob(req.body || {})
    res.status(out.ok ? 200 : 200).json({ ok: true, dispatch: out })
  })

  router.get('/audit', requireScope('read'), (req, res) => {
    const limit = Math.min(500, Math.max(1, parseInt(req.query.limit, 10) || 100))
    res.json({ ok: true, audit: reg.auditTail(limit) })
  })

  return router
}
