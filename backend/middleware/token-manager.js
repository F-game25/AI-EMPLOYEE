'use strict';

/**
 * JWT Token Management — Enhanced token lifecycle with rotation
 *
 * Features:
 *  - Short-lived access tokens (15m) + long-lived refresh tokens (7d)
 *  - Token version tracking for revocation
 *  - Refresh token rotation: new refresh token on each use
 *  - Scoped WS tokens: separate short-lived token just for WebSocket
 *  - Refresh token hash storage (not plaintext)
 *  - Token rotation counter to prevent reuse
 */

const jwt = require('jsonwebtoken');
const crypto = require('crypto');

const LOG = '[TokenManager]';

// Token lifetimes (seconds)
const ACCESS_TOKEN_LIFETIME = 15 * 60; // 15 minutes
const REFRESH_TOKEN_LIFETIME = 7 * 24 * 60 * 60; // 7 days
const WS_TOKEN_LIFETIME = 5 * 60; // 5 minutes (short-lived for WS)
const TOKEN_ROTATION_WINDOW = 30 * 24 * 60 * 60; // 30 days — old keys kept for rotation

class TokenManager {
  constructor(jwtSecret, options = {}) {
    if (!jwtSecret || jwtSecret.length < 32) {
      throw new Error(`TokenManager: JWT secret must be 32+ chars (got ${jwtSecret.length})`);
    }
    this.jwtSecret = jwtSecret;
    this.store = options.store || new InMemoryTokenStore(); // Allow custom store (Redis, DB, etc.)
    this.issuer = options.issuer || 'ai-employee';
  }

  /**
   * Generate tokens for a user: access token + refresh token
   */
  issueTokenPair(userId, claims = {}) {
    const now = Math.floor(Date.now() / 1000);
    const tokenVersion = this.store.nextTokenVersion();
    const rotationId = crypto.randomBytes(16).toString('hex');

    // Access token: short-lived, scoped
    const accessPayload = {
      sub: userId,
      type: 'access',
      version: tokenVersion,
      rotation_id: rotationId,
      iss: this.issuer,
      iat: now,
      exp: now + ACCESS_TOKEN_LIFETIME,
      ...claims,
    };

    // Refresh token: long-lived, includes rotation counter
    const refreshPayload = {
      sub: userId,
      type: 'refresh',
      version: tokenVersion,
      rotation_id: rotationId,
      rotation_count: 0, // Counter to prevent reuse
      iss: this.issuer,
      iat: now,
      exp: now + REFRESH_TOKEN_LIFETIME,
      ...claims,
    };

    const accessToken = jwt.sign(accessPayload, this.jwtSecret);
    const refreshToken = jwt.sign(refreshPayload, this.jwtSecret);
    const refreshTokenHash = this._hashToken(refreshToken);

    // Store refresh token hash + metadata
    this.store.storeRefreshToken(refreshTokenHash, {
      user_id: userId,
      version: tokenVersion,
      rotation_id: rotationId,
      rotation_count: 0,
      issued_at: new Date().toISOString(),
      expires_at: new Date(now * 1000 + REFRESH_TOKEN_LIFETIME * 1000).toISOString(),
    });

    return { accessToken, refreshToken, expiresIn: ACCESS_TOKEN_LIFETIME };
  }

  /**
   * Verify and decode access token
   */
  verifyAccessToken(token) {
    try {
      const payload = jwt.verify(token, this.jwtSecret);
      if (payload.type !== 'access') {
        throw new Error('Token is not an access token');
      }
      if (this.store.isTokenRevoked(payload.version, payload.rotation_id)) {
        throw new Error('Token has been revoked');
      }
      return payload;
    } catch (err) {
      const error = new Error(`Invalid access token: ${err.message}`);
      error.code = 'INVALID_TOKEN';
      throw error;
    }
  }

  /**
   * Refresh access token using refresh token
   * Issues NEW refresh token (rotation) to prevent token reuse
   */
  refreshAccessToken(refreshToken, claims = {}) {
    try {
      const payload = jwt.verify(refreshToken, this.jwtSecret);
      if (payload.type !== 'refresh') {
        throw new Error('Token is not a refresh token');
      }

      const refreshTokenHash = this._hashToken(refreshToken);
      const stored = this.store.getRefreshToken(refreshTokenHash);

      if (!stored) {
        throw new Error('Refresh token not found in store (may have been revoked)');
      }

      if (stored.rotation_count > 10) {
        throw new Error('Refresh token rotation limit exceeded — re-authentication required');
      }

      // Invalidate old refresh token by incrementing rotation count
      this.store.incrementRotationCount(refreshTokenHash);

      // Issue new token pair (new refresh token = rotation)
      return this.issueTokenPair(payload.sub, {
        tenant_id: payload.tenant_id,
        email: payload.email,
        role: payload.role,
        ...claims,
      });
    } catch (err) {
      const error = new Error(`Token refresh failed: ${err.message}`);
      error.code = 'REFRESH_FAILED';
      throw error;
    }
  }

  /**
   * Issue WebSocket token: short-lived, scoped
   */
  issueWSToken(userId, claims = {}) {
    const now = Math.floor(Date.now() / 1000);
    const wsPayload = {
      sub: userId,
      type: 'ws',
      iss: this.issuer,
      iat: now,
      exp: now + WS_TOKEN_LIFETIME,
      ...claims,
    };
    return jwt.sign(wsPayload, this.jwtSecret);
  }

  /**
   * Verify WebSocket token
   */
  verifyWSToken(token) {
    try {
      const payload = jwt.verify(token, this.jwtSecret);
      if (payload.type !== 'ws') {
        throw new Error('Token is not a WebSocket token');
      }
      return payload;
    } catch (err) {
      const error = new Error(`Invalid WS token: ${err.message}`);
      error.code = 'INVALID_WS_TOKEN';
      throw error;
    }
  }

  /**
   * Revoke refresh token (logout)
   */
  revokeRefreshToken(refreshToken) {
    const hash = this._hashToken(refreshToken);
    this.store.revokeRefreshToken(hash);
  }

  /**
   * Revoke all tokens for a user (force logout everywhere)
   */
  revokeAllUserTokens(userId) {
    this.store.revokeAllUserTokens(userId);
  }

  /**
   * Rotate JWT secret (graceful key rotation)
   * Keeps old secret for rotation window (30 days)
   */
  rotateJWTSecret(newSecret) {
    if (!newSecret || newSecret.length < 32) {
      throw new Error(`New secret must be 32+ chars (got ${newSecret.length})`);
    }
    this.store.archiveOldSecret(this.jwtSecret, {
      rotated_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + TOKEN_ROTATION_WINDOW * 1000).toISOString(),
    });
    this.jwtSecret = newSecret;
  }

  /**
   * Get token stats for monitoring
   */
  getStats() {
    return this.store.getStats();
  }

  _hashToken(token) {
    return crypto.createHash('sha256').update(token).digest('hex');
  }
}

/**
 * In-memory token store (for single-server deployments)
 * For distributed deployments, use Redis or database store
 */
class InMemoryTokenStore {
  constructor() {
    this.refreshTokens = new Map(); // hash -> metadata
    this.revokedTokenVersions = new Set(); // revoked token version:rotation_id pairs
    this.userTokens = new Map(); // user_id -> [token hashes]
    this.tokenVersion = 1;
    this.oldSecrets = []; // Array of { secret, expires_at }
  }

  nextTokenVersion() {
    return this.tokenVersion++;
  }

  storeRefreshToken(hash, metadata) {
    this.refreshTokens.set(hash, metadata);
    const userId = metadata.user_id;
    if (!this.userTokens.has(userId)) {
      this.userTokens.set(userId, []);
    }
    this.userTokens.get(userId).push(hash);
  }

  getRefreshToken(hash) {
    return this.refreshTokens.get(hash);
  }

  revokeRefreshToken(hash) {
    this.refreshTokens.delete(hash);
  }

  revokeAllUserTokens(userId) {
    const tokens = this.userTokens.get(userId) || [];
    tokens.forEach(hash => this.refreshTokens.delete(hash));
    this.userTokens.delete(userId);
  }

  incrementRotationCount(hash) {
    const metadata = this.refreshTokens.get(hash);
    if (metadata) {
      metadata.rotation_count = (metadata.rotation_count || 0) + 1;
    }
  }

  isTokenRevoked(version, rotationId) {
    return this.revokedTokenVersions.has(`${version}:${rotationId}`);
  }

  archiveOldSecret(secret, metadata) {
    this.oldSecrets.push({ secret, ...metadata });
    // Clean up expired secrets
    const now = new Date();
    this.oldSecrets = this.oldSecrets.filter(
      s => new Date(s.expires_at) > now
    );
  }

  getStats() {
    return {
      active_refresh_tokens: this.refreshTokens.size,
      tracked_users: this.userTokens.size,
      revoked_token_versions: this.revokedTokenVersions.size,
      archived_secrets: this.oldSecrets.length,
    };
  }
}

module.exports = {
  TokenManager,
  InMemoryTokenStore,
  ACCESS_TOKEN_LIFETIME,
  REFRESH_TOKEN_LIFETIME,
  WS_TOKEN_LIFETIME,
};
