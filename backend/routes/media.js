'use strict';

const _mediaBuckets = new Map();

function rateLimit(req, res, next) {
  const rawIp = req.ip || req.connection?.remoteAddress || 'unknown';
  const now = Date.now();
  const windowMs = 60_000;
  const key = `media-demo-assets:${rawIp}`;
  const hits = (_mediaBuckets.get(key) || []).filter((ts) => now - ts < windowMs);
  hits.push(now);
  _mediaBuckets.set(key, hits);
  if (hits.length > 60) {
    res.set('Retry-After', String(Math.ceil(windowMs / 1000)));
    return res.status(429).json({ ok: false, error: 'Rate limit exceeded' });
  }
  next();
}

module.exports = function createMediaRouter(deps) {
  const router = require('express').Router();
  const { requireAuth, path, fs, AI_HOME, ARTIFACTS_DIR, readJsonLinesRecent, statePath } = deps;

  // GET /api/artifacts/:filename — download a named artifact (auth required)
  router.get('/artifacts/:filename', requireAuth, (req, res) => {
    const fname = path.basename(req.params.filename); // prevent path traversal
    const fpath = path.join(ARTIFACTS_DIR, fname);
    if (!require('fs').existsSync(fpath)) return res.status(404).json({ error: 'Artifact not found' });
    res.download(fpath);
  });

  // GET /api/preview/:filename — render HTML artifact inline
  // No auth cookie needed — token may arrive as query param for iframe src
  router.get('/preview/:filename', (req, res) => {
    const fname = path.basename(req.params.filename);
    if (!fname.endsWith('.html')) return res.status(400).send('Only HTML files can be previewed');
    const fpath = path.join(ARTIFACTS_DIR, fname);
    if (!fs.existsSync(fpath)) return res.status(404).send('Preview not found');
    // Validate JWT from query param (iframes cannot send Authorization headers)
    const token = req.query.token;
    if (token) {
      try {
        const jwt = require('jsonwebtoken');
        // Fail closed (no empty-secret fallback) and pin the signing algorithm.
        jwt.verify(token, process.env.JWT_SECRET_KEY, { algorithms: ['HS256'] });
      } catch {
        return res.status(401).send('Unauthorized');
      }
    } else {
      // Fall back to cookie-based auth check via requireAuth pattern
      const authHeader = req.headers.authorization;
      if (!authHeader) return res.status(401).send('Unauthorized');
    }
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('X-Frame-Options', 'SAMEORIGIN');
    res.send(fs.readFileSync(fpath, 'utf8'));
  });

  // GET /api/artifacts — list all stored artifact files
  router.get('/artifacts', requireAuth, (_req, res) => {
    const fs = require('fs');
    if (!fs.existsSync(ARTIFACTS_DIR)) return res.json([]);
    const files = fs.readdirSync(ARTIFACTS_DIR)
      .filter(f => fs.statSync(path.join(ARTIFACTS_DIR, f)).isFile())
      .map(f => ({ name: f, url: `/api/artifacts/${f}`, size: fs.statSync(path.join(ARTIFACTS_DIR, f)).size }));
    res.json(files);
  });

  // GET /api/proof/center — aggregated proof/artifact index from turns.jsonl
  router.get('/proof/center', requireAuth, (_req, res) => {
    const turns = readJsonLinesRecent(statePath('turns.jsonl'), 100);
    const artifactFiles = (() => {
      try {
        if (!fs.existsSync(ARTIFACTS_DIR)) return [];
        return fs.readdirSync(ARTIFACTS_DIR)
          .filter((name) => fs.statSync(path.join(ARTIFACTS_DIR, name)).isFile())
          .map((name) => {
            const stat = fs.statSync(path.join(ARTIFACTS_DIR, name));
            return {
              id: `artifact:${name}`,
              name,
              type: 'file',
              path: path.join(ARTIFACTS_DIR, name),
              url: `/api/artifacts/${encodeURIComponent(name)}`,
              source: 'artifact_storage',
              status: 'available',
              size: stat.size,
              created_at: stat.mtime.toISOString(),
            };
          })
          .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
      } catch {
        return [];
      }
    })();

    const proofItems = [];
    for (const turn of turns) {
      for (const item of [...(turn.proof || []), ...(turn.artifacts || [])]) {
        if (!item || typeof item !== 'object') continue;
        const name = item.name || item.label || item.type || 'proof item';
        proofItems.push({
          id: item.id || `${turn.turn_id || turn.task_id || 'turn'}:${proofItems.length + 1}`,
          task_id: item.task_id || turn.task_id || turn.taskId || null,
          turn_id: turn.turn_id || null,
          name,
          type: item.type || item.artifact_type || 'trace',
          path: item.path || null,
          url: item.url || null,
          source: item.source || turn.source || turn.compatibility_route || 'turn',
          status: item.status || turn.status || 'unknown',
          degraded: turn.degraded === true || item.status === 'fallback' || item.status === 'degraded',
          created_at: item.created_at || turn.created_at || turn.timestamp || null,
        });
      }
    }

    const counts = [...proofItems, ...artifactFiles].reduce((acc, item) => {
      const status = item.degraded ? 'degraded' : (item.status || 'unknown');
      acc[status] = (acc[status] || 0) + 1;
      return acc;
    }, {});

    res.json({
      ok: true,
      source: 'node_proof_center',
      generated_at: new Date().toISOString(),
      counts,
      turns: turns.map((turn) => ({
        turn_id: turn.turn_id || null,
        task_id: turn.task_id || turn.taskId || null,
        contract_version: turn.contract_version || null,
        status: turn.status || 'unknown',
        source: turn.source || turn.compatibility_route || 'unknown',
        degraded: turn.degraded === true,
        proof_count: Array.isArray(turn.proof) ? turn.proof.length : 0,
        artifact_count: Array.isArray(turn.artifacts) ? turn.artifacts.length : 0,
        created_at: turn.created_at || turn.timestamp || null,
        errors: Array.isArray(turn.errors) ? turn.errors : [],
      })),
      proof_items: proofItems,
      artifacts: artifactFiles,
    });
  });

  // ── Demo serving — publicly accessible (no auth), shared with customers ──────
  // Demos are now multi-page sites in a per-business folder:
  //   /api/demos/<slug>/            -> <slug>/index.html
  //   /api/demos/<slug>/<page>.html -> <slug>/<page>.html
  // Legacy single-file demos still work: /api/demos/<file>.html
  // res.send() (not sendFile) lets us strip Helmet's restrictive headers and set
  // a permissive CSP so the page (incl. Google Fonts) renders cleanly in a tab.
  const DEMOS_DIR = path.join(AI_HOME, 'state', 'artifacts', 'demos');
  const DEMOS_ROOT = path.resolve(DEMOS_DIR);
  router.use('/api/demos', rateLimit);

  function _sendDemo(res, absPath) {
    // Confine to the demos dir — defence in depth against path traversal.
    if (!path.resolve(absPath).startsWith(DEMOS_ROOT)) return res.status(400).send('Ongeldig pad');
    if (!fs.existsSync(absPath) || !fs.statSync(absPath).isFile()) return res.status(404).send('Demo niet gevonden');
    const html = fs.readFileSync(absPath, 'utf8');
    res.removeHeader('X-Download-Options');
    res.removeHeader('Cross-Origin-Opener-Policy');
    res.removeHeader('Cross-Origin-Resource-Policy');
    res.set({
      'Content-Type': 'text/html; charset=utf-8',
      'X-Frame-Options': 'SAMEORIGIN',
      'Cache-Control': 'no-store',
      'Content-Security-Policy':
        "default-src 'self' data:; script-src 'self' 'unsafe-inline'; " +
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
        "img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com; " +
        "form-action 'self'; frame-ancestors 'self';",
    });
    res.send(html);
  }

  // Publicly serve uploaded order photos used in demos: /api/demos/_assets/<id>/<file>
  // (3 path segments — never matches the 1-/2-segment demo routes below.)
  router.get('/api/demos/_assets/:id/:file', (req, res) => {
    const id = path.basename(req.params.id);
    const file = path.basename(req.params.file);
    const fpath = path.resolve(path.join(DEMOS_DIR, '_assets', id, file));
    if (!fpath.startsWith(DEMOS_ROOT)) return res.status(400).send('Ongeldig pad');
    if (!fs.existsSync(fpath) || !fs.statSync(fpath).isFile()) return res.status(404).send('Niet gevonden');
    res.sendFile(fpath);
  });

  // Sub-page within a site folder: /api/demos/<slug>/<page>.html
  router.get('/api/demos/:slug/:page', (req, res) => {
    const slug = path.basename(req.params.slug);
    const page = path.basename(req.params.page);
    if (!page.endsWith('.html')) return res.status(400).send('Only HTML files allowed');
    _sendDemo(res, path.join(DEMOS_DIR, slug, page));
  });

  // Folder root or legacy single file: /api/demos/<slug>(/)  |  /api/demos/<file>.html
  router.get('/api/demos/:slug', (req, res) => {
    const slug = path.basename(req.params.slug);
    if (slug.endsWith('.html')) return _sendDemo(res, path.join(DEMOS_DIR, slug)); // legacy
    const dir = path.join(DEMOS_DIR, slug);
    if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return res.status(404).send('Demo niet gevonden');
    // Relative links (over.html, …) only resolve correctly under a trailing slash.
    if (!req.path.endsWith('/')) return res.redirect(301, req.path + '/');
    _sendDemo(res, path.join(dir, 'index.html'));
  });

  return router;
};
