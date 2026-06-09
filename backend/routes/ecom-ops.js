'use strict';
/**
 * /api/ecom — E-commerce product research and shortlist management.
 * All business logic lives in runtime/core/product_researcher.py
 * and runtime/agents/ecom-agent/ecom_agent.py.
 * Python calls go through the persistent worker; pure-JS routes stay as-is.
 */

const express = require('express');
const path = require('path');
const os = require('os');
const fs = require('fs');
const { getWorker } = require('../py_worker_client');

const AI_HOME = path.resolve(
  process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
);

const PRODUCTS_FILE = path.join(AI_HOME, 'state', 'ecom_products.json');
const RESEARCH_FILE = path.join(AI_HOME, 'state', 'product_research.json');

const w = () => getWorker();

// Atomic JSON write: write .tmp then rename.
function writeJsonAtomic(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = filePath + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
  fs.renameSync(tmp, filePath);
}

function readJsonSafe(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

module.exports = function createEcomOpsRouter(deps) {
  // deps may expose requireAuth — fall through with no-op if unavailable
  const requireAuth = (deps && deps.requireAuth) ? deps.requireAuth : (_req, _res, next) => next();
  const r = express.Router();

  // POST /api/ecom/research — run product research for a niche
  r.post('/ecom/research', requireAuth, async (req, res) => {
    try {
      const { niche, markt = 'nl', min_marge = 30 } = req.body || {};
      if (!niche) return res.status(400).json({ ok: false, error: 'niche is verplicht' });
      const result = await w().call('ecom.research', {
        niche, markt, min_marge: parseInt(min_marge, 10) || 30,
      }, 90_000);
      res.status(result?.ok ? 200 : 500).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/research — return last 50 research results from product_research.json
  r.get('/ecom/research', requireAuth, (req, res) => {
    try {
      const entries = readJsonSafe(RESEARCH_FILE, []);
      const list = Array.isArray(entries) ? entries.slice(0, 50) : [];
      res.json({ ok: true, entries: list, total: list.length });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/scout/run — run product scout (HITL gate required for high-scorers)
  r.post('/ecom/scout/run', requireAuth, async (req, res) => {
    try {
      const { markt = 'nl', min_marge = 30 } = req.body || {};
      const result = await w().call('ecom.scout', {
        markt, min_marge: parseInt(min_marge, 10) || 30,
      }, 90_000);
      res.status(result?.ok ? 200 : 500).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/products — return approved product shortlist
  r.get('/ecom/products', requireAuth, (req, res) => {
    try {
      const data = readJsonSafe(PRODUCTS_FILE, { products: [] });
      const products = Array.isArray(data.products) ? data.products : [];
      res.json({ ok: true, products, total: products.length });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/products — add product to approved shortlist
  r.post('/ecom/products', requireAuth, (req, res) => {
    try {
      const product = req.body || {};
      if (!product.naam) return res.status(400).json({ ok: false, error: 'naam is verplicht' });

      const data = readJsonSafe(PRODUCTS_FILE, { products: [] });
      if (!Array.isArray(data.products)) data.products = [];

      const id = `prod-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const entry = {
        id,
        naam: product.naam,
        niche: product.niche || '',
        status: product.status || 'shortlist',
        aankoopprijs: product.aankoopprijs || product.aankoopprijs_est || 0,
        verkoopprijs: product.verkoopprijs || product.verkoopprijs_est || 0,
        marge_pct: product.marge_pct || 0,
        supplier: product.supplier || '',
        bronnen: product.bronnen || [],
        demand: product.demand || 0,
        marge: product.marge || 0,
        concurrentie: product.concurrentie || 0,
        opmerking: product.opmerking || '',
        toegevoegd_op: new Date().toISOString(),
      };

      data.products.unshift(entry);
      writeJsonAtomic(PRODUCTS_FILE, data);
      res.status(201).json({ ok: true, product: entry });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // PATCH /api/ecom/products/:id — edit product (status, prijs, supplier)
  r.patch('/ecom/products/:id', requireAuth, (req, res) => {
    try {
      const { id } = req.params;
      const updates = req.body || {};

      const data = readJsonSafe(PRODUCTS_FILE, { products: [] });
      if (!Array.isArray(data.products)) data.products = [];

      const idx = data.products.findIndex(p => p.id === id);
      if (idx === -1) return res.status(404).json({ ok: false, error: 'product niet gevonden' });

      const allowed = ['status', 'aankoopprijs', 'verkoopprijs', 'marge_pct', 'supplier', 'opmerking'];
      for (const key of allowed) {
        if (key in updates) data.products[idx][key] = updates[key];
      }
      data.products[idx].bijgewerkt_op = new Date().toISOString();

      writeJsonAtomic(PRODUCTS_FILE, data);
      res.json({ ok: true, product: data.products[idx] });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── Listing store routes (Track 2) ──────────────────────────────────────────

  // POST /api/ecom/listings — generate listing via LLM + persist to SQLite
  r.post('/ecom/listings', requireAuth, async (req, res) => {
    try {
      const { product_naam, platform = 'shopify' } = req.body || {};
      if (!product_naam?.trim())
        return res.status(400).json({ ok: false, error: 'product_naam is verplicht' });
      const result = await w().call('ecom.listing.create', {
        product_naam: product_naam.trim(), platform,
      }, 60_000);
      res.status(result?.ok === false ? 500 : 201).json({ ok: true, listing: result });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/listings
  r.get('/ecom/listings', requireAuth, async (req, res) => {
    try {
      const listings = await w().call('ecom.listing.list', { status: req.query.status || null }, 10_000);
      res.json({ ok: true, listings });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/listings/:id
  r.get('/ecom/listings/:id', requireAuth, async (req, res) => {
    try {
      const listing = await w().call('ecom.listing.get', { id: req.params.id }, 10_000);
      if (!listing || listing?.ok === false)
        return res.status(404).json({ ok: false, error: 'Listing niet gevonden' });
      res.json({ ok: true, listing });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // PATCH /api/ecom/listings/:id
  r.patch('/ecom/listings/:id', requireAuth, async (req, res) => {
    try {
      const result = await w().call('ecom.listing.update', { id: req.params.id, ...(req.body || {}) }, 10_000);
      res.status(result?.ok === false ? 400 : 200).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/listings/:id/approve
  r.post('/ecom/listings/:id/approve', requireAuth, async (req, res) => {
    try {
      const result = await w().call('ecom.listing.approve', { id: req.params.id }, 10_000);
      res.status(result?.ok === false ? 400 : 200).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/listings/:id/emails
  r.post('/ecom/listings/:id/emails', requireAuth, async (req, res) => {
    try {
      const result = await w().call('ecom.listing.emails', {
        id: req.params.id, type: req.body?.type || 'welcome',
      }, 60_000);
      res.status(result?.ok === false ? 500 : 201).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/listings/:id/ads
  r.post('/ecom/listings/:id/ads', requireAuth, async (req, res) => {
    try {
      const result = await w().call('ecom.listing.ads', { id: req.params.id }, 60_000);
      res.status(result?.ok === false ? 500 : 201).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/listings/:id/export
  r.get('/ecom/listings/:id/export', requireAuth, async (req, res) => {
    try {
      const listing = await w().call('ecom.listing.get', { id: req.params.id }, 10_000);
      if (!listing || listing?.ok === false)
        return res.status(404).json({ ok: false, error: 'Listing niet gevonden' });
      const exportText = listing.export_tekst || [
        listing.titel || '', '',
        listing.beschrijving || '', '',
        'Bullets:', ...(listing.bullets || []).map(b => `- ${b}`), '',
        `Tags: ${(listing.tags || []).join(', ')}`,
        `Prijs: €${listing.prijs || 0}`,
      ].join('\n');
      res.setHeader('Content-Type', 'text/plain; charset=utf-8');
      res.setHeader('Content-Disposition', `attachment; filename="listing-${req.params.id}.txt"`);
      res.send(exportText);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // DELETE /api/ecom/listings/:id
  r.delete('/ecom/listings/:id', requireAuth, async (req, res) => {
    try {
      const result = await w().call('ecom.listing.delete', { id: req.params.id }, 10_000);
      res.status(result?.ok === false ? 404 : 200).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  return r;
};
