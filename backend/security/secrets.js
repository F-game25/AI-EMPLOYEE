'use strict';

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
