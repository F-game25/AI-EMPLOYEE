'use strict';

/**
 * Enterprise Secrets Broker
 *
 * Replaces the existing SecretStore (direct env var reads) with a
 * tiered, auditable, rotation-aware secrets management system.
 *
 * Backend priority (first available wins):
 *   1. HashiCorp Vault (KV v2 engine)  — VAULT_ADDR + VAULT_TOKEN
 *   2. AWS Secrets Manager              — AWS_REGION + credentials chain
 *   3. Encrypted local store            — AES-256-GCM encrypted JSON file
 *   4. Environment variables            — always available (existing behaviour)
 *
 * Key capabilities:
 *   - Secrets never logged, never returned in API responses
 *   - Per-agent scoped access: agent only receives declared secret keys
 *   - Rotation: versioned secrets, rotate without restart
 *   - TTL: time-bound leases; auto-revoke on expiry
 *   - Audit: every get/set/rotate written to audit log
 *   - Multi-tenant: secret paths namespaced by tenant_id
 *
 * Secret path schema:
 *   aie/{tenant_id}/agents/{agent_id}/{key}
 *   aie/{tenant_id}/system/{key}
 *   aie/{tenant_id}/llm/{provider}/{key}
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const LOG = '[SecretsBroker]';

// Best-effort security telemetry → Python sentinel (BlacklightEngine).
// Never throws; never carries secret values.
let _forwardSecurityEvent = () => {};
try {
  ({ forwardSecurityEvent: _forwardSecurityEvent } = require('../../security/security_event_forwarder'));
} catch { /* forwarder unavailable — telemetry silently disabled */ }

// In-memory burst detector: >20 reads / 10s per tenant|agent → suspicious.
const _BURST_WINDOW_MS = 10_000;
const _BURST_THRESHOLD = 20;
const _readWindows = new Map();  // 'tenant|agent' → number[] (timestamps)

function _recordReadAndCheckBurst(tenant_id, agent_id) {
  const k = `${tenant_id}|${agent_id || ''}`;
  const now = Date.now();
  const hits = (_readWindows.get(k) || []).filter(t => now - t < _BURST_WINDOW_MS);
  hits.push(now);
  _readWindows.set(k, hits);
  return hits.length > _BURST_THRESHOLD;
}

function _emit(eventType, payload) {
  try { _forwardSecurityEvent(eventType, payload); } catch { /* never break secrets access */ }
}
const STATE_DIR = path.resolve(process.env.STATE_DIR || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || process.env.HOME || '/tmp', '.ai-employee', 'state'));
const AUDIT_LOG_PATH = path.join(STATE_DIR, 'secrets-audit.jsonl');

// Encryption key from env (32 bytes hex) or derived from JWT secret
const _rawKey = process.env.JWT_SECRET_KEY;
if (!process.env.SECRETS_ENCRYPTION_KEY && !_rawKey) throw new Error('[secrets/broker] JWT_SECRET_KEY is required');
const LOCAL_STORE_KEY = process.env.SECRETS_ENCRYPTION_KEY
  ? Buffer.from(process.env.SECRETS_ENCRYPTION_KEY, 'hex').slice(0, 32)
  : crypto.createHash('sha256').update(_rawKey).digest().slice(0, 32);

const LOCAL_STORE_PATH = path.join(
  STATE_DIR,
  'secrets.enc'
);

// ── Vault backend ─────────────────────────────────────────────────────────────

class VaultBackend {
  constructor() {
    this._addr  = process.env.VAULT_ADDR  || 'http://localhost:8200';
    this._token = process.env.VAULT_TOKEN || '';
    this._mount = process.env.VAULT_MOUNT || 'secret';
  }

  get name() { return 'vault'; }

  async available() {
    try {
      const res = await fetch(`${this._addr}/v1/sys/health`, {
        headers: { 'X-Vault-Token': this._token },
        signal: AbortSignal.timeout(2000),
      });
      return res.ok;
    } catch { return false; }
  }

  async get(path) {
    const res = await fetch(`${this._addr}/v1/${this._mount}/data/${path}`, {
      headers: { 'X-Vault-Token': this._token },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.data?.data || null;
  }

  async set(path, value, metadata = {}) {
    const res = await fetch(`${this._addr}/v1/${this._mount}/data/${path}`, {
      method: 'POST',
      headers: { 'X-Vault-Token': this._token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: value, options: { cas: 0 } }),
      signal: AbortSignal.timeout(5000),
    });
    return res.ok;
  }

  async rotate(path, newValue) {
    return this.set(path, newValue);
  }

  async delete(path) {
    const res = await fetch(`${this._addr}/v1/${this._mount}/data/${path}`, {
      method: 'DELETE',
      headers: { 'X-Vault-Token': this._token },
    });
    return res.ok;
  }
}

// ── AWS Secrets Manager backend ───────────────────────────────────────────────

class AwsSecretsBackend {
  get name() { return 'aws-secrets-manager'; }

  async available() {
    try {
      const { SecretsManagerClient, ListSecretsCommand } = require('@aws-sdk/client-secrets-manager');
      this._client = new SecretsManagerClient({ region: process.env.AWS_REGION || 'us-east-1' });
      await this._client.send(new ListSecretsCommand({ MaxResults: 1 }));
      return true;
    } catch { return false; }
  }

  async get(secretPath) {
    const { GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
    try {
      const res = await this._client.send(new GetSecretValueCommand({ SecretId: secretPath }));
      return res.SecretString ? JSON.parse(res.SecretString) : null;
    } catch { return null; }
  }

  async set(secretPath, value) {
    const { CreateSecretCommand, UpdateSecretCommand } = require('@aws-sdk/client-secrets-manager');
    const str = JSON.stringify(value);
    try {
      await this._client.send(new CreateSecretCommand({ Name: secretPath, SecretString: str }));
    } catch {
      await this._client.send(new UpdateSecretCommand({ SecretId: secretPath, SecretString: str }));
    }
    return true;
  }

  async rotate(secretPath, newValue) { return this.set(secretPath, newValue); }
  async delete(secretPath) { return false; }  // requires additional permissions
}

// ── Encrypted local backend ───────────────────────────────────────────────────

class LocalEncryptedBackend {
  constructor() {
    this._store = {};
    this._loaded = false;
  }

  get name() { return 'local-encrypted'; }
  async available() { return true; }

  _load() {
    if (this._loaded) return;
    this._loaded = true;
    try {
      if (!fs.existsSync(LOCAL_STORE_PATH)) return;
      const raw = fs.readFileSync(LOCAL_STORE_PATH);
      const iv  = raw.slice(0, 12);
      const tag = raw.slice(12, 28);
      const enc = raw.slice(28);
      const decipher = crypto.createDecipheriv('aes-256-gcm', LOCAL_STORE_KEY, iv);
      decipher.setAuthTag(tag);
      const plain = Buffer.concat([decipher.update(enc), decipher.final()]);
      this._store = JSON.parse(plain.toString('utf8'));
    } catch (e) {
      console.warn(`${LOG} Could not load encrypted secrets: ${e.message}`);
    }
  }

  _save() {
    fs.mkdirSync(path.dirname(LOCAL_STORE_PATH), { recursive: true });
    const plain = Buffer.from(JSON.stringify(this._store));
    const iv    = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', LOCAL_STORE_KEY, iv);
    const enc   = Buffer.concat([cipher.update(plain), cipher.final()]);
    const tag   = cipher.getAuthTag();
    fs.writeFileSync(LOCAL_STORE_PATH, Buffer.concat([iv, tag, enc]), { mode: 0o600 });
  }

  async get(secretPath) {
    this._load();
    return this._store[secretPath] || null;
  }

  async set(secretPath, value) {
    this._load();
    this._store[secretPath] = value;
    this._save();
    return true;
  }

  async rotate(secretPath, newValue) { return this.set(secretPath, newValue); }

  async delete(secretPath) {
    this._load();
    delete this._store[secretPath];
    this._save();
    return true;
  }
}

// ── Env backend (existing SecretStore behaviour) ──────────────────────────────

class EnvBackend {
  get name() { return 'env'; }
  async available() { return true; }

  async get(secretPath) {
    // Map path format 'aie/tenant/system/ANTHROPIC_API_KEY' → env var 'ANTHROPIC_API_KEY'
    const key = secretPath.split('/').pop();
    return process.env[key] ? { value: process.env[key] } : null;
  }

  async set() { return false; }   // env vars are read-only from this layer
  async rotate() { return false; }
  async delete() { return false; }
}

// ── Secrets Broker ────────────────────────────────────────────────────────────

class SecretsBroker {
  constructor() {
    this._backends = [];
    this._active   = null;
    this._leases   = new Map();  // path → { expires_at }
  }

  async init() {
    const candidates = [
      new VaultBackend(),
      new AwsSecretsBackend(),
      new LocalEncryptedBackend(),
      new EnvBackend(),
    ];

    for (const backend of candidates) {
      const ok = await backend.available().catch(() => false);
      if (ok) {
        this._backends.push(backend);
        if (!this._active) {
          this._active = backend;
          console.log(`${LOG} Primary backend: ${backend.name}`);
        }
      }
    }
    return this;
  }

  get backendName() { return this._active?.name ?? 'none'; }

  /**
   * Retrieve a scoped secret.
   *
   * @param {string} key           - Secret key name
   * @param {object} opts
   *   tenant_id  string
   *   agent_id   string|null  — if set, restricts to agent scope
   *   scope      'agent'|'system'|'llm'
   */
  async get(key, opts = {}) {
    const { tenant_id = 'system', agent_id = null, scope = 'system' } = opts;
    const secretPath = _buildPath(tenant_id, scope, key, agent_id);

    // Security guard: deny ALL secret/API-key/wallet access while the sentinel has
    // locked sensitive stores (responding to a detected attack). Fail closed.
    try {
      const { isSensitiveLocked } = require('../../security/sentinel_guard');
      if (isSensitiveLocked()) {
        _audit('get', secretPath, tenant_id, agent_id, false, 'sensitive_lock_active');
        _emit('vault:access_denied', { key_path: secretPath, tenant_id, agent_id, reason: 'sensitive_lock_active' });
        const err = new Error('sensitive stores locked by security guard');
        err.code = 'SENSITIVE_LOCKED';
        throw err;
      }
    } catch (e) {
      if (e && e.code === 'SENSITIVE_LOCKED') throw e;
      // guard helper unavailable — do not block normal operation
    }

    _audit('get', secretPath, tenant_id, agent_id, true);

    // Try backends in priority order
    for (const backend of this._backends) {
      try {
        const result = await backend.get(secretPath);
        if (result) {
          // Check TTL
          const lease = this._leases.get(secretPath);
          if (lease && Date.now() > lease.expires_at) {
            _audit('get', secretPath, tenant_id, agent_id, false, 'lease_expired');
            _emit('vault:access_denied', { key_path: secretPath, tenant_id, agent_id, reason: 'lease_expired' });
            return null;
          }
          const suspicious = _recordReadAndCheckBurst(tenant_id, agent_id);
          _emit('vault:access', { key_path: secretPath, tenant_id, agent_id, scope, suspicious });
          return result.value ?? (typeof result === 'string' ? result : null);
        }
      } catch (e) {
        console.warn(`${LOG} Backend ${backend.name} get failed: ${e.message}`);
      }
    }
    return null;
  }

  /**
   * Store a secret. Written to primary backend only.
   */
  async set(key, value, opts = {}) {
    const { tenant_id = 'system', agent_id = null, scope = 'system', ttl_seconds = null } = opts;
    const secretPath = _buildPath(tenant_id, scope, key, agent_id);

    // Never log the value
    _audit('set', secretPath, tenant_id, agent_id, true);

    if (ttl_seconds) {
      this._leases.set(secretPath, { expires_at: Date.now() + ttl_seconds * 1000 });
    }

    const ok = await this._active?.set(secretPath, { value, version: Date.now() });
    return ok;
  }

  /**
   * Rotate a secret — new value written, version incremented.
   */
  async rotate(key, newValue, opts = {}) {
    const { tenant_id = 'system', agent_id = null, scope = 'system' } = opts;
    const secretPath = _buildPath(tenant_id, scope, key, agent_id);
    _audit('rotate', secretPath, tenant_id, agent_id, true);
    return this._active?.rotate(secretPath, { value: newValue, version: Date.now(), rotated_at: new Date().toISOString() });
  }

  /**
   * Delete a secret.
   */
  async delete(key, opts = {}) {
    const { tenant_id = 'system', agent_id = null, scope = 'system' } = opts;
    const secretPath = _buildPath(tenant_id, scope, key, agent_id);
    _audit('delete', secretPath, tenant_id, agent_id, true);
    this._leases.delete(secretPath);
    return this._active?.delete(secretPath);
  }

  /**
   * Get scoped secrets for an agent — returns ONLY the keys the agent declares.
   * Used by SandboxExecutor to inject env vars.
   * Secret values are NEVER logged; only key names are audited.
   */
  async getScopedForAgent(agent_id, declaredKeys, tenant_id = 'system') {
    const result = {};
    for (const key of declaredKeys) {
      const value = await this.get(key, { tenant_id, agent_id, scope: 'agent' })
        || await this.get(key, { tenant_id, scope: 'system' });  // fall back to system scope
      if (value != null) result[key] = value;
    }
    _audit('agent_inject', `${tenant_id}/agents/${agent_id}`, tenant_id, agent_id, true,
           `injected_keys=[${declaredKeys.join(',')}]`);
    return result;
  }

  /**
   * Revoke all leases for an agent (e.g. on agent stop).
   */
  revokeAgentLeases(agent_id, tenant_id = 'system') {
    const prefix = `aie/${tenant_id}/agents/${agent_id}/`;
    for (const [path] of this._leases) {
      if (path.startsWith(prefix)) {
        this._leases.delete(path);
        _audit('revoke', path, tenant_id, agent_id, true);
      }
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _buildPath(tenant_id, scope, key, agent_id) {
  if (scope === 'agent' && agent_id) {
    return `aie/${tenant_id}/agents/${agent_id}/${key}`;
  }
  return `aie/${tenant_id}/${scope}/${key}`;
}

function _audit(action, path, tenant_id, agent_id, success, detail = '') {
  try {
    fs.mkdirSync(path.dirname(AUDIT_LOG_PATH), { recursive: true });
    const line = JSON.stringify({
      ts: new Date().toISOString(),
      action,
      secret_path: path,
      tenant_id,
      agent_id,
      success,
      detail,
    }) + '\n';
    fs.appendFileSync(AUDIT_LOG_PATH, line);
  } catch {}
}

// ── Singleton ─────────────────────────────────────────────────────────────────

let _broker = null;

async function getSecretsBroker() {
  if (_broker) return _broker;
  _broker = new SecretsBroker();
  await _broker.init();
  return _broker;
}

module.exports = { getSecretsBroker, SecretsBroker };
