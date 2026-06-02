'use strict';
/**
 * /api/orders — Website-sales pipeline for Lars.
 * All business logic lives in runtime/core/{orders_store,demo_flow,pitch}.py.
 * This file only shuttles JSON between HTTP and those Python modules.
 */

const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const RUNTIME_DIR = path.join(REPO_ROOT, 'runtime');
const AI_HOME = path.resolve(
  process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee')
);

// Public base URL for demo links sent to customers.
// Set BASE_URL in .env to your domain or ngrok tunnel for production use.
// Falls back to reading the request host (breaks behind reverse proxies without this).
const BASE_URL = (process.env.BASE_URL || '').replace(/\/$/, '');

// Run a one-shot Python snippet with sys.path pre-loaded.
// Returns parsed JSON output or throws.
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

// Build the public, clickable demo URL from a stored demo_pad.
// Handles both multi-page folder demos (.../<slug>/index.html -> /api/demos/<slug>/)
// and legacy single-file demos (.../<file>.html -> /api/demos/<file>.html).
function demoUrlFromPad(demoPad, host) {
  if (!demoPad) return '';
  const parts = String(demoPad).split('/').filter(Boolean);
  const base = parts[parts.length - 1] || '';
  if (base === 'index.html') {
    const slug = parts[parts.length - 2] || '';
    return slug ? `${host}/api/demos/${slug}/` : '';
  }
  if (base.endsWith('.html')) return `${host}/api/demos/${base}`;      // legacy single file
  return `${host}/api/demos/${base}/`;                                  // folder path
}

// Photo upload → demos/_assets/<orderId>/, served publicly at /api/demos/_assets/...
const DEMOS_ASSETS_DIR = path.join(AI_HOME, 'state', 'artifacts', 'demos', '_assets');
const _IMAGE_EXT = new Set(['.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif']);
const photoUpload = require('multer')({
  storage: require('multer').diskStorage({
    destination: (req, _f, cb) => {
      const d = path.join(DEMOS_ASSETS_DIR, path.basename(req.params.id));
      fs.mkdirSync(d, { recursive: true });
      cb(null, d);
    },
    filename: (_r, file, cb) => {
      const ext = path.extname(file.originalname).toLowerCase();
      const base = path.basename(file.originalname, ext).replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 60) || 'foto';
      cb(null, `${Date.now()}-${base}${ext}`);
    },
  }),
  fileFilter: (_r, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (!_IMAGE_EXT.has(ext)) return cb(new Error(`Bestandstype '${ext}' niet toegestaan (alleen afbeeldingen)`));
    cb(null, true);
  },
  limits: { fileSize: 10 * 1024 * 1024, files: 10 },
});

module.exports = function createOrdersRouter(requireAuth) {
  const r = express.Router();

  // POST /api/orders/search — zoek lokale bedrijfskandidaten via Ollama
  r.post('/search', requireAuth, async (req, res) => {
    try {
      const { stad, branche, aantal = 8 } = req.body || {};
      if (!stad || !branche) {
        return res.status(400).json({ ok: false, error: 'stad en branche zijn verplicht' });
      }
      const aantalNum = Math.min(20, Math.max(1, parseInt(aantal, 10) || 8));
      const snippet = `
from core.bedrijf_finder import zoek_bedrijven
result = zoek_bedrijven(${JSON.stringify(stad)}, ${JSON.stringify(branche)}, ${aantalNum})
print(json.dumps(result))
`;
      const result = await pyCall(snippet, 120_000);
      const status = result.ok ? 200 : 500;
      res.status(status).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/orders — list all orders
  r.get('/', requireAuth, async (req, res) => {
    try {
      const status = req.query.status || null;
      const snippet = `
from core.orders_store import orders_ophalen
result = orders_ophalen(${status ? `status=${JSON.stringify(status)}` : ''})
print(json.dumps(result))
`;
      const orders = await pyCall(snippet);
      res.json({ ok: true, orders });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/orders/hosting/status — is NETLIFY_API_TOKEN ingesteld? (UI gate't de deploy-knop)
  // MOET vóór '/:id' staan, anders vangt de :id-route 'hosting' op.
  r.get('/hosting/status', requireAuth, async (req, res) => {
    try {
      const snippet = `
import os
print(json.dumps({"has_token": bool(os.environ.get("NETLIFY_API_TOKEN", ""))}))
`;
      const result = await pyCall(snippet, 10_000);
      res.json(result);
    } catch (err) {
      // Bij twijfel: meld geen token, zodat de UI veilig blijft (knop disabled).
      res.json({ has_token: false, error: err.message });
    }
  });

  // GET /api/orders/:id — single order
  r.get('/:id', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.orders_store import order_ophalen
result = order_ophalen(${JSON.stringify(id)})
print(json.dumps(result))
`;
      const order = await pyCall(snippet);
      if (!order) return res.status(404).json({ ok: false, error: 'Order niet gevonden' });
      res.json({ ok: true, order });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders — create order
  r.post('/', requireAuth, async (req, res) => {
    try {
      const { bedrijfsnaam, plaats, branche, contact = '', prijs = 299.0 } = req.body || {};
      if (!bedrijfsnaam || !plaats || !branche) {
        return res.status(400).json({ ok: false, error: 'bedrijfsnaam, plaats en branche zijn verplicht' });
      }
      // Sanitize prijs: must be a finite positive number — NaN/Infinity would inject as Python tokens
      const prijsNum = parseFloat(prijs)
      if (!Number.isFinite(prijsNum) || prijsNum <= 0) {
        return res.status(400).json({ ok: false, error: 'prijs moet een positief getal zijn' });
      }
      const snippet = `
from core.orders_store import order_aanmaken
result = order_aanmaken(
  bedrijfsnaam=${JSON.stringify(bedrijfsnaam)},
  plaats=${JSON.stringify(plaats)},
  branche=${JSON.stringify(branche)},
  contact=${JSON.stringify(contact)},
  prijs=${prijsNum},
)
print(json.dumps(result))
`;
      const order = await pyCall(snippet);
      res.status(201).json({ ok: true, order });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/research — research real business info (HITL: Lars klikt)
  r.post('/:id/research', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.orders_store import order_ophalen, _conn
from core.bedrijf_research import research_bedrijf
import json
order = order_ophalen(${JSON.stringify(id)})
if not order:
  print(json.dumps({"ok": False, "error": "Order niet gevonden"}))
else:
  try:
    existing = json.loads(order.get('research_data') or '{}')
    if not isinstance(existing, dict): existing = {}
  except Exception:
    existing = {}
  data = research_bedrijf(order['bedrijfsnaam'], order['plaats'], website=existing.get('website'))
  # Merge: keep Lars's earlier non-empty fields; new findings only fill/overwrite where non-empty.
  merged = dict(existing)
  for k, v in data.items():
    if v not in (None, "", []):
      merged[k] = v
  try:
    with _conn() as conn:
      conn.execute("UPDATE orders SET research_data=? WHERE id=?", (json.dumps(merged, ensure_ascii=False), ${JSON.stringify(id)}))
  except Exception as exc:
    pass  # non-fatal — data still returned
  print(json.dumps({"ok": True, "research_data": merged}))
`;
      const result = await pyCall(snippet, 30_000);
      res.status(result.ok ? 200 : 500).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/research-data — persist USER-EDITED research (real info only)
  r.post('/:id/research-data', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const data = (req.body && typeof req.body.research_data === 'object') ? req.body.research_data : {};
      const snippet = `
from core.orders_store import research_data_opslaan
result = research_data_opslaan(${JSON.stringify(id)}, ${JSON.stringify(data)})
print(json.dumps(result))
`;
      const result = await pyCall(snippet, 10_000);
      res.status(result.ok ? 200 : 404).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/update — edit core order fields (bedrijfsnaam/plaats/branche/contact/prijs)
  r.post('/:id/update', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const velden = {};
      for (const k of ['bedrijfsnaam', 'plaats', 'branche', 'contact', 'prijs']) {
        if (req.body && k in req.body) velden[k] = req.body[k];
      }
      const snippet = `
from core.orders_store import order_velden_bijwerken
result = order_velden_bijwerken(${JSON.stringify(id)}, ${JSON.stringify(velden)})
print(json.dumps(result))
`;
      const result = await pyCall(snippet, 10_000);
      res.status(result.ok ? 200 : 400).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/photo — upload business photo(s) (multipart field 'photos')
  r.post('/:id/photo', requireAuth, (req, res) => {
    photoUpload.array('photos', 10)(req, res, (err) => {
      if (err) return res.status(400).json({ ok: false, error: err.message });
      const id = path.basename(req.params.id);
      const urls = (req.files || []).map(f => `/api/demos/_assets/${id}/${f.filename}`);
      res.json({ ok: true, urls });
    });
  });

  // POST /api/orders/:id/demo — generate demo website, set status ter_review
  r.post('/:id/demo', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.orders_store import order_ophalen, status_bijwerken
from core.demo_generator import genereer_demo
order = order_ophalen(${JSON.stringify(id)})
if not order:
  print(json.dumps({"ok": False, "error": "Order niet gevonden"}))
else:
  _rd = {}
  try:
    _rd = json.loads(order.get('research_data') or '{}')
    if not isinstance(_rd, dict): _rd = {}
  except Exception:
    _rd = {}
  gen = genereer_demo(
    bedrijfsnaam=order['bedrijfsnaam'],
    plaats=order['plaats'],
    branche=order['branche'],
    diensten=None,
    research_data=_rd,
    job_id=order['id'],
  )
  if gen['status'] == 'ok':
    order = status_bijwerken(${JSON.stringify(id)}, 'demo_klaar', demo_pad=gen['path'])
    order = status_bijwerken(${JSON.stringify(id)}, 'ter_review')
    print(json.dumps({"ok": True, "order": order, "demo_pad": gen['path'], "pages": gen.get('pages'), "theme": gen.get('theme'), "bytes": gen['bytes']}))
  else:
    print(json.dumps({"ok": False, "error": gen.get('error', 'Generatie mislukt')}))
`;
      const result = await pyCall(snippet, 120_000);
      const status = result.ok ? 200 : 500;
      res.status(status).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/approve — Lars keurt de demo goed (HITL door UI-klik)
  r.post('/:id/approve', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      // The human in the loop IS Lars clicking this button.
      // We set status directly; no in-memory HITL gate lookup needed.
      const snippet = `
from core.orders_store import order_ophalen, status_bijwerken
order = order_ophalen(${JSON.stringify(id)})
if not order:
  print(json.dumps({"ok": False, "error": "Order niet gevonden"}))
elif order['status'] not in ('ter_review', 'demo_klaar'):
  print(json.dumps({"ok": False, "error": f"Verwacht status ter_review/demo_klaar, is: {order['status']}"}))
else:
  order = status_bijwerken(${JSON.stringify(id)}, 'goedgekeurd')
  print(json.dumps({"ok": True, "order": order}))
`;
      const result = await pyCall(snippet);
      const status = result.ok ? 200 : 400;
      res.status(status).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/pitch — generate pitch text
  r.post('/:id/pitch', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      // Build a real clickable URL from the order's demo_pad so the pitch text
      // contains something the customer can actually open (not a filesystem path).
      let demo_url = req.body?.demo_url || '';
      if (!demo_url) {
        try {
          const orderSnippet = `
from core.orders_store import order_ophalen
o = order_ophalen(${JSON.stringify(id)})
import json; print(json.dumps(o or {}))
`;
          const orderData = await pyCall(orderSnippet, 10_000);
          // No token — demos are publicly accessible so customers can open them
          const host = BASE_URL || (req.protocol + '://' + req.get('host'));
          demo_url = demoUrlFromPad(orderData.demo_pad, host);
        } catch { /* fall through — demo_url stays empty */ }
      }
      const snippet = `
from core.pitch import genereer_pitch
result = genereer_pitch(${JSON.stringify(id)}, demo_url=${JSON.stringify(demo_url)})
print(json.dumps(result))
`;
      const result = await pyCall(snippet, 120_000);
      const status = result.ok ? 200 : 400;
      res.status(status).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/akkoord — klant heeft akkoord gegeven, genereer vervolgbericht
  r.post('/:id/akkoord', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.pitch import markeer_akkoord
result = markeer_akkoord(${JSON.stringify(id)})
print(json.dumps(result))
`;
      const result = await pyCall(snippet);
      const httpStatus = result.ok ? 200 : 400;
      res.status(httpStatus).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/betaald — mark as paid; requires PayPal transaction reference
  r.post('/:id/betaald', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const { referentie } = req.body || {};
      if (!referentie || !referentie.trim()) {
        return res.status(400).json({
          ok: false,
          error: 'Vul de PayPal-transactiereferentie in. Je vindt deze in je PayPal-account onder Activiteit → de betaling → Transactie-ID.',
        });
      }
      const snippet = `
from core.pitch import markeer_betaald
result = markeer_betaald(${JSON.stringify(id)}, referentie=${JSON.stringify(referentie.trim())})
print(json.dumps(result))
`;
      const result = await pyCall(snippet);
      res.status(result.ok ? 200 : 400).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/status — set status (gepitcht/live)
  r.post('/:id/status', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const { status: newStatus } = req.body || {};
      const ALLOWED = ['gepitcht', 'betaald', 'live'];
      if (!ALLOWED.includes(newStatus)) {
        return res.status(400).json({ ok: false, error: `Status moet een van ${ALLOWED.join('/')} zijn` });
      }
      const fnMap = { gepitcht: 'markeer_gepitcht', live: 'markeer_live' };
      if (newStatus === 'betaald') {
        return res.status(400).json({
          ok: false,
          error: 'Gebruik de /betaald route met een PayPal-transactiereferentie',
        });
      }
      const fn = fnMap[newStatus];
      const snippet = `
from core.pitch import ${fn}
result = ${fn}(${JSON.stringify(id)})
print(json.dumps(result))
`;
      const result = await pyCall(snippet);
      const httpStatus = result.ok ? 200 : 400;
      res.status(httpStatus).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // POST /api/orders/:id/deploy — deploy demo naar Netlify (HITL: Lars klikt)
  r.post('/:id/deploy', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.hosting import deploy_to_netlify
result = deploy_to_netlify(${JSON.stringify(id)})
print(json.dumps(result))
`;
      const result = await pyCall(snippet, 60_000);
      const httpStatus = result.ok ? 200 : (result.error?.includes('NETLIFY_API_TOKEN') ? 400 : 500);
      res.status(httpStatus).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // GET /api/orders/:id/stuur-link — generate WhatsApp/email/SMS share links (HITL: Lars klikt zelf)
  r.get('/:id/stuur-link', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.orders_store import order_ophalen
o = order_ophalen(${JSON.stringify(id)})
import json; print(json.dumps(o or {}))
`;
      const order = await pyCall(snippet, 10_000);
      if (!order || !order.id) return res.status(404).json({ ok: false, error: 'Order niet gevonden' });

      const host = BASE_URL || (req.protocol + '://' + req.get('host'));
      const demo_url = demoUrlFromPad(order.demo_pad, host);
      if (!demo_url) return res.status(400).json({ ok: false, error: 'Nog geen demo gegenereerd voor dit order' });
      const bedrijf = order.bedrijfsnaam || 'uw bedrijf';

      const waText = `Goedemiddag,\n\nIk heb een gratis demo-website gemaakt voor ${bedrijf}. U kunt deze hier bekijken:\n${demo_url}\n\nIk hoor graag wat u ervan vindt!\n\nMet vriendelijke groet,\nLars`;
      const emailSubject = `Uw nieuwe website — ${bedrijf}`;
      const emailBody = `Goedemiddag,\n\nIk heb een gratis demo-website gemaakt voor ${bedrijf}.\nBekijk hem hier: ${demo_url}\n\nIk hoor graag uw reactie.\n\nMet vriendelijke groet,\nLars`;

      res.json({
        ok: true,
        demo_url,
        whatsapp_url: `https://wa.me/?text=${encodeURIComponent(waText)}`,
        email_subject: emailSubject,
        email_body: emailBody,
        email_url: `mailto:?subject=${encodeURIComponent(emailSubject)}&body=${encodeURIComponent(emailBody)}`,
        sms_text: `Demo-website voor ${bedrijf}: ${demo_url}`,
      });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // DELETE /api/orders/:id — archive/delete an order (for dedup cleanup)
  r.delete('/:id', requireAuth, async (req, res) => {
    try {
      const { id } = req.params;
      const snippet = `
from core.orders_store import order_verwijderen
result = order_verwijderen(${JSON.stringify(id)})
print(json.dumps(result))
`;
      const result = await pyCall(snippet, 10_000);
      const status = result.ok ? 200 : 404;
      res.status(status).json(result);
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  return r;
};
