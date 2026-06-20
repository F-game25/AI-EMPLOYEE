'use strict';
/**
 * Sentinel guard enforcement (Node side).
 *
 * The Python BlacklightEngine sentinel writes two state files when it blocks a threat:
 *   - state/blocked_ips.json   — [{ ip, reason, blocked_at, by }]
 *   - state/sensitive_lock.json — { locked, scope[], reason, locked_at, by }
 *
 * These helpers ENFORCE those decisions in the Node runtime so the guard's actions are
 * real (no fake states): blocked IPs are rejected at the edge, and all sensitive-store
 * access (secrets / API keys / wallet / money / vaults) is denied while locked.
 * Files are cached with a short TTL so enforcement reacts within ~1.5s of a block
 * without a disk read per request.
 */
const fs = require('fs');
const path = require('path');

const STATE_DIR = require('../state-paths').STATE_DIR;  // canonical, not repo-local (C0)
const BLOCKED_IPS_FILE = path.join(STATE_DIR, 'blocked_ips.json');
const SENSITIVE_LOCK_FILE = path.join(STATE_DIR, 'sensitive_lock.json');
const TTL_MS = 1500;

let _ipCache = { at: 0, set: new Set() };
let _lockCache = { at: 0, value: null };

function _readJSON(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}

function blockedIps() {
  const now = Date.now();
  if (now - _ipCache.at > TTL_MS) {
    const list = _readJSON(BLOCKED_IPS_FILE, []);
    _ipCache = {
      at: now,
      set: new Set((Array.isArray(list) ? list : []).map(e => (typeof e === 'string' ? e : e && e.ip)).filter(Boolean)),
    };
  }
  return _ipCache.set;
}

function isIpBlocked(ip) {
  if (!ip) return false;
  const norm = String(ip).replace(/^::ffff:/, '');
  return blockedIps().has(ip) || blockedIps().has(norm);
}

function sensitiveLock() {
  const now = Date.now();
  if (now - _lockCache.at > TTL_MS) {
    _lockCache = { at: now, value: _readJSON(SENSITIVE_LOCK_FILE, null) };
  }
  return _lockCache.value;
}

function isSensitiveLocked() {
  const l = sensitiveLock();
  return !!(l && l.locked === true);
}

/** Express middleware: reject requests from sentinel-blocked IPs (keep attackers out). */
function ipBlockMiddleware(req, res, next) {
  const ip = (req.ip || req.connection?.remoteAddress || '').replace(/^::ffff:/, '');
  if (isIpBlocked(ip)) {
    return res.status(403).json({ error: 'blocked', reason: 'IP blocked by security guard' });
  }
  next();
}

module.exports = { isIpBlocked, isSensitiveLocked, sensitiveLock, ipBlockMiddleware, BLOCKED_IPS_FILE, SENSITIVE_LOCK_FILE };
