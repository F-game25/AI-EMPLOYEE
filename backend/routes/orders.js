'use strict';
/**
 * /api/orders — Website-sales pipeline for Lars.
 * All business logic lives in runtime/core/{orders_store,demo_flow,pitch}.py.
 * This file only shuttles JSON between HTTP and the persistent Python worker.
 */

const express = require('express');
const path = require('path');
const { getWorker } = require('../py_worker_client');

// Public base URL for demo links sent to customers.
const BASE_URL = (process.env.BASE_URL || '').replace(/\/$/, '');

const w = () => getWorker(); // resolved lazily so the module loads before the worker is ready

module.exports = function createOrdersRouter(requireAuth) {
  const r = express.Router();

  // POST /api/orders/search
  r.post('/search', requireAuth, async (req, res) => {
    try {
      const { stad, branche, aantal = 8 } = req.body || {};
      if (!stad || !branche)
        return res.status(400).json({ ok: false, error: 'stad en branche zijn verplicht' });
      const result = await w().call('orders.search', {
        stad, branche, aantal: Math.min(20, Math.max(1, parseInt(aantal, 10) || 8)),
      }, 120_000);
      res.status(result?.ok ? 200 : 500).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // GET /api/orders/hosting/status — MUST be before /:id
  r.get('/hosting/status', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.hosting_status', {}, 10_000);
      res.json(result);
    } catch (err) {
      res.json({ has_token: false, error: err.message });
    }
  });

  // GET /api/orders
  r.get('/', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.list', { status: req.query.status || null });
      res.json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // GET /api/orders/:id
  r.get('/:id', requireAuth, async (req, res) => {
    try {
      const order = await w().call('orders.get', { id: req.params.id });
      if (!order) return res.status(404).json({ ok: false, error: 'Order niet gevonden' });
      res.json({ ok: true, order });
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders
  r.post('/', requireAuth, async (req, res) => {
    try {
      const { bedrijfsnaam, plaats, branche, contact = '', prijs = 299.0 } = req.body || {};
      if (!bedrijfsnaam || !plaats || !branche)
        return res.status(400).json({ ok: false, error: 'bedrijfsnaam, plaats en branche zijn verplicht' });
      const prijsNum = parseFloat(prijs);
      if (!Number.isFinite(prijsNum) || prijsNum <= 0)
        return res.status(400).json({ ok: false, error: 'prijs moet een positief getal zijn' });
      const order = await w().call('orders.create', { bedrijfsnaam, plaats, branche, contact, prijs: prijsNum });
      res.status(201).json({ ok: true, order });
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/research
  r.post('/:id/research', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.research', { id: req.params.id }, 30_000);
      res.status(result?.ok ? 200 : 500).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/research-data — persist finder website into research_data
  r.post('/:id/research-data', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.research_data', {
        id: req.params.id,
        research_data: req.body?.research_data || {},
      }, 10_000);
      res.json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/demo
  r.post('/:id/demo', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.demo', { id: req.params.id }, 120_000);
      res.status(result?.ok ? 200 : 500).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/approve
  r.post('/:id/approve', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.approve', { id: req.params.id });
      res.status(result?.ok ? 200 : 400).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/pitch
  r.post('/:id/pitch', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      let demo_url = req.body?.demo_url || '';
      if (!demo_url) {
        try {
          const order = await w().call('orders.get', { id }, 10_000);
          const fname = (order?.demo_pad || '').split('/').pop();
          if (fname) {
            const host = BASE_URL || (req.protocol + '://' + req.get('host'));
            demo_url = `${host}/api/demos/${fname}`;
          }
        } catch { /* non-fatal */ }
      }
      const result = await w().call('orders.pitch', { id, demo_url }, 120_000);
      res.status(result?.ok ? 200 : 400).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/akkoord
  r.post('/:id/akkoord', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.akkoord', { id: req.params.id });
      res.status(result?.ok ? 200 : 400).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/betaald — confirm payment with PayPal transaction ID
  r.post('/:id/betaald', requireAuth, async (req, res) => {
    try {
      const { referentie = '' } = req.body || {};
      const result = await w().call('orders.betaald', { id: req.params.id, referentie }, 15_000);
      res.status(result?.ok ? 200 : 400).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/demo-quality — heuristic quality gate on generated demo HTML
  r.post('/:id/demo-quality', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.demo_quality', { id: req.params.id }, 30_000);
      res.status(result?.ok ? 200 : 500).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // GET /api/orders/:id/resource-plan — compute backend recommendation for Forge build
  r.get('/:id/resource-plan', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.resource_plan', { id: req.params.id }, 15_000);
      res.status(result?.ok ? 200 : 500).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/forge-handoff — create Ascend Forge V5 project from approved order
  // Body: { override_payment?: boolean } — set true to send to Forge even without betaald status
  r.post('/:id/forge-handoff', requireAuth, async (req, res) => {
    try {
      const host = (process.env.BASE_URL || '').replace(/\/$/, '') || (req.protocol + '://' + req.get('host'));
      const overridePayment = !!(req.body?.override_payment);
      const result = await w().call('orders.forge_handoff', { id: req.params.id, base_url: host, override_payment: overridePayment }, 120_000);
      res.status(result?.ok ? 200 : 400).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/status
  r.post('/:id/status', requireAuth, async (req, res) => {
    try {
      const { status: newStatus } = req.body || {};
      const ALLOWED = ['gepitcht', 'betaald', 'live'];
      if (!ALLOWED.includes(newStatus))
        return res.status(400).json({ ok: false, error: `Status moet een van ${ALLOWED.join('/')} zijn` });
      const result = await w().call('orders.status', { id: req.params.id, status: newStatus });
      res.status(result?.ok ? 200 : 400).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // POST /api/orders/:id/deploy
  r.post('/:id/deploy', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.deploy', { id: req.params.id }, 60_000);
      const httpStatus = result?.ok ? 200 : (result?.error?.includes('NETLIFY_API_TOKEN') ? 400 : 500);
      res.status(httpStatus).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  // DELETE /api/orders/:id
  r.delete('/:id', requireAuth, async (req, res) => {
    try {
      const result = await w().call('orders.delete', { id: req.params.id }, 10_000);
      res.status(result?.ok ? 200 : 404).json(result);
    } catch (err) { res.status(500).json({ ok: false, error: err.message }); }
  });

  return r;
};
