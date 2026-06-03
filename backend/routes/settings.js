const express = require('express')
const fs = require('fs').promises
const path = require('path')
const crypto = require('crypto')
const validator = require('../validators/settings-validator')
const { createRouteRateLimit } = require('../middleware/route-rate-limit')

const router = express.Router()
router.use(createRouteRateLimit({ keyPrefix: 'settings', max: 60, windowMs: 60_000 }))

// Encryption key — must be set via env var; fallback generates a stable per-process key (dev only)
const RAW_KEY = process.env.SETTINGS_ENCRYPTION_KEY || (() => {
  if (process.env.NODE_ENV === 'production') {
    console.error('FATAL: SETTINGS_ENCRYPTION_KEY must be set in production');
    process.exit(1);
  }
  // Dev/test: derive a stable but non-secret key so the server can still start
  const { execSync } = require('child_process');
  try { return execSync('hostname').toString().trim() + '-dev-only-not-secret'; } catch { return 'dev-only-not-secret'; }
})();
const ENCRYPTION_KEY = crypto.createHash('sha256').update(RAW_KEY).digest() // always 32 bytes

// Settings file path (per tenant)
function getSettingsPath(tenantId) {
  const homeDir = process.env.HOME || process.env.USERPROFILE
  return path.join(homeDir, '.ai-employee', 'tenants', tenantId, 'settings.json')
}

// AES-256-CBC with random IV — format: iv_hex:encrypted_hex
function encryptKey(key) {
  if (!key) return ''
  const iv = crypto.randomBytes(16)
  const cipher = crypto.createCipheriv('aes-256-cbc', ENCRYPTION_KEY, iv)
  let encrypted = cipher.update(key, 'utf8', 'hex')
  encrypted += cipher.final('hex')
  return `${iv.toString('hex')}:${encrypted}`
}

function decryptKey(encrypted) {
  if (!encrypted) return ''
  try {
    const [ivHex, data] = encrypted.split(':')
    if (!ivHex || !data) return ''
    const iv = Buffer.from(ivHex, 'hex')
    const decipher = crypto.createDecipheriv('aes-256-cbc', ENCRYPTION_KEY, iv)
    let decrypted = decipher.update(data, 'hex', 'utf8')
    decrypted += decipher.final('utf8')
    return decrypted
  } catch {
    return ''
  }
}

// Mask sensitive values for API responses
function maskSensitiveValue(value) {
  if (!value || typeof value !== 'string') return ''
  return value.length > 4 ? value.slice(0, 2) + '****' + value.slice(-2) : '****'
}

// Helper: Load settings from file for a tenant
async function loadSettingsForTenant(tenantId) {
  const settingsPath = getSettingsPath(tenantId)
  let settings = validator.getDefaultSettings()

  try {
    const data = await fs.readFile(settingsPath, 'utf8')
    const stored = JSON.parse(data)

    // Merge stored settings with defaults (preserve new fields)
    settings = {
      ...settings,
      ...stored,
      apiKeys: {
        ...settings.apiKeys,
        ...(stored.apiKeys || {}),
      },
      llmSettings: {
        ...settings.llmSettings,
        ...(stored.llmSettings || {}),
      },
      workspace: {
        ...settings.workspace,
        ...(stored.workspace || {}),
      },
      notifications: {
        ...settings.notifications,
        ...(stored.notifications || {}),
      },
      security: {
        ...settings.security,
        ...(stored.security || {}),
      },
      advanced: {
        ...settings.advanced,
        ...(stored.advanced || {}),
      },
    }

    // Decrypt API keys and Slack webhook
    if (settings.apiKeys) {
      settings.apiKeys.anthropic = decryptKey(settings.apiKeys.anthropic)
      settings.apiKeys.openrouter = decryptKey(settings.apiKeys.openrouter)
    }
    if (settings.notifications?.slackWebhookUrl) {
      settings.notifications.slackWebhookUrl = decryptKey(settings.notifications.slackWebhookUrl)
    }
  } catch (e) {
    console.log(`Settings file not found for tenant ${tenantId}, returning defaults`)
  }

  return settings
}

// Helper: Format settings for API response (mask sensitive values)
function formatSettingsResponse(settings) {
  return {
    apiKeys: {
      anthropic: maskSensitiveValue(settings.apiKeys?.anthropic),
      openrouter: maskSensitiveValue(settings.apiKeys?.openrouter),
      ollama_endpoint: settings.apiKeys?.ollama_endpoint || 'http://localhost:11434',
    },
    llmSettings: settings.llmSettings || {},
    workspace: settings.workspace || {},
    notifications: {
      ...settings.notifications,
      slackWebhookUrl: maskSensitiveValue(settings.notifications?.slackWebhookUrl),
    },
    security: settings.security || {},
    advanced: settings.advanced || {},
    updatedAt: settings.updatedAt || new Date().toISOString(),
  }
}

// GET /api/settings — fetch all settings
router.get('/', async (req, res) => {
  try {
    const tenantId = req.tenant?.id || 'default'
    const settings = await loadSettingsForTenant(tenantId)
    const response = formatSettingsResponse(settings)
    res.json(response)
  } catch (e) {
    console.error('GET /api/settings error:', e)
    res.status(500).json({ error: 'Failed to load settings' })
  }
})

// POST /api/settings — save all settings with validation
router.post('/', async (req, res) => {
  try {
    const tenantId = req.tenant?.id || 'default'
    const newSettings = req.body

    // Validate all settings
    const validation = validator.validateAll(newSettings)
    if (!validation.valid) {
      return res.status(400).json({
        success: false,
        message: 'Validation failed',
        errors: validation.errors,
      })
    }

    const settingsPath = getSettingsPath(tenantId)

    // Encrypt sensitive fields before saving
    const toSave = {
      apiKeys: {
        anthropic: encryptKey(newSettings.apiKeys?.anthropic || ''),
        openrouter: encryptKey(newSettings.apiKeys?.openrouter || ''),
        ollama_endpoint: newSettings.apiKeys?.ollama_endpoint || 'http://localhost:11434',
      },
      llmSettings: newSettings.llmSettings || {},
      workspace: newSettings.workspace || {},
      notifications: {
        ...newSettings.notifications,
        slackWebhookUrl: encryptKey(newSettings.notifications?.slackWebhookUrl || ''),
      },
      security: newSettings.security || {},
      advanced: newSettings.advanced || {},
      updatedAt: new Date().toISOString(),
    }

    // Ensure directory exists
    const dir = path.dirname(settingsPath)
    await fs.mkdir(dir, { recursive: true })

    // Save settings
    await fs.writeFile(settingsPath, JSON.stringify(toSave, null, 2), 'utf8')

    // Update environment variables
    if (newSettings.apiKeys?.anthropic) {
      process.env.ANTHROPIC_API_KEY = newSettings.apiKeys.anthropic
    }
    if (newSettings.apiKeys?.openrouter) {
      process.env.OPENROUTER_API_KEY = newSettings.apiKeys.openrouter
    }
    if (newSettings.apiKeys?.ollama_endpoint) {
      process.env.OLLAMA_ENDPOINT = newSettings.apiKeys.ollama_endpoint
    }
    if (newSettings.llmSettings?.provider) {
      process.env.LLM_PROVIDER = newSettings.llmSettings.provider
    }
    if (newSettings.llmSettings?.model) {
      process.env.LLM_MODEL = newSettings.llmSettings.model
    }
    if (newSettings.llmSettings?.ollama_model) {
      process.env.OLLAMA_MODEL = newSettings.llmSettings.ollama_model
    }
    if (newSettings.advanced?.logLevel) {
      process.env.LOG_LEVEL = newSettings.advanced.logLevel
    }
    if (newSettings.security?.enableMultiTenancy !== undefined) {
      process.env.MULTI_TENANCY_ENABLED = String(newSettings.security.enableMultiTenancy)
    }

    // Return masked response
    const response = formatSettingsResponse(newSettings)
    res.json({
      success: true,
      message: 'Settings saved successfully',
      settings: response,
    })
  } catch (e) {
    console.error('POST /api/settings error:', e)
    res.status(500).json({ error: 'Failed to save settings' })
  }
})

// POST /api/settings/validate — validate settings without saving
router.post('/validate', async (req, res) => {
  try {
    const newSettings = req.body
    const validation = validator.validateAll(newSettings)

    if (!validation.valid) {
      return res.status(400).json({
        valid: false,
        message: 'Validation failed',
        errors: validation.errors,
      })
    }

    res.json({
      valid: true,
      message: 'Settings are valid',
    })
  } catch (e) {
    console.error('POST /api/settings/validate error:', e)
    res.status(500).json({ error: 'Validation failed' })
  }
})

// POST /api/settings/reset — reset to factory defaults
router.post('/reset', async (req, res) => {
  try {
    const tenantId = req.tenant?.id || 'default'
    const { confirmed } = req.body

    if (!confirmed) {
      return res.status(400).json({
        success: false,
        message: 'Reset not confirmed. Include confirmed: true in request body.',
      })
    }

    const settingsPath = getSettingsPath(tenantId)
    const defaultSettings = validator.getDefaultSettings()

    // Encrypt sensitive fields
    const toSave = {
      ...defaultSettings,
      apiKeys: {
        anthropic: encryptKey(defaultSettings.apiKeys.anthropic),
        openrouter: encryptKey(defaultSettings.apiKeys.openrouter),
        ollama_endpoint: defaultSettings.apiKeys.ollama_endpoint,
      },
      notifications: {
        ...defaultSettings.notifications,
        slackWebhookUrl: encryptKey(defaultSettings.notifications.slackWebhookUrl),
      },
      updatedAt: new Date().toISOString(),
    }

    // Ensure directory exists
    const dir = path.dirname(settingsPath)
    await fs.mkdir(dir, { recursive: true })

    // Save default settings
    await fs.writeFile(settingsPath, JSON.stringify(toSave, null, 2), 'utf8')

    const response = formatSettingsResponse(defaultSettings)
    res.json({
      success: true,
      message: 'Settings reset to factory defaults',
      settings: response,
    })
  } catch (e) {
    console.error('POST /api/settings/reset error:', e)
    res.status(500).json({ error: 'Failed to reset settings' })
  }
})

// DELETE /api/settings/:section/:key — delete specific setting
router.delete('/:section/:key', async (req, res) => {
  try {
    const tenantId = req.tenant?.id || 'default'
    const { section, key } = req.params

    // Allowed sections for deletion
    const allowedSections = ['apiKeys', 'notifications', 'advanced']
    if (!allowedSections.includes(section)) {
      return res.status(400).json({
        success: false,
        message: `Cannot delete from section "${section}". Allowed sections: ${allowedSections.join(', ')}`,
      })
    }

    // Load current settings
    const settingsPath = getSettingsPath(tenantId)
    let currentSettings = validator.getDefaultSettings()

    try {
      const data = await fs.readFile(settingsPath, 'utf8')
      const stored = JSON.parse(data)
      currentSettings = {
        ...currentSettings,
        ...stored,
      }
    } catch (e) {
      // File doesn't exist, use defaults
    }

    // Delete the specific key from section
    if (currentSettings[section] && currentSettings[section][key]) {
      delete currentSettings[section][key]

      // Encrypt sensitive fields before saving
      const toSave = {
        ...currentSettings,
        apiKeys: {
          anthropic: encryptKey(currentSettings.apiKeys?.anthropic || ''),
          openrouter: encryptKey(currentSettings.apiKeys?.openrouter || ''),
          ollama_endpoint: currentSettings.apiKeys?.ollama_endpoint || 'http://localhost:11434',
        },
        notifications: {
          ...currentSettings.notifications,
          slackWebhookUrl: encryptKey(currentSettings.notifications?.slackWebhookUrl || ''),
        },
        updatedAt: new Date().toISOString(),
      }

      // Ensure directory exists
      const dir = path.dirname(settingsPath)
      await fs.mkdir(dir, { recursive: true })

      // Save updated settings
      await fs.writeFile(settingsPath, JSON.stringify(toSave, null, 2), 'utf8')

      const response = formatSettingsResponse(currentSettings)
      return res.json({
        success: true,
        message: `Deleted ${section}.${key}`,
        settings: response,
      })
    }

    res.status(404).json({
      success: false,
      message: `Setting ${section}.${key} not found`,
    })
  } catch (e) {
    console.error('DELETE /api/settings/:section/:key error:', e)
    res.status(500).json({ error: 'Failed to delete setting' })
  }
})

// POST /api/settings/test/:provider (test API connection)
router.post('/test/:provider', async (req, res) => {
  try {
    const { provider } = req.params
    // Use tenant from context, or fall back to default tenant for development
    const tenantId = req.tenant?.id || 'default'

    // Get current settings to test with
    const settingsPath = getSettingsPath(tenantId)
    let settings = {
      apiKeys: { anthropic: process.env.ANTHROPIC_API_KEY || '', openrouter: process.env.OPENROUTER_API_KEY || '', ollama_endpoint: process.env.OLLAMA_ENDPOINT || 'http://localhost:11434' },
    }

    try {
      const data = await fs.readFile(settingsPath, 'utf8')
      const stored = JSON.parse(data)
      if (stored.apiKeys) {
        settings.apiKeys = {
          anthropic: decryptKey(stored.apiKeys.anthropic),
          openrouter: decryptKey(stored.apiKeys.openrouter),
          ollama_endpoint: stored.apiKeys.ollama_endpoint,
        }
      }
    } catch (e) {
      // Use env vars
    }

    // Test connection based on provider
    let success = false
    let message = ''

    if (provider === 'anthropic') {
      if (!settings.apiKeys.anthropic) {
        return res.status(400).json({ error: 'No Anthropic API key configured' })
      }
      try {
        // Quick test: validate API key format and connectivity
        const fetch = (await import('node-fetch')).default
        const response = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers: {
            'x-api-key': settings.apiKeys.anthropic,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
          },
          body: JSON.stringify({
            model: 'claude-3-5-sonnet',
            max_tokens: 1,
            messages: [{ role: 'user', content: 'test' }],
          }),
          timeout: 5000,
        })
        success = response.status === 200 || response.status === 400 // 400 = auth ok but invalid request
        message = success ? 'Connected to Anthropic API' : `Failed: ${response.statusText}`
      } catch (e) {
        message = `Connection failed: ${e.message}`
      }
    } else if (provider === 'ollama') {
      try {
        const fetch = (await import('node-fetch')).default
        const endpoint = settings.apiKeys.ollama_endpoint || 'http://localhost:11434'
        const response = await fetch(`${endpoint}/api/tags`, { timeout: 5000 })
        success = response.status === 200
        message = success ? 'Connected to Ollama' : `Failed: ${response.statusText}`
      } catch (e) {
        message = `Connection failed: ${e.message}`
      }
    } else if (provider === 'openrouter') {
      if (!settings.apiKeys.openrouter) {
        return res.status(400).json({ error: 'No OpenRouter API key configured' })
      }
      try {
        const fetch = (await import('node-fetch')).default
        const response = await fetch('https://openrouter.ai/api/v1/auth/key', {
          headers: { Authorization: `Bearer ${settings.apiKeys.openrouter}` },
          timeout: 5000,
        })
        success = response.status === 200
        message = success ? 'Connected to OpenRouter' : `Failed: ${response.statusText}`
      } catch (e) {
        message = `Connection failed: ${e.message}`
      }
    } else if (provider === 'nvidia_nim') {
      const { key, endpoint, model } = req.body
      const nimEndpoint = (endpoint || settings.apiKeys?.nim_endpoint || 'https://integrate.api.nvidia.com/v1').replace(/\/$/, '')
      const nimKey = key || settings.apiKeys?.nim_key || ''
      try {
        const fetch = (await import('node-fetch')).default
        const headers = { 'content-type': 'application/json' }
        if (nimKey) headers['authorization'] = `Bearer ${nimKey}`
        const response = await fetch(`${nimEndpoint}/models`, { headers, timeout: 8000 })
        success = response.status === 200 || response.status === 401 // 401 = endpoint reachable
        message = response.status === 200
          ? `Connected to NIM at ${nimEndpoint}`
          : response.status === 401
            ? `NIM endpoint reachable — check API key`
            : `Failed: ${response.statusText}`
      } catch (e) {
        message = `NIM connection failed: ${e.message}`
      }
    } else if (provider === 'remote_compute') {
      const { endpoint } = req.body
      const remoteHost = (endpoint || '').replace(/\/$/, '')
      if (!remoteHost) return res.status(400).json({ error: 'No endpoint provided' })
      try {
        const fetch = (await import('node-fetch')).default
        const response = await fetch(`${remoteHost}/api/tags`, { timeout: 8000 })
        success = response.status === 200
        message = success ? `Remote Ollama reachable at ${remoteHost}` : `Failed: ${response.statusText}`
      } catch (e) {
        message = `Remote compute connection failed: ${e.message}`
      }
    }

    if (success) {
      res.json({ success: true, message })
    } else {
      res.status(400).json({ success: false, message })
    }
  } catch (e) {
    console.error(`POST /api/settings/test/:provider error:`, e)
    res.status(500).json({ error: 'Test failed' })
  }
})

// POST /api/settings/llm/swap — hot-swap LLM backend without losing context
router.post('/llm/swap', async (req, res) => {
  try {
    const { backend, model, endpoint } = req.body
    const allowed = ['anthropic', 'openrouter', 'ollama', 'nvidia_nim', 'remote_compute']
    if (!allowed.includes(backend)) return res.status(400).json({ error: `Unknown backend: ${backend}` })

    // Persist new config to settings file
    const tenantId = req.tenant?.id || 'default'
    const settings = await loadSettingsForTenant(tenantId)
    settings.llmSettings = { ...settings.llmSettings, provider: backend, model: model || settings.llmSettings?.model }
    if (endpoint) {
      if (backend === 'nvidia_nim') settings.apiKeys = { ...settings.apiKeys, nim_endpoint: endpoint }
      else if (backend === 'remote_compute') settings.apiKeys = { ...settings.apiKeys, remote_compute_endpoint: endpoint }
      else if (backend === 'ollama') settings.apiKeys = { ...settings.apiKeys, ollama_endpoint: endpoint }
    }
    settings.updatedAt = new Date().toISOString()
    const settingsPath = getSettingsPath(tenantId)
    const dir = path.dirname(settingsPath)
    await fs.mkdir(dir, { recursive: true })
    await fs.writeFile(settingsPath, JSON.stringify(settings, null, 2), 'utf8')

    // Update live process env (Python backend picks this up on next call via env)
    process.env.LLM_BACKEND = backend
    if (model) {
      if (backend === 'ollama' || backend === 'remote_compute') process.env.OLLAMA_MODEL = model
      else if (backend === 'nvidia_nim') process.env.NIM_MODEL = model
      else if (backend === 'openrouter') process.env.OPENROUTER_MODEL = model
    }
    if (endpoint) {
      if (backend === 'nvidia_nim') process.env.NIM_ENDPOINT = endpoint
      else if (backend === 'remote_compute') process.env.OLLAMA_HOST = endpoint
      else if (backend === 'ollama') process.env.OLLAMA_HOST = endpoint
    }

    // Signal Python backend to hot-swap (best-effort — Python resets singleton on next request)
    try {
      const fetch = (await import('node-fetch')).default
      await fetch('http://127.0.0.1:18790/internal/swap-backend', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ backend, model, endpoint }),
        timeout: 3000,
      })
    } catch (_) { /* Python may not have this endpoint — fallback: env var pick-up on next request */ }

    res.json({ ok: true, backend, model: model || 'default', swapped_at: new Date().toISOString() })
  } catch (e) {
    console.error('POST /api/settings/llm/swap error:', e)
    res.status(500).json({ error: 'Swap failed' })
  }
})

module.exports = router
