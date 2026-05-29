'use strict';

// NOTE: SecretStore is a synchronous config/env accessor (plain process.env
// reads used for app bootstrap config), not the runtime secrets/wallet/API-key
// vault read path. The auditable vault read path lives in
// backend/infra/secrets/broker.js, which is instrumented to emit vault:access /
// vault:access_denied telemetry to the Python sentinel. Instrumenting these
// env lookups would emit on every config read (noise, no attack signal), so it
// is intentionally left uninstrumented.
class SecretStore {
  constructor(env = process.env) {
    this._env = env;
    this._required = new Set();
  }

  get(name, options = {}) {
    const aliases = Array.isArray(options.aliases) ? options.aliases : [];
    const required = Boolean(options.required);
    const allowEmpty = Boolean(options.allowEmpty);
    const defaultValue = options.defaultValue;
    if (required) this._required.add(name);
    const keys = [name, ...aliases];
    for (const key of keys) {
      const raw = this._env[key];
      if (raw === undefined || raw === null) continue;
      const value = String(raw);
      if (!allowEmpty && !value.trim()) continue;
      return value;
    }
    return defaultValue;
  }

  describe(name, options = {}) {
    const value = this.get(name, options);
    return {
      name,
      configured: Boolean(value),
      redacted: value ? SecretStore.redact(value) : null,
    };
  }

  requiredHealth() {
    const missing = [];
    for (const name of this._required.values()) {
      if (!this.get(name)) missing.push(name);
    }
    return {
      required: Array.from(this._required.values()),
      missing,
      healthy: missing.length === 0,
    };
  }

  static redact(value) {
    const raw = String(value || '');
    if (!raw) return '';
    if (raw.length <= 6) return '*'.repeat(raw.length);
    return `${raw.slice(0, 2)}${'*'.repeat(raw.length - 4)}${raw.slice(-2)}`;
  }
}

module.exports = {
  SecretStore,
};
