const fs = require('fs')
const path = require('path')
const { PATHS } = require('./paths')

const DEFAULT_POLICY = Object.freeze({
  network: {
    offlineByDefault: true,
    allowDependencyInstall: false,
    allowModelDownloads: false,
    allowAutoUpdate: false,
  },
  security: {
    bindHost: '127.0.0.1',
    requireApprovalForMoneyMode: true,
  },
})

function deepMerge(base, override) {
  const out = { ...base }
  for (const [key, value] of Object.entries(override || {})) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = deepMerge(base[key] || {}, value)
    } else {
      out[key] = value
    }
  }
  return out
}

function loadPolicy({ allowEnvOverride = process.env.AI_EMPLOYEE_ALLOW_POLICY_ENV === '1' } = {}) {
  const managed = process.env.AI_EMPLOYEE_POLICY_FILE || path.join(PATHS.configDir, 'enterprise-policy.json')
  let policy = DEFAULT_POLICY
  try {
    if (fs.existsSync(managed)) {
      policy = deepMerge(DEFAULT_POLICY, JSON.parse(fs.readFileSync(managed, 'utf8')))
    }
  } catch {
    policy = DEFAULT_POLICY
  }

  if (allowEnvOverride && process.env.AI_EMPLOYEE_OFFLINE != null) {
    policy = deepMerge(policy, {
      network: {
        offlineByDefault: process.env.AI_EMPLOYEE_OFFLINE !== '0',
      },
    })
  }

  return {
    ...policy,
    source: fs.existsSync(managed) ? managed : 'defaults',
  }
}

module.exports = { DEFAULT_POLICY, loadPolicy }
