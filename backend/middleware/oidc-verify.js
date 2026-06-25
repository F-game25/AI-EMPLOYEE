'use strict';
// OIDC token verification for Node.js — validates RS256/ES256 tokens from external IdPs

const jwt = require('jsonwebtoken');
const crypto = require('crypto');

const LOG = '[OIDCVerify]';
const JWKS_TTL_MS = 30_000; // 30 seconds

// ---------------------------------------------------------------------------
// OIDCVerifier
// ---------------------------------------------------------------------------

class OIDCVerifier {
  constructor() {
    this._providers = [];
    /** @type {Map<string, {keys: object[], fetchedAt: number}>} */
    this._jwksCache = new Map();

    const raw = (process.env.OIDC_PROVIDERS || '').trim();
    if (!raw) return;

    let cfgs;
    try {
      cfgs = JSON.parse(raw);
      if (!Array.isArray(cfgs)) throw new Error('OIDC_PROVIDERS must be a JSON array');
    } catch (err) {
      console.error(`${LOG} failed to parse OIDC_PROVIDERS:`, err.message, '— OIDC disabled');
      return;
    }

    for (const cfg of cfgs) {
      if (!cfg.name || !cfg.issuer || !cfg.jwks_uri || !cfg.client_id || !cfg.audience) {
        console.warn(`${LOG} skipping incomplete provider config:`, JSON.stringify(cfg));
        continue;
      }
      this._providers.push({
        name: cfg.name,
        issuer: cfg.issuer,
        jwks_uri: cfg.jwks_uri,
        client_id: cfg.client_id,
        audience: cfg.audience,
        tenant_id_claim: cfg.tenant_id_claim || 'org_id',
        role_claim: cfg.role_claim || 'role',
      });
      console.info(`${LOG} registered provider '${cfg.name}' (issuer=${cfg.issuer})`);
    }
  }

  // -------------------------------------------------------------------------
  // JWKS fetch with 30-second TTL cache
  // -------------------------------------------------------------------------

  async fetchJWKS(jwksUri) {
    const cached = this._jwksCache.get(jwksUri);
    if (cached && Date.now() - cached.fetchedAt < JWKS_TTL_MS) {
      return cached.keys;
    }
    const resp = await fetch(jwksUri, { headers: { Accept: 'application/json' } });
    if (!resp.ok) throw new Error(`JWKS fetch failed: ${resp.status} ${resp.statusText}`);
    const data = await resp.json();
    const keys = data.keys || [];
    this._jwksCache.set(jwksUri, { keys, fetchedAt: Date.now() });
    return keys;
  }

  // -------------------------------------------------------------------------
  // Convert a JWK to a Node.js crypto key object (RS256 / ES256)
  // -------------------------------------------------------------------------

  _jwkToPublicKey(jwk) {
    try {
      return crypto.createPublicKey({ key: jwk, format: 'jwk' });
    } catch {
      return null;
    }
  }

  // -------------------------------------------------------------------------
  // Verify token against all registered providers
  // Returns normalised payload or null
  // -------------------------------------------------------------------------

  async verifyToken(token) {
    // Decode header to learn kid + alg without verifying signature yet
    let header;
    try {
      header = jwt.decode(token, { complete: true })?.header || {};
    } catch {
      return null;
    }
    const { kid, alg = 'RS256' } = header;

    if (!['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512'].includes(alg)) {
      return null; // Only asymmetric algorithms accepted from OIDC providers
    }

    for (const provider of this._providers) {
      try {
        const keys = await this.fetchJWKS(provider.jwks_uri);

        // Find matching key by kid (or try all if no kid)
        const candidates = kid ? keys.filter(k => k.kid === kid) : keys;
        if (!candidates.length) continue;

        for (const jwk of candidates) {
          const pubKey = this._jwkToPublicKey(jwk);
          if (!pubKey) continue;

          try {
            const payload = jwt.verify(token, pubKey, {
              algorithms: ['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512'],
              audience: provider.audience,
              issuer: provider.issuer,
            });
            return _normalizePayload(payload, provider);
          } catch (verifyErr) {
            // Wrong key or invalid token for this provider — try next
            continue;
          }
        }
      } catch (err) {
        console.warn(`${LOG} error verifying against '${provider.name}':`, err.message);
      }
    }
    return null;
  }

  get providerNames() {
    return this._providers.map(p => p.name);
  }
}

// ---------------------------------------------------------------------------
// Payload normalisation — maps IdP claims to internal schema
// ---------------------------------------------------------------------------

function _normalizePayload(payload, provider) {
  return {
    sub: payload.sub || '',
    tenant_id: payload[provider.tenant_id_claim] || payload.tenant_id || '',
    role: payload[provider.role_claim] || payload.role || 'user',
    type: 'oidc',
    provider: provider.name,
    email: payload.email || '',
  };
}

// ---------------------------------------------------------------------------
// Module-level singleton
// ---------------------------------------------------------------------------

const _verifier = new OIDCVerifier();

// ---------------------------------------------------------------------------
// Express middleware: built-in auth first, OIDC fallback
// ---------------------------------------------------------------------------

/**
 * oidcOrBuiltin(req, res, next)
 *
 * Tries the existing requireAuth logic (HMAC-signed built-in JWT) first.
 * On failure attempts OIDC verification against all registered providers.
 * Populates req.user and req.jwtPayload on success.
 */
async function oidcOrBuiltin(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : req.query?.token;

  if (!token) {
    return res.status(401).json({ error: 'unauthorized', detail: 'Missing Bearer token' });
  }

  // --- Built-in path: HMAC JWT verify ---
  const JWT_SECRET = process.env.JWT_SECRET_KEY;
  if (JWT_SECRET) {
    try {
      const payload = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
      req.jwtPayload = payload;
      req.user = payload;
      return next();
    } catch {
      // Fall through to OIDC path
    }
  }

  // --- OIDC path ---
  try {
    const payload = await _verifier.verifyToken(token);
    if (payload) {
      req.jwtPayload = payload;
      req.user = payload;
      return next();
    }
  } catch (err) {
    console.error(`${LOG} OIDC verify error:`, err.message);
  }

  return res.status(401).json({ error: 'unauthorized' });
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = { OIDCVerifier, oidcOrBuiltin, _verifier };
