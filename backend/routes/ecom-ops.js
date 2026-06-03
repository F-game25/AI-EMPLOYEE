'use strict';
/**
 * /api/ecom — E-commerce product research and shortlist management.
 * All business logic lives in runtime/core/product_researcher.py
 * and runtime/agents/product-scout/product_scout.py.
 * This file only shuttles JSON between HTTP and those Python modules.
 */

const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const REPO_ROOT   = path.resolve(__dirname, '..', '..');
const RUNTIME_DIR = path.join(REPO_ROOT, 'runtime');
const AI_HOME     = path.resolve(
  process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
);

const PRODUCTS_FILE = path.join(AI_HOME, 'state', 'ecom_products.json');
const RESEARCH_FILE = path.join(AI_HOME, 'state', 'product_research.json');
const STATE_DIR     = path.join(AI_HOME, 'state');

const AGENT_DIR = path.join(REPO_ROOT, 'runtime', 'agents', 'ecom-agent');

// pyCallWithAgent: same as pyCall but also adds the ecom-agent dir to sys.path
// so that ecom_agent.py can be imported directly.
function pyCallAgent(snippet, timeoutMs = 90_000) {
  return new Promise((resolve, reject) => {
    const script = `
import sys, os
sys.path.insert(0, ${JSON.stringify(RUNTIME_DIR)})
sys.path.insert(0, ${JSON.stringify(AGENT_DIR)})
os.environ.setdefault('AI_HOME', ${JSON.stringify(AI_HOME)})
import json
${snippet}
`;
    let stdout = '';
    let stderr = '';
    const child = spawn(process.env.PYTHON_BIN || 'python3', ['-c', script], {
      env: { ...process.env, AI_HOME, PYTHONPATH: RUNTIME_DIR },
      timeout: timeoutMs,
    });
    child.stdout.on('data', d => { stdout += d; });
    child.stderr.on('data', d => { stderr += d; });
    child.on('close', code => {
      if (code !== 0) return reject(new Error(`Python error (${code}): ${stderr.slice(0, 400)}`));
      try {
        const line = stdout.trim().split('\n').pop() || '{}';
        resolve(JSON.parse(line));
      } catch {
        reject(new Error(`Could not parse Python output: ${stdout.slice(0, 200)}`));
      }
    });
    child.on('error', err => reject(err));
  });
}

// Run a one-shot Python snippet with sys.path pre-loaded.
// Returns parsed JSON output (last line of stdout) or throws.
function pyCall(snippet, timeoutMs = 90_000) {
  return new Promise((resolve, reject) => {
    const script = `
import sys, os
sys.path.insert(0, ${JSON.stringify(RUNTIME_DIR)})
os.environ.setdefault('AI_HOME', ${JSON.stringify(AI_HOME)})
import json
${snippet}
`;
    let stdout = '';
    let stderr = '';
    const child = spawn(process.env.PYTHON_BIN || 'python3', ['-c', script], {
      env: { ...process.env, AI_HOME, PYTHONPATH: RUNTIME_DIR },
      timeout: timeoutMs,
    });
    child.stdout.on('data', d => { stdout += d; });
    child.stderr.on('data', d => { stderr += d; });
    child.on('close', code => {
      if (code !== 0) return reject(new Error(`Python error (${code}): ${stderr.slice(0, 400)}`));
      try {
        const line = stdout.trim().split('\n').pop() || '{}';
        resolve(JSON.parse(line));
      } catch {
        reject(new Error(`Could not parse Python output: ${stdout.slice(0, 200)}`));
      }
    });
    child.on('error', err => reject(err));
  });
}

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
      const snippet = `
from core.product_researcher import research_products
result = research_products(${JSON.stringify(niche)}, ${JSON.stringify(markt)}, ${parseInt(min_marge, 10) || 30})
print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCall(snippet, 90_000);
      res.status(result.ok ? 200 : 500).json(result);
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
      const snippet = `
import sys, os
sys.path.insert(0, ${JSON.stringify(RUNTIME_DIR)})
os.environ.setdefault('AI_HOME', ${JSON.stringify(AI_HOME)})
import json
from agents.product_scout.product_scout import ProductScoutAgent
agent = ProductScoutAgent()
result = agent.execute({"markt": ${JSON.stringify(markt)}, "min_marge": ${parseInt(min_marge, 10) || 30}})
print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCall(snippet, 90_000);
      res.status(result.ok ? 200 : 500).json(result);
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
      if (!product_naam || !product_naam.trim()) {
        return res.status(400).json({ ok: false, error: 'product_naam is verplicht' });
      }
      const snippet = `
from ecom_agent import genereer_en_sla_op
result = genereer_en_sla_op(${JSON.stringify(product_naam.trim())}, platform=${JSON.stringify(platform)})
print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCallAgent(snippet, 60_000);
      res.status(result && result.ok === false ? 500 : 201).json({ ok: true, listing: result });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/listings — list all listings (optionally ?status=concept|goedgekeurd|gepubliceerd)
  r.get('/ecom/listings', requireAuth, async (req, res) => {
    try {
      const status = req.query.status || null;
      const snippet = `
from core.ecom_listing_store import listings_ophalen
result = listings_ophalen(${status ? `status=${JSON.stringify(status)}` : ''})
print(json.dumps(result, ensure_ascii=False))
`;
      const listings = await pyCall(snippet, 10_000);
      res.json({ ok: true, listings });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/listings/:id — single listing
  // NOTE: must be declared after /ecom/listings (exact) to avoid shadowing
  r.get('/ecom/listings/:id', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.ecom_listing_store import listing_ophalen
result = listing_ophalen(${JSON.stringify(id)})
print(json.dumps(result, ensure_ascii=False))
`;
      const listing = await pyCall(snippet, 10_000);
      if (!listing || (typeof listing === 'object' && listing.ok === false)) {
        return res.status(404).json({ ok: false, error: 'Listing niet gevonden' });
      }
      res.json({ ok: true, listing });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // PATCH /api/ecom/listings/:id — update editable fields
  r.patch('/ecom/listings/:id', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const velden = req.body || {};
      const snippet = `
from core.ecom_listing_store import listing_bijwerken
result = listing_bijwerken(${JSON.stringify(id)}, **${JSON.stringify(velden)})
print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCall(snippet, 10_000);
      res.status(result && result.ok === false ? 400 : 200).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/listings/:id/approve — HITL: human approves listing (status → goedgekeurd)
  r.post('/ecom/listings/:id/approve', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.ecom_listing_store import listing_ophalen, listing_status_bijwerken
listing = listing_ophalen(${JSON.stringify(id)})
if not listing or (isinstance(listing, dict) and listing.get('ok') is False):
  print(json.dumps({"ok": False, "error": "Listing niet gevonden"}))
elif listing.get('status') == 'gepubliceerd':
  print(json.dumps({"ok": False, "error": "Listing is al gepubliceerd"}))
else:
  result = listing_status_bijwerken(${JSON.stringify(id)}, 'goedgekeurd')
  print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCall(snippet, 10_000);
      res.status(result && result.ok === false ? 400 : 200).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/listings/:id/emails — generate + persist email flow for listing
  r.post('/ecom/listings/:id/emails', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const { type = 'welcome' } = req.body || {};
      const snippet = `
from ecom_agent import genereer_email_flow_en_sla_op
result = genereer_email_flow_en_sla_op(${JSON.stringify(id)}, ${JSON.stringify(type)})
print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCallAgent(snippet, 60_000);
      res.status(result && result.ok === false ? 500 : 201).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/ecom/listings/:id/ads — generate + persist Facebook + Google ads for listing
  r.post('/ecom/listings/:id/ads', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from ecom_agent import genereer_ads_en_sla_op
result = genereer_ads_en_sla_op(${JSON.stringify(id)})
print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCallAgent(snippet, 60_000);
      res.status(result && result.ok === false ? 500 : 201).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/ecom/listings/:id/export — download listing as plain text
  r.get('/ecom/listings/:id/export', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.ecom_listing_store import listing_ophalen
result = listing_ophalen(${JSON.stringify(id)})
print(json.dumps(result, ensure_ascii=False))
`;
      const listing = await pyCall(snippet, 10_000);
      if (!listing || (typeof listing === 'object' && listing.ok === false)) {
        return res.status(404).json({ ok: false, error: 'Listing niet gevonden' });
      }
      const exportText = listing.export_tekst
        || [
            listing.titel || '',
            '',
            listing.beschrijving || '',
            '',
            'Bullets:',
            ...(listing.bullets || []).map(b => `- ${b}`),
            '',
            `Tags: ${(listing.tags || []).join(', ')}`,
            `Prijs: €${listing.prijs || 0}`,
          ].join('\n');
      res.setHeader('Content-Type', 'text/plain; charset=utf-8');
      res.setHeader('Content-Disposition', `attachment; filename="listing-${id}.txt"`);
      res.send(exportText);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // DELETE /api/ecom/listings/:id — remove a listing
  r.delete('/ecom/listings/:id', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.ecom_listing_store import listing_verwijderen
result = listing_verwijderen(${JSON.stringify(id)})
print(json.dumps(result, ensure_ascii=False))
`;
      const result = await pyCall(snippet, 10_000);
      res.status(result && result.ok === false ? 404 : 200).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  return r;
};
