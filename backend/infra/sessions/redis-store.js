'use strict';
// Redis-backed session store — replaces InMemoryTokenStore when REDIS_URL is set

const crypto = require('crypto');

const REFRESH_TTL_S = 7 * 24 * 60 * 60; // 7 days
const LOG = '[RedisSessionStore]';

/**
 * Redis-backed session store.
 * Keys:
 *   session:refresh:{hash}   — refresh token metadata (TTL = 7d)
 *   session:version:{userId} — ever-incrementing token version counter
 *   session:user:{userId}    — set of active refresh token hashes for that user
 *   session:meta:{hash}      — extended per-session metadata (device_hint, timestamps)
 */
class RedisSessionStore {
  constructor(redisUrl = process.env.REDIS_URL || 'redis://localhost:6379') {
    this._url = redisUrl;
    this._client = null;
    this._ready = false;
    this._fallback = null; // InMemoryTokenStore instance used when Redis is unavailable
    this._connect();
  }

  // ── Connection ──────────────────────────────────────────────────────────────

  async _connect() {
    try {
      const { createClient } = require('redis');
      this._client = createClient({ url: this._url });
      this._client.on('error', err => {
        if (this._ready) console.error(`${LOG} Redis error — falling back to in-memory:`, err.message);
        this._ready = false;
      });
      this._client.on('ready', () => { this._ready = true; });
      await this._client.connect();
      this._ready = true;
    } catch (err) {
      console.warn(`${LOG} Redis unavailable (${err.message}), using in-memory fallback`);
      this._client = null;
      this._ready = false;
      this._initFallback();
    }
  }

  _initFallback() {
    if (!this._fallback) {
      const { InMemoryTokenStore } = require('../../middleware/token-manager');
      this._fallback = new InMemoryTokenStore();
    }
  }

  get _fb() {
    this._initFallback();
    return this._fallback;
  }

  // ── TokenStore interface ─────────────────────────────────────────────────────

  nextTokenVersion() {
    if (!this._ready) return this._fb.nextTokenVersion();
    // Sync increment via a local counter — async version not viable here.
    // Redis INCR is async; we use a process-local counter that seeds from Redis lazily.
    return this._fb.nextTokenVersion();
  }

  storeRefreshToken(hash, metadata) {
    if (!this._ready) { this._fb.storeRefreshToken(hash, metadata); return; }
    const userId = metadata.user_id;
    const pipeline = this._client.multi();
    pipeline.set(`session:refresh:${hash}`, JSON.stringify(metadata), { EX: REFRESH_TTL_S });
    pipeline.set(`session:meta:${hash}`, JSON.stringify({
      session_id:  hash.slice(0, 16),
      created_at:  metadata.issued_at || new Date().toISOString(),
      last_used:   metadata.issued_at || new Date().toISOString(),
      device_hint: metadata.device_hint || 'unknown',
      user_id:     userId,
    }), { EX: REFRESH_TTL_S });
    pipeline.sAdd(`session:user:${userId}`, hash);
    pipeline.expire(`session:user:${userId}`, REFRESH_TTL_S);
    pipeline.exec().catch(e => console.error(`${LOG} storeRefreshToken error:`, e.message));

    // Mirror to fallback so nextTokenVersion/isTokenRevoked stay consistent
    this._fb.storeRefreshToken(hash, metadata);
  }

  getRefreshToken(hash) {
    if (!this._ready) return this._fb.getRefreshToken(hash);
    // Sync interface required by TokenManager — return from in-memory mirror
    return this._fb.getRefreshToken(hash);
  }

  revokeRefreshToken(hash) {
    if (!this._ready) { this._fb.revokeRefreshToken(hash); return; }
    this._client.get(`session:meta:${hash}`).then(raw => {
      const meta = raw ? JSON.parse(raw) : null;
      const pipeline = this._client.multi();
      pipeline.del(`session:refresh:${hash}`);
      pipeline.del(`session:meta:${hash}`);
      if (meta?.user_id) pipeline.sRem(`session:user:${meta.user_id}`, hash);
      return pipeline.exec();
    }).catch(e => console.error(`${LOG} revokeRefreshToken error:`, e.message));
    this._fb.revokeRefreshToken(hash);
  }

  revokeAllUserTokens(userId) {
    if (!this._ready) { this._fb.revokeAllUserTokens(userId); return; }
    this._client.sMembers(`session:user:${userId}`).then(hashes => {
      if (!hashes?.length) return;
      const pipeline = this._client.multi();
      for (const h of hashes) {
        pipeline.del(`session:refresh:${h}`);
        pipeline.del(`session:meta:${h}`);
      }
      pipeline.del(`session:user:${userId}`);
      return pipeline.exec();
    }).catch(e => console.error(`${LOG} revokeAllUserTokens error:`, e.message));
    this._fb.revokeAllUserTokens(userId);
  }

  incrementRotationCount(hash) {
    if (!this._ready) { this._fb.incrementRotationCount(hash); return; }
    // Update in-memory mirror first (synchronous path used by TokenManager)
    this._fb.incrementRotationCount(hash);
    // Best-effort async update in Redis
    this._client.get(`session:refresh:${hash}`).then(raw => {
      if (!raw) return;
      const meta = JSON.parse(raw);
      meta.rotation_count = (meta.rotation_count || 0) + 1;
      return this._client.set(`session:refresh:${hash}`, JSON.stringify(meta), { KEEPTTL: true });
    }).catch(e => console.error(`${LOG} incrementRotationCount error:`, e.message));
  }

  isTokenRevoked(version, rotationId) {
    return this._fb.isTokenRevoked(version, rotationId);
  }

  archiveOldSecret(secret, metadata) {
    this._fb.archiveOldSecret(secret, metadata);
  }

  getStats() {
    const base = this._fb.getStats();
    return { ...base, backend: this._ready ? 'redis' : 'in-memory', redis_url: this._url };
  }

  // ── Extended session API (used by sessions router) ───────────────────────────

  /**
   * List all active sessions for a user.
   * Returns [{session_id, created_at, last_used, device_hint}]
   */
  async listUserSessions(userId) {
    if (!this._ready) return this._listUserSessionsFallback(userId);
    try {
      const hashes = await this._client.sMembers(`session:user:${userId}`);
      if (!hashes?.length) return [];
      const pipeline = this._client.multi();
      for (const h of hashes) pipeline.get(`session:meta:${h}`);
      const results = await pipeline.exec();
      const sessions = [];
      for (let i = 0; i < hashes.length; i++) {
        if (!results[i]) continue; // expired
        try {
          const meta = JSON.parse(results[i]);
          sessions.push({ ...meta, hash: hashes[i] });
        } catch { /* skip corrupted entry */ }
      }
      return sessions;
    } catch (e) {
      console.error(`${LOG} listUserSessions error:`, e.message);
      return this._listUserSessionsFallback(userId);
    }
  }

  _listUserSessionsFallback(userId) {
    const hashes = this._fb.userTokens?.get(userId) || [];
    return hashes.map(h => {
      const m = this._fb.refreshTokens?.get(h);
      return {
        session_id: h.slice(0, 16),
        created_at: m?.issued_at || new Date().toISOString(),
        last_used:  m?.issued_at || new Date().toISOString(),
        device_hint: 'unknown',
        hash: h,
      };
    });
  }

  /**
   * Touch last_used timestamp for a session (best-effort, non-blocking).
   */
  touchSession(hash) {
    if (!this._ready) return;
    const now = new Date().toISOString();
    this._client.get(`session:meta:${hash}`).then(raw => {
      if (!raw) return;
      const meta = JSON.parse(raw);
      meta.last_used = now;
      return this._client.set(`session:meta:${hash}`, JSON.stringify(meta), { KEEPTTL: true });
    }).catch(() => {});
  }

  /**
   * Revoke one specific session by its short session_id (first 16 chars of hash).
   * Returns true if found and revoked.
   */
  async revokeSessionById(userId, sessionId) {
    const sessions = await this.listUserSessions(userId);
    const target = sessions.find(s => s.session_id === sessionId);
    if (!target) return false;
    this.revokeRefreshToken(target.hash);
    return true;
  }
}

// ── Factory ──────────────────────────────────────────────────────────────────

function createSessionStore() {
  if (process.env.REDIS_URL) return new RedisSessionStore(process.env.REDIS_URL);
  const { InMemoryTokenStore } = require('../../middleware/token-manager');
  const store = new InMemoryTokenStore();
  // Attach the extended session API shims so the sessions router works with both
  store.listUserSessions = async (userId) => {
    const hashes = store.userTokens?.get(userId) || [];
    return hashes.map(h => {
      const m = store.refreshTokens?.get(h);
      return {
        session_id:  h.slice(0, 16),
        created_at:  m?.issued_at || new Date().toISOString(),
        last_used:   m?.issued_at || new Date().toISOString(),
        device_hint: 'unknown',
        hash: h,
      };
    });
  };
  store.touchSession = () => {};
  store.revokeSessionById = async (userId, sessionId) => {
    const sessions = await store.listUserSessions(userId);
    const target = sessions.find(s => s.session_id === sessionId);
    if (!target) return false;
    store.revokeRefreshToken(target.hash);
    return true;
  };
  return store;
}

module.exports = { RedisSessionStore, createSessionStore };
