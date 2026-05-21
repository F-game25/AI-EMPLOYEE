'use strict';

/**
 * Compute Fabric (WS6) — estimate compute, search remote GPU offers, and (only with
 * verified owner approval) provision. SAFETY IS THE POINT:
 *
 *   - Dry-run is the default for every money path.
 *   - A real purchase is *physically impossible* unless ALL hold:
 *       COMPUTE_FABRIC_LIVE=1  +  a valid single-use owner approval token
 *       +  within budget caps  +  a provider adapter with credentials.
 *     No adapters/credentials are wired, so today every purchase returns a PLAN,
 *     never a charge.
 *   - Every consequential call is appended to state/compute_fabric/audit.jsonl.
 *   - Secrets are never logged or returned.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFile } = require('child_process');

const STATE_DIR = path.resolve(
  process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.HOME || '/tmp', '.ai-employee', 'state'),
);
const CF_DIR = path.join(STATE_DIR, 'compute_fabric');
const JOBS_PATH = path.join(CF_DIR, 'jobs.json');
const SPEND_PATH = path.join(CF_DIR, 'spend.json');
const AUDIT_PATH = path.join(CF_DIR, 'audit.jsonl');
const APPROVALS_PATH = path.join(CF_DIR, 'approvals.json');

const LIVE = process.env.COMPUTE_FABRIC_LIVE === '1';
const SECRET = process.env.JWT_SECRET_KEY || process.env.JWT_SECRET || 'cf-dev-secret';
const DAILY_CAP_USD = Number(process.env.COMPUTE_DAILY_CAP_USD || 0);   // 0 = no spend allowed
const TOTAL_CAP_USD = Number(process.env.COMPUTE_TOTAL_CAP_USD || 0);

function _ensureDir() { fs.mkdirSync(CF_DIR, { recursive: true }); }
function _readJSON(p, fallback) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return fallback; } }
function _writeJSON(p, val) { _ensureDir(); const tmp = `${p}.tmp`; fs.writeFileSync(tmp, JSON.stringify(val, null, 2)); fs.renameSync(tmp, p); }
function _now() { return new Date().toISOString(); }

function audit(event, detail = {}) {
  try { _ensureDir(); fs.appendFileSync(AUDIT_PATH, JSON.stringify({ ts: _now(), event, ...detail }) + '\n'); } catch { /* never throw */ }
}

// ── Provider registry (metadata only — no live calls unless an adapter is enabled) ──
const PROVIDERS = {
  runpod: { name: 'RunPod', enabled: false, gpus: ['A100-80G', 'A40', 'RTX4090', 'H100-80G'] },
  vastai: { name: 'Vast.ai', enabled: false, gpus: ['RTX4090', 'A100-80G', '3090', 'A6000'] },
  lambda: { name: 'Lambda', enabled: false, gpus: ['A100-40G', 'A100-80G', 'H100-80G'] },
  nvidia: { name: 'NVIDIA DGX Cloud', enabled: false, gpus: ['H100-80G', 'A100-80G'] },
};
// Indicative on-demand $/hr (used for ESTIMATES only — not a quote, never a charge).
const GPU_HOURLY = { 'RTX4090': 0.44, '3090': 0.22, 'A6000': 0.47, 'A40': 0.39, 'A100-40G': 1.10, 'A100-80G': 1.79, 'H100-80G': 3.29 };

function localStatus() {
  return new Promise(resolve => {
    execFile('nvidia-smi', ['--query-gpu=name,memory.total,memory.used,utilization.gpu', '--format=csv,noheader,nounits'],
      { timeout: 4000 }, (err, stdout) => {
        if (err) return resolve({ gpu: false, gpus: [], note: 'no NVIDIA GPU detected (nvidia-smi unavailable)' });
        const gpus = String(stdout).trim().split('\n').filter(Boolean).map(line => {
          const [name, total, used, util] = line.split(',').map(s => s.trim());
          return { name, vram_total_mb: Number(total), vram_used_mb: Number(used), util_pct: Number(util) };
        });
        resolve({ gpu: gpus.length > 0, gpus });
      });
  });
}

// ── Estimator: turn a job spec into a compute estimate ──
function estimate(job = {}) {
  const params_b = Number(job.params_b || job.model_params_b || 7);
  const hours = Number(job.hours || job.est_hours || 1);
  const task = String(job.task || 'inference');
  // crude VRAM need: training ~ params*18 bytes, inference ~ params*2.2 bytes (GB)
  const vramGb = Math.ceil(params_b * (task === 'train' || task === 'finetune' ? 18 : 2.2));
  const gpu = vramGb <= 24 ? 'RTX4090' : vramGb <= 48 ? 'A6000' : vramGb <= 80 ? 'A100-80G' : 'H100-80G';
  const count = vramGb > 80 ? Math.ceil(vramGb / 80) : 1;
  const hourly = (GPU_HOURLY[gpu] || 1.0) * count;
  return {
    task, params_b, est_vram_gb: vramGb, recommended_gpu: gpu, gpu_count: count,
    est_hours: hours, est_hourly_usd: Number(hourly.toFixed(2)), est_total_usd: Number((hourly * hours).toFixed(2)),
    note: 'Indicative estimate only — not a price quote. Real provisioning requires owner approval and is dry-run by default.',
  };
}

// ── Marketplace: search offers (synthetic unless a provider adapter is live) ──
function searchOffers(requirements = {}) {
  const est = estimate(requirements);
  const offers = Object.entries(PROVIDERS).flatMap(([id, p]) => {
    if (!p.gpus.includes(est.recommended_gpu)) return [];
    const hourly = (GPU_HOURLY[est.recommended_gpu] || 1.0) * est.gpu_count;
    return [{
      provider: id, provider_name: p.name, gpu: est.recommended_gpu, gpu_count: est.gpu_count,
      hourly_usd: Number((hourly * (0.9 + Math.random() * 0.3)).toFixed(2)),
      region: 'synthetic', live: p.enabled,
      source: p.enabled ? 'provider_api' : 'indicative_catalog',
    }];
  }).sort((a, b) => a.hourly_usd - b.hourly_usd);
  return { dry_run: !LIVE, requirements: est, offers, note: LIVE ? 'Live providers disabled until adapters+keys are configured.' : 'Dry-run: indicative offers, no provider was contacted.' };
}

// ── Budget guard ──
function todaySpend() {
  const s = _readJSON(SPEND_PATH, { days: {}, total_usd: 0 });
  const day = _now().slice(0, 10);
  return { day, day_usd: s.days?.[day] || 0, total_usd: s.total_usd || 0 };
}
function budgetCheck(amountUsd) {
  const { day, day_usd, total_usd } = todaySpend();
  const reasons = [];
  if (DAILY_CAP_USD <= 0) reasons.push('daily cap is 0 (spending disabled — set COMPUTE_DAILY_CAP_USD to enable)');
  if (day_usd + amountUsd > DAILY_CAP_USD) reasons.push(`would exceed daily cap $${DAILY_CAP_USD} (today $${day_usd.toFixed(2)})`);
  if (TOTAL_CAP_USD > 0 && total_usd + amountUsd > TOTAL_CAP_USD) reasons.push(`would exceed total cap $${TOTAL_CAP_USD}`);
  return { ok: reasons.length === 0, day, day_usd, total_usd, daily_cap: DAILY_CAP_USD, total_cap: TOTAL_CAP_USD, reasons };
}
function recordSpend(amountUsd) {
  const s = _readJSON(SPEND_PATH, { days: {}, total_usd: 0 });
  const day = _now().slice(0, 10);
  s.days = s.days || {}; s.days[day] = (s.days[day] || 0) + amountUsd; s.total_usd = (s.total_usd || 0) + amountUsd;
  _writeJSON(SPEND_PATH, s);
}

// ── Owner approval: single-use, short-lived, HMAC-signed token ──
function requestApproval(plan = {}) {
  const est = estimate(plan);
  const nonce = crypto.randomBytes(8).toString('hex');
  const expires = Date.now() + 5 * 60 * 1000;
  const challenge = { nonce, expires, est_total_usd: est.est_total_usd, gpu: est.recommended_gpu, plan_summary: `${est.gpu_count}× ${est.recommended_gpu} for ${est.est_hours}h ≈ $${est.est_total_usd}` };
  const approvals = _readJSON(APPROVALS_PATH, {});
  approvals[nonce] = { ...challenge, used: false, created: _now() };
  _writeJSON(APPROVALS_PATH, approvals);
  audit('approval_requested', { nonce, est_total_usd: est.est_total_usd, gpu: est.recommended_gpu });
  return { ...challenge, requires: 'Owner must verify to receive a single-use approval token. No charge occurs.' };
}

function _sign(nonce, expires) {
  return crypto.createHmac('sha256', SECRET).update(`${nonce}:${expires}`).digest('hex');
}

function verifyOwner({ nonce, ownerApproved }) {
  const approvals = _readJSON(APPROVALS_PATH, {});
  const a = approvals[nonce];
  if (!a) return { ok: false, error: 'unknown approval challenge' };
  if (a.used) return { ok: false, error: 'approval already used' };
  if (Date.now() > a.expires) return { ok: false, error: 'approval expired' };
  if (ownerApproved !== true) return { ok: false, error: 'explicit owner approval required (ownerApproved:true)' };
  const token = `${nonce}.${a.expires}.${_sign(nonce, a.expires)}`;
  audit('owner_verified', { nonce, est_total_usd: a.est_total_usd });
  return { ok: true, approval_token: token, expires: a.expires, est_total_usd: a.est_total_usd };
}

function _consumeToken(token) {
  const [nonce, expires, sig] = String(token || '').split('.');
  if (!nonce || !expires || !sig) return { ok: false, error: 'malformed approval token' };
  if (sig !== _sign(nonce, Number(expires))) return { ok: false, error: 'invalid approval signature' };
  if (Date.now() > Number(expires)) return { ok: false, error: 'approval token expired' };
  const approvals = _readJSON(APPROVALS_PATH, {});
  const a = approvals[nonce];
  if (!a) return { ok: false, error: 'unknown approval' };
  if (a.used) return { ok: false, error: 'approval already used' };
  a.used = true; a.used_at = _now(); _writeJSON(APPROVALS_PATH, approvals);
  return { ok: true, approval: a };
}

// ── Purchase / provision — dry-run unless every safety gate passes ──
function purchase({ offer = {}, approval_token, dry_run } = {}) {
  const wantLive = dry_run === false;
  const amount = Number(offer.hourly_usd || 0) * Number(offer.est_hours || offer.hours || 1);
  // Always produce the plan first.
  const plan = { provider: offer.provider, gpu: offer.gpu, est_amount_usd: Number(amount.toFixed(2)), would_charge: false };

  if (!wantLive) { audit('purchase_dryrun', { provider: offer.provider, amount: plan.est_amount_usd }); return { status: 'dry_run', plan, note: 'Dry-run: no provider contacted, no charge.' }; }

  // Live path — every gate must pass or we refuse and DO NOT spend.
  if (!LIVE) return { status: 'refused', plan, reason: 'COMPUTE_FABRIC_LIVE is not set — live provisioning disabled.' };
  const tok = _consumeToken(approval_token);
  if (!tok.ok) return { status: 'refused', plan, reason: tok.error };
  const budget = budgetCheck(amount);
  if (!budget.ok) { audit('purchase_blocked_budget', { reasons: budget.reasons }); return { status: 'refused', plan, budget, reason: budget.reasons.join('; ') }; }
  const prov = PROVIDERS[offer.provider];
  if (!prov || !prov.enabled) return { status: 'refused', plan, reason: `provider ${offer.provider} adapter not enabled/configured` };

  // (No adapter is wired — so we reach here only in a future with real adapters.)
  audit('purchase_attempt_no_adapter', { provider: offer.provider, amount });
  return { status: 'refused', plan, reason: 'No provider adapter implementation present — refusing to claim a charge that cannot occur.' };
}

// ── Jobs ──
function listJobs() { return _readJSON(JOBS_PATH, { jobs: [] }).jobs; }
function _saveJobs(jobs) { _writeJSON(JOBS_PATH, { jobs, updated_at: _now() }); }

function startJob({ name, offer, approval_token, dry_run } = {}) {
  const result = purchase({ offer: offer || {}, approval_token, dry_run });
  const job = {
    id: crypto.randomUUID(), name: name || 'compute-job', status: result.status === 'dry_run' ? 'planned' : (result.status === 'refused' ? 'refused' : 'provisioning'),
    provider: offer?.provider || null, gpu: offer?.gpu || null, created_at: _now(),
    dry_run: dry_run !== false, provision: result, heartbeat_at: null,
  };
  const jobs = listJobs(); jobs.unshift(job); _saveJobs(jobs);
  audit('job_started', { id: job.id, status: job.status, dry_run: job.dry_run });
  return job;
}

function stopJob(id) {
  const jobs = listJobs();
  const j = jobs.find(x => x.id === id);
  if (!j) return { ok: false, error: 'job not found' };
  j.status = 'stopped'; j.stopped_at = _now(); _saveJobs(jobs);
  audit('job_stopped', { id });
  return { ok: true, job: j };
}

function spend() { const t = todaySpend(); return { ...t, daily_cap: DAILY_CAP_USD, total_cap: TOTAL_CAP_USD, live: LIVE }; }
function auditTail(limit = 100) {
  try { return _readJSON ? fs.readFileSync(AUDIT_PATH, 'utf8').trim().split('\n').slice(-limit).map(l => JSON.parse(l)) : []; }
  catch { return []; }
}

module.exports = {
  localStatus, estimate, searchOffers, budgetCheck, requestApproval, verifyOwner,
  purchase, startJob, stopJob, listJobs, spend, auditTail, PROVIDERS, LIVE,
};
