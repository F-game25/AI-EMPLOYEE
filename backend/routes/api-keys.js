'use strict'
/**
 * API key management for programmatic / machine-to-machine access.
 *
 * Keys are generated as `aie_<32-byte hex>` (65 chars total) and stored
 * as SHA-256 hashes so the plaintext never persists past the creation
 * response.  Storage is per-tenant in
 *   ~/.ai-employee/tenants/<tenant_id>/api_keys.json
 *
 * Routes (all require Bearer JWT):
 *   POST   /api/api-keys          — generate a new key
 *   GET    /api/api-keys          — list keys (prefix-masked)
 *   DELETE /api/api-keys/:key_id  — revoke a key
 */

const express = require('express')
const crypto = require('crypto')
const fs = require('fs').promises
const path = require('path')

const AI_HOME = path.join(process.env.HOME || process.env.USERPROFILE || '', '.ai-employee')

// ── helpers ─────────────────────────────────────────────────────────────────

function _keysPath(tenantId) {
  return path.join(AI_HOME, 'tenants', tenantId, 'api_keys.json')
}

async function _loadKeys(tenantId) {
  try {
    const raw = await fs.readFile(_keysPath(tenantId), 'utf8')
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

async function _saveKeys(tenantId, data) {
  const p = _keysPath(tenantId)
  await fs.mkdir(path.dirname(p), { recursive: true })
  await fs.writeFile(p, JSON.stringify(data, null, 2), 'utf8')
}

function _sha256(text) {
  return crypto.createHash('sha256').update(text).digest('hex')
}

function _mask(plainKey) {
  // Show prefix `aie_` + first 6 chars, then asterisks
  return plainKey.slice(0, 10) + '****'
}

// ── router factory ───────────────────────────────────────────────────────────

module.exports = function createApiKeysRouter(requireAuth) {
  const router = express.Router()

  /**
   * POST /api/api-keys
   * Generate a new API key for the authenticated tenant.
   * Body (optional): { name: "my key label" }
   * Returns: { ok, key_id, key, created_at }  ← plaintext key shown once only
   */
  router.post('/api-keys', requireAuth, async (req, res) => {
    try {
      const payload = req.jwtPayload || {}
      const tenantId = payload.tenant_id || 'default'
      const userId = payload.sub || payload.user_id || 'unknown'
      const label = (req.body && req.body.name) ? String(req.body.name).slice(0, 80) : 'default'

      const rawKey = 'aie_' + crypto.randomBytes(32).toString('hex')
      const keyHash = _sha256(rawKey)
      const keyId = crypto.randomBytes(8).toString('hex')   // stable ID for revocation
      const createdAt = new Date().toISOString()

      const keys = await _loadKeys(tenantId)
      keys[keyId] = {
        key_id: keyId,
        hash: keyHash,
        label,
        created_by: userId,
        created_at: createdAt,
        last_used_at: null,
      }
      await _saveKeys(tenantId, keys)

      // The plaintext key is returned exactly once and never stored
      return res.status(201).json({ ok: true, key_id: keyId, key: rawKey, created_at: createdAt })
    } catch (err) {
      return res.status(500).json({ ok: false, error: err.message })
    }
  })

  /**
   * GET /api/api-keys
   * List API keys for the current tenant (plaintext never returned).
   * Returns: { ok, keys: [{ key_id, label, prefix, created_at, last_used_at }] }
   */
  router.get('/api-keys', requireAuth, async (req, res) => {
    try {
      const tenantId = (req.jwtPayload || {}).tenant_id || 'default'
      const keys = await _loadKeys(tenantId)
      const list = Object.values(keys).map(k => ({
        key_id: k.key_id,
        label: k.label,
        prefix: 'aie_****',   // never reveal even the suffix
        created_by: k.created_by,
        created_at: k.created_at,
        last_used_at: k.last_used_at,
      }))
      return res.json({ ok: true, keys: list })
    } catch (err) {
      return res.status(500).json({ ok: false, error: err.message })
    }
  })

  /**
   * DELETE /api/api-keys/:key_id
   * Revoke (delete) an API key by its key_id.
   * Returns: { ok, revoked }
   */
  router.delete('/api-keys/:key_id', requireAuth, async (req, res) => {
    try {
      const tenantId = (req.jwtPayload || {}).tenant_id || 'default'
      const { key_id } = req.params
      const keys = await _loadKeys(tenantId)
      if (!keys[key_id]) {
        return res.status(404).json({ ok: false, error: 'Key not found' })
      }
      delete keys[key_id]
      await _saveKeys(tenantId, keys)
      return res.json({ ok: true, revoked: key_id })
    } catch (err) {
      return res.status(500).json({ ok: false, error: err.message })
    }
  })

  return router
}
