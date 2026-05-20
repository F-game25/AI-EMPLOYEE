'use strict';

/**
 * Secrets Rotation Manager — Secure key rotation and vault integration
 *
 * Features:
 *  - JWT secret rotation every 30 days
 *  - HMAC key rotation for event signing
 *  - .env-based storage (secure, not in code)
 *  - HashiCorp Vault integration (if available)
 *  - Secret masking in logs
 *  - Rotation endpoint (admin only)
 *  - Old key retention for transition period (30 days)
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');

const LOG = '[SecretsRotation]';

// Default rotation intervals (milliseconds)
const ROTATION_INTERVALS = {
  JWT_SECRET: 30 * 24 * 60 * 60 * 1000, // 30 days
  HMAC_KEY: 30 * 24 * 60 * 60 * 1000, // 30 days
  API_KEY: 90 * 24 * 60 * 60 * 1000, // 90 days
};

const RETENTION_PERIOD = 30 * 24 * 60 * 60 * 1000; // Keep old keys for 30 days

class SecretsRotationManager {
  constructor(options = {}) {
    this.envPath = options.envPath || path.join(os.homedir(), '.ai-employee', '.env');
    this.vaultUrl = options.vaultUrl || process.env.VAULT_ADDR;
    this.vaultToken = options.vaultToken || process.env.VAULT_TOKEN;
    this.enableVault = options.enableVault !== false && !!(this.vaultUrl && this.vaultToken);
    this.rotationHistory = new Map(); // key_name -> [{ key, rotated_at, expires_at }]
    this.maskPatterns = options.maskPatterns || this._defaultMaskPatterns();
  }

  /**
   * Get a secret, preferring vault if available, fallback to .env
   */
  async getSecret(name) {
    // Try vault first
    if (this.enableVault) {
      try {
        const vaultSecret = await this._getFromVault(name);
        if (vaultSecret) return vaultSecret;
      } catch (err) {
        console.warn(`${LOG} Vault lookup failed for ${name}: ${err.message}`);
      }
    }

    // Fallback to .env
    return this._getFromEnv(name);
  }

  /**
   * Rotate a secret: generate new key, store old one, update .env
   */
  async rotateSecret(name, generator = null) {
    const oldSecret = this._getFromEnv(name);
    const newSecret = generator ? generator() : crypto.randomBytes(32).toString('hex');

    // Archive old secret
    if (oldSecret) {
      if (!this.rotationHistory.has(name)) {
        this.rotationHistory.set(name, []);
      }
      const archive = this.rotationHistory.get(name);
      archive.push({
        key: oldSecret,
        rotated_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + RETENTION_PERIOD).toISOString(),
      });

      // Keep only recent 5 versions
      if (archive.length > 5) {
        archive.shift();
      }
    }

    // Update .env
    this._updateEnv(name, newSecret);

    // Update vault if enabled
    if (this.enableVault) {
      try {
        await this._storeInVault(name, newSecret);
      } catch (err) {
        console.error(`${LOG} Failed to update secret in vault: ${err.message}`);
        throw err;
      }
    }

    return { name, rotated_at: new Date().toISOString(), new_key_preview: `${newSecret.slice(0, 4)}...` };
  }

  /**
   * Get all secrets for a service (for bundle rotation)
   */
  async rotateAllSecrets() {
    const secrets = ['JWT_SECRET_KEY', 'HMAC_KEY', 'API_GATEWAY_KEY'];
    const results = [];

    for (const secretName of secrets) {
      try {
        const result = await this.rotateSecret(secretName);
        results.push(result);
      } catch (err) {
        console.error(`${LOG} Failed to rotate ${secretName}: ${err.message}`);
        results.push({ name: secretName, error: err.message });
      }
    }

    return results;
  }

  /**
   * Check if a secret needs rotation
   */
  shouldRotate(name) {
    const lastRotation = this._getLastRotationTime(name);
    const interval = ROTATION_INTERVALS[name] || ROTATION_INTERVALS.JWT_SECRET;
    return Date.now() - lastRotation > interval;
  }

  /**
   * Mask sensitive values in logs/output
   */
  maskSecrets(text) {
    if (!text || typeof text !== 'string') return text;

    let masked = text;
    for (const [pattern, replacement] of this.maskPatterns) {
      masked = masked.replace(pattern, replacement);
    }
    return masked;
  }

  /**
   * Get rotation status for all secrets
   */
  getRotationStatus() {
    const secrets = ['JWT_SECRET_KEY', 'HMAC_KEY', 'API_GATEWAY_KEY'];
    const status = {};

    for (const secretName of secrets) {
      const lastRotation = this._getLastRotationTime(secretName);
      const interval = ROTATION_INTERVALS[secretName] || ROTATION_INTERVALS.JWT_SECRET;
      const nextRotation = new Date(lastRotation + interval);
      const shouldRotate = Date.now() > lastRotation + interval;

      status[secretName] = {
        last_rotated: new Date(lastRotation).toISOString(),
        next_rotation: nextRotation.toISOString(),
        days_until_rotation: Math.max(0, Math.ceil((nextRotation - Date.now()) / (1000 * 60 * 60 * 24))),
        should_rotate_now: shouldRotate,
      };
    }

    return status;
  }

  /**
   * Get archived keys (for transition period)
   */
  getArchivedKeys(name) {
    const archive = this.rotationHistory.get(name) || [];
    const now = Date.now();

    return archive.filter(entry => new Date(entry.expires_at) > now);
  }

  // ── Internal methods ──────────────────────────────────────────────────────

  _getFromEnv(name) {
    try {
      if (!fs.existsSync(this.envPath)) return null;
      const content = fs.readFileSync(this.envPath, 'utf8');
      const match = content.match(new RegExp(`^${name}=(.+)$`, 'm'));
      return match ? match[1].trim() : null;
    } catch (err) {
      console.error(`${LOG} Error reading .env: ${err.message}`);
      return null;
    }
  }

  _updateEnv(name, value) {
    try {
      // Ensure directory exists
      const dir = path.dirname(this.envPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
      }

      // Read existing content
      let content = '';
      if (fs.existsSync(this.envPath)) {
        content = fs.readFileSync(this.envPath, 'utf8');
      }

      // Update or add variable
      const lines = content.split('\n');
      let found = false;
      const newLines = lines.map(line => {
        if (line.startsWith(`${name}=`)) {
          found = true;
          return `${name}=${value}`;
        }
        return line;
      });

      if (!found) {
        newLines.push(`${name}=${value}`);
      }

      // Write back with secure permissions
      const newContent = newLines.filter(l => l.trim()).join('\n') + '\n';
      fs.writeFileSync(this.envPath, newContent, { mode: 0o600 });

      console.info(`${LOG} Updated ${name} in ${this.envPath}`);
    } catch (err) {
      console.error(`${LOG} Error updating .env: ${err.message}`);
      throw err;
    }
  }

  async _getFromVault(name) {
    if (!this.enableVault) return null;

    try {
      const response = await fetch(`${this.vaultUrl}/v1/secret/data/ai-employee/${name}`, {
        method: 'GET',
        headers: {
          'X-Vault-Token': this.vaultToken,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        if (response.status === 404) return null;
        throw new Error(`Vault error: ${response.status}`);
      }

      const data = await response.json();
      return data.data?.data?.value;
    } catch (err) {
      console.error(`${LOG} Vault lookup error: ${err.message}`);
      return null;
    }
  }

  async _storeInVault(name, value) {
    if (!this.enableVault) return;

    const response = await fetch(`${this.vaultUrl}/v1/secret/data/ai-employee/${name}`, {
      method: 'POST',
      headers: {
        'X-Vault-Token': this.vaultToken,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ data: { value } }),
    });

    if (!response.ok) {
      throw new Error(`Vault error: ${response.status} ${await response.text()}`);
    }
  }

  _getLastRotationTime(name) {
    // For now, return a fixed time in the past
    // In production, this would read from audit log
    return Date.now() - ROTATION_INTERVALS[name] + 1000 * 60 * 60 * 24; // 1 day ago
  }

  _defaultMaskPatterns() {
    return [
      [/JWT_SECRET_KEY=[^\s]+/g, 'JWT_SECRET_KEY=[REDACTED]'],
      [/HMAC_KEY=[^\s]+/g, 'HMAC_KEY=[REDACTED]'],
      [/API_KEY=[^\s]+/g, 'API_KEY=[REDACTED]'],
      [/authorization:\s*Bearer\s+[^\s]+/gi, 'Authorization: Bearer [REDACTED]'],
      [/token=[^\s&]+/gi, 'token=[REDACTED]'],
      [/"token"\s*:\s*"[^"]+"/g, '"token": "[REDACTED]"'],
    ];
  }
}

/**
 * Express middleware for admin-only rotation endpoint
 */
function rotateSecretsEndpoint(secretsManager) {
  return async (req, res, next) => {
    try {
      // Only org_admin+ can rotate
      const role = req.user?.role;
      if (role !== 'super_admin' && role !== 'org_admin') {
        return res.status(403).json({
          error: 'Only admins can rotate secrets',
          code: 'PERMISSION_DENIED',
        });
      }

      const results = await secretsManager.rotateAllSecrets();
      const status = secretsManager.getRotationStatus();

      return res.json({
        ok: true,
        rotated: results,
        next_rotation_schedule: status,
      });
    } catch (err) {
      return res.status(500).json({
        error: `Rotation failed: ${err.message}`,
        code: 'ROTATION_ERROR',
      });
    }
  };
}

module.exports = {
  SecretsRotationManager,
  rotateSecretsEndpoint,
  ROTATION_INTERVALS,
};
