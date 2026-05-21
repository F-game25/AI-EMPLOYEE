'use strict';

// Compute Fabric routes (WS6) — estimate/search/approve/provision remote GPU.
// Every money path is dry-run by default and owner-gated. See compute_fabric/index.js.

const express = require('express');
const cf = require('../compute_fabric');
const persist = require('../compute_fabric/persistence');

module.exports = function createComputeRouter(requireAuth) {
  const router = express.Router();

  router.get('/local-status', requireAuth, async (_req, res) => {
    res.json({ ok: true, ...(await cf.localStatus()), live_provisioning: cf.LIVE });
  });

  router.get('/providers', requireAuth, (_req, res) => {
    res.json({ ok: true, providers: cf.PROVIDERS, live_provisioning: cf.LIVE });
  });

  router.post('/estimate', requireAuth, (req, res) => {
    res.json({ ok: true, estimate: cf.estimate(req.body || {}) });
  });

  router.post('/search-offers', requireAuth, (req, res) => {
    res.json({ ok: true, ...cf.searchOffers(req.body || {}) });
  });

  router.post('/request-approval', requireAuth, (req, res) => {
    res.json({ ok: true, approval: cf.requestApproval(req.body || {}) });
  });

  router.post('/verify-owner', requireAuth, (req, res) => {
    const r = cf.verifyOwner(req.body || {});
    res.status(r.ok ? 200 : 400).json(r);
  });

  // Dry-run by default. Real spend requires dry_run:false + valid approval_token +
  // COMPUTE_FABRIC_LIVE + budget + a provider adapter (none wired → always refused).
  router.post('/purchase', requireAuth, (req, res) => {
    res.json({ ok: true, ...cf.purchase(req.body || {}) });
  });

  router.post('/start-job', requireAuth, (req, res) => {
    const job = cf.startJob(req.body || {});
    // WS7: every job gets a local archive + heartbeat from the start.
    try { persist.initJob(job.id, { name: job.name, provider: job.provider, dry_run: job.dry_run }); } catch { /* */ }
    res.json({ ok: true, job });
  });

  // ── WS7: Remote Job Persistence — local is the source of truth ──────────────
  router.get('/jobs/:id/sync-status', requireAuth, (req, res) => res.json(persist.syncStatus(req.params.id)));
  router.get('/jobs/:id/manifest', requireAuth, (req, res) => res.json(persist.manifest(req.params.id)));
  router.get('/jobs/:id/artifacts', requireAuth, (req, res) => res.json(persist.artifacts(req.params.id)));
  router.post('/jobs/:id/heartbeat', requireAuth, (req, res) => res.json(persist.heartbeat(req.params.id, req.body || {})));
  router.post('/jobs/:id/checkpoint', requireAuth, (req, res) => res.json(persist.writeCheckpoint(req.params.id, req.body?.name, req.body?.data ?? {})));
  router.post('/jobs/:id/collect', requireAuth, (req, res) => res.json(persist.collectArtifact(req.params.id, req.body || {})));
  router.post('/jobs/:id/force-sync', requireAuth, (req, res) => res.json(persist.forceSync(req.params.id, req.body?.from_dir)));
  router.get('/jobs/:id/recover', requireAuth, (req, res) => res.json(persist.recover(req.params.id)));
  router.post('/jobs/:id/safe-teardown', requireAuth, (req, res) => {
    const r = persist.safeTeardown(req.params.id, { force: req.body?.force === true });
    res.status(r.ok ? 200 : 409).json(r);
  });

  router.post('/stop-job', requireAuth, (req, res) => {
    const r = cf.stopJob(String(req.body?.id || ''));
    res.status(r.ok ? 200 : 404).json(r);
  });

  router.get('/jobs', requireAuth, (_req, res) => {
    res.json({ ok: true, jobs: cf.listJobs() });
  });

  router.get('/spend', requireAuth, (_req, res) => {
    res.json({ ok: true, ...cf.spend() });
  });

  router.get('/audit', requireAuth, (req, res) => {
    res.json({ ok: true, events: cf.auditTail(Number(req.query.limit) || 100) });
  });

  return router;
};
