#!/usr/bin/env node
/**
 * bootstrap.js — Zero-dependency entry point for AI-Employee
 * Uses ONLY Node.js built-in modules (http, fs, path, child_process)
 * to avoid chicken-and-egg dependency issues on first install.
 *
 * Flow:
 *   1. Start tiny HTTP server on PORT (default 8787)
 *   2. Serve installation wizard at /
 *   3. Run installers in background, stream status via /api/bootstrap/status
 *   4. Once ready, transition: kill self, exec start.sh
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn, exec } = require('child_process');
const url = require('url');

const PORT = parseInt(process.env.PORT || '8787', 10);
const REPO_ROOT = __dirname;
const AI_HOME = path.join(os.homedir(), '.ai-employee');

const systemState = {
  pythonReady: false,
  pythonError: null,
  pythonLog: [],
  nodeReady: false,
  nodeError: null,
  nodeLog: [],
  frontendReady: false,
  frontendError: null,
  frontendLog: [],
  identityReady: false,
  identity: null,
  allReady: false,
  transitioning: false,
};

const MAX_LOG_LINES = 30;

function pushLog(arr, msg) {
  const line = String(msg).trim();
  if (!line) return;
  for (const part of line.split('\n')) {
    if (part.trim()) {
      arr.push(part);
      if (arr.length > MAX_LOG_LINES) arr.shift();
    }
  }
  console.log(`[bootstrap] ${line}`);
}

// ─────────────────────────────────────────────────────────────────────────────
// Identity generation (pure Node, no Python dependency)
// ─────────────────────────────────────────────────────────────────────────────
const MYTHOLOGIES = ['Aurora', 'Helios', 'Artemis', 'Hermes', 'Athena', 'Apollo', 'Nova', 'Zenith', 'Orion', 'Vega', 'Sirius', 'Polaris'];
const SUFFIXES = ['Prime', 'Elite', 'Core', 'Nexus', 'Edge', 'Pulse', 'Forge', 'Storm', 'Crown'];

function hslToHex(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs((h * 6) % 2 - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 1/6) [r, g, b] = [c, x, 0];
  else if (h < 1/3) [r, g, b] = [x, c, 0];
  else if (h < 1/2) [r, g, b] = [0, c, x];
  else if (h < 2/3) [r, g, b] = [0, x, c];
  else if (h < 5/6) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const toHex = (v) => Math.round((v + m) * 255).toString(16).padStart(2, '0');
  return '#' + toHex(r) + toHex(g) + toHex(b);
}

function randomTenantId() {
  return 'tnt_' + Math.random().toString(36).slice(2, 14);
}

function ensureIdentity() {
  if (!fs.existsSync(AI_HOME)) {
    fs.mkdirSync(AI_HOME, { recursive: true });
    for (const sub of ['state', 'tenants', 'credentials', 'capabilities', 'models', 'logs']) {
      fs.mkdirSync(path.join(AI_HOME, sub), { recursive: true });
    }
  }
  const identityFile = path.join(AI_HOME, 'identity.json');
  if (fs.existsSync(identityFile)) {
    try {
      return JSON.parse(fs.readFileSync(identityFile, 'utf8'));
    } catch (_) { /* fall through, regenerate */ }
  }

  const hue = 0.7 + Math.random() * 0.3;
  const sat = 0.6 + Math.random() * 0.3;
  const identity = {
    tenant_id: randomTenantId(),
    instance_name: `${MYTHOLOGIES[Math.floor(Math.random() * MYTHOLOGIES.length)]}-${SUFFIXES[Math.floor(Math.random() * SUFFIXES.length)]}`,
    user_chosen: null,
    color_palette: {
      primary: hslToHex(hue, sat, 0.4),
      accent: hslToHex(hue, sat * 0.8, 0.55),
      secondary: hslToHex((hue + 0.15) % 1.0, sat * 0.7, 0.4),
    },
    voice_preset: 'professional',
    emergent: { vocabulary_signature: [], favorite_agents: [], work_pattern: null, tone_drift: 0.0 },
    created_at: new Date().toISOString(),
    evolution_log: [],
  };
  fs.writeFileSync(identityFile, JSON.stringify(identity, null, 2));
  return identity;
}

function ensureEnv() {
  const envFile = path.join(AI_HOME, '.env');
  if (fs.existsSync(envFile)) return;
  const crypto = require('crypto');
  const jwtSecret = crypto.randomBytes(32).toString('base64url');
  const content = `# AI-Employee Environment
JWT_SECRET_KEY=${jwtSecret}
PORT=${PORT}
PYTHON_BACKEND_PORT=18790
LLM_BACKEND=anthropic
LOG_LEVEL=INFO
EVOLUTION_MODE=AUTO
# ANTHROPIC_API_KEY=<add-your-key>
`;
  fs.writeFileSync(envFile, content, { mode: 0o600 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Dependency installers
// ─────────────────────────────────────────────────────────────────────────────
function runStreaming(cmd, args, opts, logArr, doneCb) {
  pushLog(logArr, `> ${cmd} ${args.join(' ')}`);
  const child = spawn(cmd, args, { ...opts, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.on('data', (d) => pushLog(logArr, d.toString()));
  child.stderr.on('data', (d) => pushLog(logArr, d.toString()));
  child.on('close', (code) => doneCb(code));
  child.on('error', (err) => {
    pushLog(logArr, `ERROR: ${err.message}`);
    doneCb(1);
  });
}

function installPython(callback) {
  const reqFile = path.join(REPO_ROOT, 'runtime', 'requirements-core.txt');
  if (!fs.existsSync(reqFile)) {
    systemState.pythonError = 'requirements-core.txt missing';
    pushLog(systemState.pythonLog, systemState.pythonError);
    systemState.pythonReady = true;
    callback();
    return;
  }

  const venvDir = path.join(AI_HOME, 'venv');
  const venvPython = path.join(venvDir, 'bin', 'python3');
  const venvPip = path.join(venvDir, 'bin', 'pip');

  // Quick check: do we already have key packages in venv (or system, as fallback)?
  const checkCmd = fs.existsSync(venvPython)
    ? `${venvPython} -c "import fastapi, uvicorn, anthropic"`
    : `python3 -c "import fastapi, uvicorn, anthropic"`;
  exec(checkCmd, (err) => {
    if (!err) {
      pushLog(systemState.pythonLog, '✓ Core Python packages already present');
      systemState.pythonReady = true;
      callback();
      return;
    }

    const installIntoVenv = () => {
      pushLog(systemState.pythonLog, 'Installing Python core dependencies into venv...');
      runStreaming(venvPip, ['install', '-q', '--upgrade', 'pip'], { cwd: REPO_ROOT }, systemState.pythonLog, () => {
        runStreaming(venvPip, ['install', '-q', '-r', reqFile], { cwd: REPO_ROOT }, systemState.pythonLog, (code) => {
          if (code === 0) {
            pushLog(systemState.pythonLog, '✓ Python core dependencies installed');
            systemState.pythonReady = true;
          } else {
            systemState.pythonError = `pip install exited with code ${code}`;
            pushLog(systemState.pythonLog, systemState.pythonError);
            systemState.pythonReady = true;
          }
          callback();
        });
      });
    };

    if (!fs.existsSync(venvPython)) {
      pushLog(systemState.pythonLog, `Creating virtualenv at ${venvDir}...`);
      runStreaming('python3', ['-m', 'venv', venvDir], { cwd: REPO_ROOT }, systemState.pythonLog, (code) => {
        if (code !== 0) {
          // venv creation failed (likely python3-venv missing). Tell user how to fix.
          systemState.pythonError = 'Could not create venv. Install: sudo apt install python3-venv python3-full';
          pushLog(systemState.pythonLog, systemState.pythonError);
          systemState.pythonReady = true;
          callback();
          return;
        }
        installIntoVenv();
      });
    } else {
      installIntoVenv();
    }
  });
}

function installNode(callback) {
  const tasks = [
    { name: 'backend', dir: path.join(REPO_ROOT, 'backend') },
    { name: 'frontend', dir: path.join(REPO_ROOT, 'frontend') },
  ];
  let pending = 0;
  let failed = false;

  const onTaskDone = (code, name) => {
    if (code !== 0) {
      failed = true;
      systemState.nodeError = `${name} npm install failed (code ${code})`;
      pushLog(systemState.nodeLog, systemState.nodeError);
    } else {
      pushLog(systemState.nodeLog, `✓ ${name} dependencies ready`);
    }
    pending--;
    if (pending === 0) {
      systemState.nodeReady = true;
      callback();
    }
  };

  for (const t of tasks) {
    const modulesDir = path.join(t.dir, 'node_modules');
    if (fs.existsSync(modulesDir)) {
      pushLog(systemState.nodeLog, `✓ ${t.name} node_modules already present`);
      continue;
    }
    if (!fs.existsSync(path.join(t.dir, 'package.json'))) {
      pushLog(systemState.nodeLog, `⚠ ${t.name}/package.json missing — skipping`);
      continue;
    }
    pending++;
    pushLog(systemState.nodeLog, `Installing ${t.name} dependencies...`);
    runStreaming('npm', ['install', '--no-fund', '--no-audit', '--silent'], { cwd: t.dir }, systemState.nodeLog, (code) => onTaskDone(code, t.name));
  }

  if (pending === 0) {
    systemState.nodeReady = true;
    callback();
  }
}

function buildFrontend(callback) {
  const distDir = path.join(REPO_ROOT, 'frontend', 'dist');
  const indexHtml = path.join(distDir, 'index.html');
  // If dist already exists with index.html, skip rebuild (cache hit)
  if (fs.existsSync(indexHtml)) {
    pushLog(systemState.frontendLog, '✓ Frontend dist already built (cache hit)');
    systemState.frontendReady = true;
    callback();
    return;
  }
  pushLog(systemState.frontendLog, 'Building frontend...');
  runStreaming('npm', ['run', 'build'], { cwd: path.join(REPO_ROOT, 'frontend') }, systemState.frontendLog, (code) => {
    if (code === 0) {
      pushLog(systemState.frontendLog, '✓ Frontend built');
      systemState.frontendReady = true;
    } else {
      systemState.frontendError = `Build exited ${code}`;
      pushLog(systemState.frontendLog, systemState.frontendError);
      systemState.frontendReady = true;
    }
    callback();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Boot sequence
// ─────────────────────────────────────────────────────────────────────────────
function runBootSequence() {
  pushLog(systemState.pythonLog, '[bootstrap] Starting boot sequence...');

  ensureEnv();
  systemState.identity = ensureIdentity();
  systemState.identityReady = true;
  pushLog(systemState.pythonLog, `Identity: ${systemState.identity.instance_name} (${systemState.identity.tenant_id})`);

  // Run python and node installers in parallel
  let completed = 0;
  const checkAllDone = () => {
    completed++;
    if (completed === 2) {
      // Now build frontend (after node deps are in place)
      buildFrontend(() => {
        systemState.allReady = true;
        pushLog(systemState.pythonLog, '✓ All dependencies ready');
      });
    }
  };

  installPython(checkAllDone);
  installNode(checkAllDone);
}

// ─────────────────────────────────────────────────────────────────────────────
// Transition: hand off to start.sh
// ─────────────────────────────────────────────────────────────────────────────
function transitionToMainSystem(res) {
  if (systemState.transitioning) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, message: 'Already transitioning' }));
    return;
  }
  systemState.transitioning = true;

  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ ok: true, message: 'Starting main system' }));

  console.log('[bootstrap] Handing off to start.sh...');
  setTimeout(() => {
    server.close(() => {
      const startScript = path.join(REPO_ROOT, 'start.sh');
      if (!fs.existsSync(startScript)) {
        console.error('[bootstrap] start.sh not found at', startScript);
        process.exit(1);
      }

      const logFile = path.join(AI_HOME, 'logs', 'startup.log');
      // Ensure logs dir exists
      try { fs.mkdirSync(path.dirname(logFile), { recursive: true }); } catch (_) {}
      const out = fs.openSync(logFile, 'a');
      const err = fs.openSync(logFile, 'a');

      // Use setsid to fully detach from our process group, so start.sh
      // survives even if our parent shell or terminal closes.
      const launcher = process.platform === 'darwin' ? 'bash' : 'setsid';
      const args = process.platform === 'darwin'
        ? [startScript]
        : ['bash', startScript];

      const child = spawn(launcher, args, {
        cwd: REPO_ROOT,
        detached: true,
        stdio: ['ignore', out, err],
        env: { ...process.env, BOOTSTRAP_HANDOFF: '1' },
      });
      child.unref();
      console.log(`[bootstrap] start.sh launched (PID ${child.pid}). Logs: ${logFile}`);
      console.log('[bootstrap] Exiting. Browser will reconnect once main server is ready.');
      setTimeout(() => process.exit(0), 800);
    });
  }, 1000);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tiny HTTP server (no express)
// ─────────────────────────────────────────────────────────────────────────────
function readBody(req, cb) {
  let data = '';
  req.on('data', (c) => { data += c; if (data.length > 1e6) req.destroy(); });
  req.on('end', () => {
    try { cb(null, data ? JSON.parse(data) : {}); }
    catch (e) { cb(e); }
  });
}

function send(res, code, body, type = 'application/json') {
  res.writeHead(code, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(typeof body === 'string' ? body : JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  const u = url.parse(req.url, true);

  if (u.pathname === '/api/bootstrap/status' && req.method === 'GET') {
    return send(res, 200, systemState);
  }

  if (u.pathname === '/api/bootstrap/start' && req.method === 'POST') {
    return transitionToMainSystem(res);
  }

  if (u.pathname === '/api/identity/finalize' && req.method === 'POST') {
    return readBody(req, (err, body) => {
      if (err) return send(res, 400, { error: 'Invalid JSON' });
      const idFile = path.join(AI_HOME, 'identity.json');
      let id;
      try { id = JSON.parse(fs.readFileSync(idFile, 'utf8')); }
      catch (_) { id = ensureIdentity(); }
      if (body.user_chosen) id.user_chosen = body.user_chosen;
      if (body.instance_name) id.instance_name = body.instance_name;
      if (body.voice_preset) id.voice_preset = body.voice_preset;
      if (body.color_palette) id.color_palette = body.color_palette;
      id.evolution_log.push({ event: 'identity_finalized', timestamp: new Date().toISOString() });
      fs.writeFileSync(idFile, JSON.stringify(id, null, 2));
      systemState.identity = id;
      send(res, 200, { ok: true, identity: id });
    });
  }

  if (u.pathname === '/' && req.method === 'GET') {
    return send(res, 200, renderUI(), 'text/html; charset=utf-8');
  }

  send(res, 404, { error: 'Not found' });
});

// ─────────────────────────────────────────────────────────────────────────────
// UI
// ─────────────────────────────────────────────────────────────────────────────
function renderUI() {
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI-Employee — Initializing</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:radial-gradient(ellipse at top,#1e293b 0%,#0f172a 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem;color:#f1f5f9}
  .card{width:100%;max-width:640px;background:rgba(15,23,42,.85);border:1px solid rgba(148,163,184,.2);border-radius:16px;padding:2.5rem;box-shadow:0 20px 60px rgba(0,0,0,.6),0 0 80px rgba(168,85,247,.15);backdrop-filter:blur(20px)}
  h1{font-size:1.75rem;background:linear-gradient(135deg,#e5c76b,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-align:center;font-weight:700}
  .sub{text-align:center;color:#94a3b8;font-size:.95rem;margin:.5rem 0 2rem}
  .item{display:flex;gap:1rem;margin:.85rem 0;padding:1rem;background:rgba(30,41,59,.5);border:1px solid rgba(148,163,184,.1);border-radius:10px;align-items:flex-start}
  .icon{flex-shrink:0;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;margin-top:1px}
  .icon.pending{background:rgba(148,163,184,.2)}
  .icon.ready{background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff}
  .icon.error{background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff}
  .text{flex:1;min-width:0}
  .label{font-weight:600;color:#f1f5f9}
  .detail{color:#94a3b8;font-size:.85rem;margin-top:.2rem}
  .log{margin-top:.5rem;padding:.6rem;background:rgba(0,0,0,.4);border:1px solid rgba(148,163,184,.08);border-radius:6px;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:.7rem;color:#cbd5e1;max-height:120px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;line-height:1.4}
  .log:empty{display:none}
  .spinner{width:14px;height:14px;border:2px solid rgba(255,255,255,.25);border-top-color:#a855f7;border-radius:50%;animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  .btn-row{display:flex;justify-content:center;margin-top:2rem}
  button{padding:.95rem 2rem;border:none;border-radius:10px;font-size:1rem;font-weight:600;cursor:pointer;transition:all .2s;font-family:inherit}
  .btn-primary{background:linear-gradient(135deg,#e5c76b,#a855f7);color:#0f172a}
  .btn-primary:hover:not(:disabled){box-shadow:0 0 24px rgba(168,85,247,.5);transform:translateY(-1px)}
  .btn-primary:disabled{opacity:.4;cursor:not-allowed}
  .identity-banner{margin-bottom:1.5rem;padding:1rem;text-align:center;background:linear-gradient(135deg,rgba(229,199,107,.1),rgba(168,85,247,.1));border:1px solid rgba(168,85,247,.2);border-radius:10px}
  .identity-name{font-size:1.4rem;font-weight:700;background:linear-gradient(135deg,#e5c76b,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  .identity-id{font-size:.75rem;color:#64748b;font-family:monospace;margin-top:.25rem}
</style></head>
<body>
<div class="card">
  <h1>AI-Employee</h1>
  <p class="sub">Initializing your system…</p>
  <div id="identityBanner" class="identity-banner" style="display:none">
    <div class="identity-name" id="identityName">—</div>
    <div class="identity-id" id="identityId">—</div>
  </div>

  <div class="item" id="item-identity">
    <div class="icon pending" id="icon-identity"><span class="spinner"></span></div>
    <div class="text">
      <div class="label">Identity</div>
      <div class="detail" id="detail-identity">Generating unique identity…</div>
    </div>
  </div>

  <div class="item" id="item-python">
    <div class="icon pending" id="icon-python"><span class="spinner"></span></div>
    <div class="text">
      <div class="label">Python AI Engine</div>
      <div class="detail" id="detail-python">Checking dependencies…</div>
      <div class="log" id="log-python"></div>
    </div>
  </div>

  <div class="item" id="item-node">
    <div class="icon pending" id="icon-node"><span class="spinner"></span></div>
    <div class="text">
      <div class="label">Backend &amp; Frontend Modules</div>
      <div class="detail" id="detail-node">Checking npm packages…</div>
      <div class="log" id="log-node"></div>
    </div>
  </div>

  <div class="item" id="item-frontend">
    <div class="icon pending" id="icon-frontend"><span class="spinner"></span></div>
    <div class="text">
      <div class="label">Dashboard Build</div>
      <div class="detail" id="detail-frontend">Waiting for modules…</div>
      <div class="log" id="log-frontend"></div>
    </div>
  </div>

  <div class="btn-row">
    <button class="btn-primary" id="continueBtn" disabled>Setting up…</button>
  </div>
</div>

<script>
function setRow(name, ready, error, detailMsg) {
  const icon = document.getElementById('icon-' + name);
  const detail = document.getElementById('detail-' + name);
  if (ready) {
    icon.className = 'icon ' + (error ? 'error' : 'ready');
    icon.innerHTML = error ? '✕' : '✓';
    if (detailMsg) detail.textContent = detailMsg;
  }
}
function setLog(name, lines) {
  const el = document.getElementById('log-' + name);
  if (!el) return;
  if (!lines || !lines.length) { el.textContent = ''; return; }
  el.textContent = lines.slice(-8).join('\\n');
  el.scrollTop = el.scrollHeight;
}

let started = false;
function poll() {
  fetch('/api/bootstrap/status').then(r => r.json()).then(s => {
    if (s.identity) {
      document.getElementById('identityBanner').style.display = 'block';
      document.getElementById('identityName').textContent = s.identity.instance_name || '—';
      document.getElementById('identityId').textContent = s.identity.tenant_id || '—';
    }
    setRow('identity', s.identityReady, false, s.identityReady ? '✓ Ready' : 'Generating…');
    setRow('python', s.pythonReady, !!s.pythonError, s.pythonError || (s.pythonReady ? '✓ Ready' : 'Installing…'));
    setRow('node', s.nodeReady, !!s.nodeError, s.nodeError || (s.nodeReady ? '✓ Ready' : 'Installing…'));
    setRow('frontend', s.frontendReady, !!s.frontendError, s.frontendError || (s.frontendReady ? '✓ Ready' : 'Waiting…'));
    setLog('python', s.pythonLog);
    setLog('node', s.nodeLog);
    setLog('frontend', s.frontendLog);

    const btn = document.getElementById('continueBtn');
    if (s.allReady && !started) {
      started = true;
      btn.disabled = false;
      btn.textContent = '🚀 Launch Dashboard';
      btn.onclick = () => {
        btn.disabled = true;
        btn.textContent = 'Starting system…';
        fetch('/api/bootstrap/start', { method: 'POST' }).then(() => {
          // Poll the new server (start.sh will replace this one)
          setTimeout(waitForMainServer, 2000);
        });
      };
    }
    if (!s.transitioning) setTimeout(poll, 1000);
  }).catch(() => setTimeout(poll, 2000));
}

function waitForMainServer() {
  // start.sh boots backend on the same port — poll /version to detect it
  fetch('/version', { cache: 'no-store' }).then(r => {
    if (r.ok) {
      window.location.reload();
    } else {
      setTimeout(waitForMainServer, 1500);
    }
  }).catch(() => setTimeout(waitForMainServer, 1500));
}

poll();
</script>
</body></html>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Start
// ─────────────────────────────────────────────────────────────────────────────
server.listen(PORT, () => {
  console.log(`\n╔═══════════════════════════════════════════════╗`);
  console.log(  `║  🤖 AI-Employee Bootstrap                    ║`);
  console.log(  `║  Open: http://localhost:${PORT}                  ║`);
  console.log(  `╚═══════════════════════════════════════════════╝\n`);
  runBootSequence();
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`[bootstrap] Port ${PORT} already in use. Maybe AI-Employee is already running?`);
    console.error(`[bootstrap] Open http://localhost:${PORT} in your browser.`);
    process.exit(2);
  }
  throw err;
});

process.on('SIGINT', () => { console.log('\n[bootstrap] Stopping...'); server.close(() => process.exit(0)); });
process.on('SIGTERM', () => { server.close(() => process.exit(0)); });
