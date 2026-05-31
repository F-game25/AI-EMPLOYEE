'use strict';

/**
 * Remote Job Persistence (WS7) — local is the permanent source of truth; remote
 * compute is disposable. Every job gets a local archive with a checksummed manifest,
 * heartbeat tracking, checkpoints, and a teardown that REFUSES until the final sync
 * is verified. "Sync" pulls a remote/working dir's files into the local archive and
 * checksums them — so nothing important is lost even if the remote vanishes.
 *
 *   state/compute_fabric/job_archive/{jobId}/
 *     ├── artifacts/         collected outputs (models, logs, results)
 *     ├── checkpoints/       resumable checkpoints (json)
 *     ├── manifest.json      {files:[{rel,bytes,sha256,ts}], last_sync, verified}
 *     └── heartbeat.json     {ts, status, ...}
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const STATE_DIR = path.resolve(
  process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.HOME || '/tmp', '.ai-employee', 'state'),
);
const ARCHIVE_ROOT = path.join(STATE_DIR, 'compute_fabric', 'job_archive');
const HEARTBEAT_STALE_S = Number(process.env.COMPUTE_HEARTBEAT_STALE_S || 120);

function _now() { return new Date().toISOString(); }
function _safeId(value, fallback = 'job') {
  const safe = String(value || fallback).replace(/[^\w.-]/g, '_').slice(0, 120);
  if (['__proto__', 'prototype', 'constructor'].includes(safe)) return fallback;
  return safe || fallback;
}
function _safeRel(value, fallback = 'artifact') {
  const cleaned = String(value || fallback)
    .split(/[\\/]+/)
    .map((part) => _safeId(part, 'part'))
    .filter(Boolean)
    .join(path.sep);
  return cleaned || fallback;
}
function _safeInside(root, rel) {
  const base = path.resolve(root);
  const target = path.resolve(base, rel);
  if (target !== base && !target.startsWith(base + path.sep)) throw new Error('path escaped archive root');
  return target;
}
function _allowedSourceDir(fromDir) {
  const source = path.resolve(String(fromDir || ''));
  const allowedRoots = [
    path.resolve(process.env.COMPUTE_SYNC_ROOT || path.join(process.env.HOME || '/tmp', '.ai-employee')),
    path.resolve('/tmp'),
  ];
  return allowedRoots.some((root) => source === root || source.startsWith(root + path.sep)) ? source : null;
}
function _allowedSourceFile(src) {
  const source = path.resolve(String(src || ''));
  const allowedDir = _allowedSourceDir(path.dirname(source));
  if (!allowedDir) return null;
  return source === path.resolve(allowedDir, path.basename(source)) ? source : null;
}
function _dir(jobId) { return _safeInside(ARCHIVE_ROOT, _safeId(jobId)); }
function _ensure(jobId) {
  const d = _dir(jobId);
  fs.mkdirSync(path.join(d, 'artifacts'), { recursive: true });
  fs.mkdirSync(path.join(d, 'checkpoints'), { recursive: true });
  return d;
}
function _readJSON(p, fb) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return fb; } }
function _writeJSON(p, v) { const tmp = `${p}.tmp`; fs.writeFileSync(tmp, JSON.stringify(v, null, 2)); fs.renameSync(tmp, p); }
function _sha256(buf) { return crypto.createHash('sha256').update(buf).digest('hex'); }
function _manifestPath(jobId) { return path.join(_dir(jobId), 'manifest.json'); }
function _hbPath(jobId) { return path.join(_dir(jobId), 'heartbeat.json'); }

function initJob(jobId, meta = {}) {
  const d = _ensure(jobId);
  const mp = _manifestPath(jobId);
  if (!fs.existsSync(mp)) _writeJSON(mp, { job_id: jobId, created_at: _now(), files: [], last_sync: null, verified: false, meta });
  heartbeat(jobId, { status: 'initialized' });
  return d;
}

function heartbeat(jobId, info = {}) {
  _ensure(jobId);
  _writeJSON(_hbPath(jobId), { ts: _now(), ...info });
  return { ok: true, ts: _now() };
}

function heartbeatAge(jobId) {
  const hb = _readJSON(_hbPath(jobId), null);
  if (!hb?.ts) return null;
  return Math.round((Date.now() - new Date(hb.ts).getTime()) / 1000);
}

function writeCheckpoint(jobId, name, data) {
  _ensure(jobId);
  const safe = _safeId(name || `ckpt-${Date.now()}`, 'checkpoint');
  const p = _safeInside(path.join(_dir(jobId), 'checkpoints'), `${safe}.json`);
  _writeJSON(p, { name: safe, ts: _now(), data });
  heartbeat(jobId, { status: 'checkpoint', checkpoint: safe });
  return { ok: true, checkpoint: safe };
}

function listCheckpoints(jobId) {
  const d = path.join(_dir(jobId), 'checkpoints');
  try {
    return fs.readdirSync(d).filter(f => f.endsWith('.json'))
      .map(f => { const c = _readJSON(path.join(d, f), {}); return { name: c.name || f, ts: c.ts }; })
      .sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
  } catch { return []; }
}

// Collect a single artifact into the archive (from content or a source file).
function collectArtifact(jobId, { rel, content, src }) {
  _ensure(jobId);
  const relName = _safeRel(rel || (src ? path.basename(src) : `artifact-${Date.now()}`));
  const artifactsRoot = path.join(_dir(jobId), 'artifacts');
  const dest = _safeInside(artifactsRoot, relName);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  let buf;
  if (content != null) buf = Buffer.from(String(content));
  else if (src) {
    const safeSrc = _allowedSourceFile(src);
    if (!safeSrc || !fs.existsSync(safeSrc)) return { ok: false, error: 'source file outside allowed sync roots' };
    buf = fs.readFileSync(safeSrc);
  }
  else return { ok: false, error: 'no content or readable src' };
  fs.writeFileSync(dest, buf);
  _updateManifestEntry(jobId, relName, buf);
  return { ok: true, rel: relName, bytes: buf.length, sha256: _sha256(buf) };
}

function _updateManifestEntry(jobId, rel, buf) {
  const mp = _manifestPath(jobId);
  const m = _readJSON(mp, { job_id: jobId, files: [], last_sync: null, verified: false });
  m.files = (m.files || []).filter(f => f.rel !== rel);
  m.files.push({ rel, bytes: buf.length, sha256: _sha256(buf), ts: _now() });
  m.last_sync = _now();
  m.verified = false; // changed since last verify
  _writeJSON(mp, m);
}

// Pull every file from a source dir (the remote/working dir) into the archive.
function forceSync(jobId, fromDir) {
  _ensure(jobId);
  const sourceDir = fromDir ? _allowedSourceDir(fromDir) : null;
  if (!sourceDir || !fs.existsSync(sourceDir)) {
    // No source provided — just re-verify what's already archived.
    return verifyManifest(jobId);
  }
  let count = 0;
  const walk = (dir, base) => {
    for (const name of fs.readdirSync(dir)) {
      const full = path.join(dir, name);
      const st = fs.statSync(full);
      if (st.isDirectory()) walk(full, path.join(base, name));
      else if (st.size <= 50 * 1024 * 1024) { collectArtifact(jobId, { rel: path.join(base, name), src: full }); count++; }
    }
  };
  walk(sourceDir, '');
  heartbeat(jobId, { status: 'synced', synced_files: count });
  return { ok: true, synced_files: count, ...verifyManifest(jobId) };
}

// Verify every manifest entry still matches its archived bytes (final-sync gate).
function verifyManifest(jobId) {
  const m = _readJSON(_manifestPath(jobId), null);
  if (!m) return { ok: false, error: 'no manifest', verified: false };
  let allMatch = true;
  const checked = [];
  for (const f of m.files || []) {
    const p = _safeInside(path.join(_dir(jobId), 'artifacts'), _safeRel(f.rel));
    let match = false;
    try { match = fs.existsSync(p) && _sha256(fs.readFileSync(p)) === f.sha256; } catch { match = false; }
    if (!match) allMatch = false;
    checked.push({ rel: f.rel, match });
  }
  m.verified = allMatch && (m.files || []).length > 0;
  m.verified_at = _now();
  _writeJSON(_manifestPath(jobId), m);
  return { ok: true, verified: m.verified, file_count: (m.files || []).length, checked };
}

function syncStatus(jobId) {
  const m = _readJSON(_manifestPath(jobId), null);
  if (!m) return { ok: false, error: 'job not initialized for persistence' };
  const age = heartbeatAge(jobId);
  return {
    ok: true, job_id: jobId, file_count: (m.files || []).length,
    last_sync: m.last_sync, verified: !!m.verified, verified_at: m.verified_at || null,
    last_heartbeat_age_s: age, heartbeat_stale: age != null && age > HEARTBEAT_STALE_S,
    unsynced_warning: !m.verified || (age != null && age > HEARTBEAT_STALE_S),
    checkpoints: listCheckpoints(jobId).length,
  };
}

function manifest(jobId) { return _readJSON(_manifestPath(jobId), { ok: false, error: 'no manifest' }); }

function artifacts(jobId) {
  const m = _readJSON(_manifestPath(jobId), { files: [] });
  return { ok: true, files: m.files || [] };
}

// Crash recovery: return latest checkpoint + manifest so a job can resume.
function recover(jobId) {
  const cks = listCheckpoints(jobId);
  const latest = cks[0]
    ? _readJSON(path.join(_dir(jobId), 'checkpoints', `${cks[0].name}.json`), null)
    : null;
  return { ok: true, job_id: jobId, latest_checkpoint: latest, checkpoints: cks, manifest: manifest(jobId) };
}

// Teardown is allowed ONLY after the final sync is verified — never lose work.
function safeTeardown(jobId, { force } = {}) {
  const v = verifyManifest(jobId);
  if (!v.verified && !force) {
    return { ok: false, allowed: false, reason: 'final sync not verified — refusing teardown. Run force-sync first (or pass force to override).', verify: v };
  }
  heartbeat(jobId, { status: 'torn_down' });
  return { ok: true, allowed: true, verified: v.verified, forced: !!force, note: 'Remote may be released; local archive retained as source of truth.' };
}

module.exports = {
  initJob, heartbeat, heartbeatAge, writeCheckpoint, listCheckpoints, collectArtifact,
  forceSync, verifyManifest, syncStatus, manifest, artifacts, recover, safeTeardown,
  ARCHIVE_ROOT,
};
