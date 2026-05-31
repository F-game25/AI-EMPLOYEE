'use strict';
// Session management endpoints
// Mount with: app.use('/api', require('./routes/sessions')(requireAuth))

const router = require('express').Router();
const { createSessionStore } = require('../infra/sessions/redis-store');

// Singleton store — shared across requests
const store = createSessionStore();

/**
 * Derive a stable session_id from a request's Authorization token.
 * Uses SHA-256 of the raw Bearer token so the current session is identifiable
 * without storing the plaintext token.
 */
const crypto = require('crypto');
function currentSessionId(req) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  if (!token) return null;
  return crypto.createHash('sha256').update(token).digest('hex').slice(0, 16);
}

module.exports = function createSessionsRouter(requireAuth) {
  // ── GET /api/sessions — list active sessions for current user ──────────────
  router.get('/sessions', requireAuth, async (req, res) => {
    try {
      const userId = req.jwtPayload?.sub;
      if (!userId) return res.status(401).json({ ok: false, error: 'No user identity in token' });

      const currentId = currentSessionId(req);
      const sessions  = await store.listUserSessions(userId);

      const result = sessions.map(s => ({
        session_id:  s.session_id,
        created_at:  s.created_at,
        last_used:   s.last_used,
        device_hint: s.device_hint || 'unknown',
        current:     s.session_id === currentId,
      }));

      // Touch last_used for the current session (best-effort)
      if (currentId) {
        const cur = sessions.find(s => s.session_id === currentId);
        if (cur?.hash) store.touchSession(cur.hash);
      }

      res.json({ ok: true, sessions: result });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── DELETE /api/sessions/:session_id — revoke a specific session ───────────
  router.delete('/sessions/:session_id', requireAuth, async (req, res) => {
    try {
      const userId    = req.jwtPayload?.sub;
      const currentId = currentSessionId(req);
      const targetId  = req.params.session_id;

      if (!userId) return res.status(401).json({ ok: false, error: 'No user identity in token' });
      if (targetId === currentId) {
        return res.status(400).json({ ok: false, error: 'Cannot revoke the current session — use /api/auth/logout instead' });
      }

      const revoked = await store.revokeSessionById(userId, targetId);
      if (!revoked) return res.status(404).json({ ok: false, error: 'Session not found' });

      res.json({ ok: true, message: `Session ${targetId} revoked` });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── DELETE /api/sessions — revoke ALL sessions except current ─────────────
  router.delete('/sessions', requireAuth, async (req, res) => {
    try {
      const userId    = req.jwtPayload?.sub;
      const currentId = currentSessionId(req);
      if (!userId) return res.status(401).json({ ok: false, error: 'No user identity in token' });

      const sessions = await store.listUserSessions(userId);
      let revokedCount = 0;
      for (const s of sessions) {
        if (s.session_id === currentId) continue; // keep current
        store.revokeRefreshToken(s.hash);
        revokedCount++;
      }

      res.json({ ok: true, message: `Revoked ${revokedCount} session(s)`, revoked: revokedCount });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // ── POST /api/sessions/force-logout/:user_id — admin: revoke all sessions ──
  router.post('/sessions/force-logout/:user_id', requireAuth, (req, res) => {
    try {
      const callerRole = req.jwtPayload?.role;
      if (callerRole !== 'admin') {
        return res.status(403).json({ ok: false, error: 'Admin role required' });
      }
      const { user_id } = req.params;
      store.revokeAllUserTokens(user_id);
      res.json({ ok: true, message: `All sessions revoked for user ${user_id}` });
    } catch (err) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  return router;
};
