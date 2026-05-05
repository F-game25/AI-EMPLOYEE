const express = require('express')
const fs = require('fs').promises
const path = require('path')
const crypto = require('crypto')

const router = express.Router()

// Encryption key (should be from env in production)
const ENCRYPTION_KEY = process.env.SETTINGS_ENCRYPTION_KEY || 'dev-key-please-set-in-env'

// Settings file path (per tenant)
function getSettingsPath(tenantId) {
  const homeDir = process.env.HOME || process.env.USERPROFILE
  return path.join(homeDir, '.ai-employee', 'tenants', tenantId, 'settings.json')
}

// Simple encryption for API keys
function encryptKey(key) {
  if (!key) return ''
  const cipher = crypto.createCipher('aes-256-cbc', ENCRYPTION_KEY)
  let encrypted = cipher.update(key, 'utf8', 'hex')
  encrypted += cipher.final('hex')
  return encrypted
}

function decryptKey(encrypted) {
  if (!encrypted) return ''
  try {
    const decipher = crypto.createDecipher('aes-256-cbc', ENCRYPTION_KEY)
    let decrypted = decipher.update(encrypted, 'hex', 'utf8')
    decrypted += decipher.final('utf8')
    return decrypted
  } catch {
    return ''
  }
}

// GET /api/settings
router.get('/', async (req, res) => {
  try {
    // Use tenant from context, or fall back to default tenant for development
    const tenantId = req.tenant?.id || 'default'

    const settingsPath = getSettingsPath(tenantId)
    let settings = {
      apiKeys: { anthropic: '', openrouter: '', ollama_endpoint: 'http://localhost:11434' },
      llmSettings: { provider: 'anthropic', model: 'claude-3-5-sonnet', temperature: 0.7, maxTokens: 2048 },
    }

    try {
      const data = await fs.readFile(settingsPath, 'utf8')
      const stored = JSON.parse(data)

      // Decrypt API keys before returning
      if (stored.apiKeys) {
        settings.apiKeys = {
          anthropic: decryptKey(stored.apiKeys.anthropic),
          openrouter: decryptKey(stored.apiKeys.openrouter),
          ollama_endpoint: stored.apiKeys.ollama_endpoint || 'http://localhost:11434',
        }
      }
      if (stored.llmSettings) {
        settings.llmSettings = stored.llmSettings
      }
    } catch (e) {
      // File doesn't exist yet, return defaults
      console.log(`Settings file not found for tenant ${tenantId}, returning defaults`)
    }

    res.json(settings)
  } catch (e) {
    console.error('GET /api/settings error:', e)
    res.status(500).json({ error: 'Failed to load settings' })
  }
})

// POST /api/settings (save all settings)
router.post('/', async (req, res) => {
  try {
    // Use tenant from context, or fall back to default tenant for development
    const tenantId = req.tenant?.id || 'default'

    const { apiKeys, llmSettings } = req.body
    if (!apiKeys || !llmSettings) {
      return res.status(400).json({ error: 'Missing apiKeys or llmSettings' })
    }

    const settingsPath = getSettingsPath(tenantId)

    // Encrypt API keys before saving
    const toSave = {
      apiKeys: {
        anthropic: encryptKey(apiKeys.anthropic),
        openrouter: encryptKey(apiKeys.openrouter),
        ollama_endpoint: apiKeys.ollama_endpoint || 'http://localhost:11434',
      },
      llmSettings,
      updatedAt: new Date().toISOString(),
    }

    // Ensure directory exists
    const dir = path.dirname(settingsPath)
    await fs.mkdir(dir, { recursive: true })

    // Save settings
    await fs.writeFile(settingsPath, JSON.stringify(toSave, null, 2), 'utf8')

    // Also save to environment variables (in-memory)
    process.env.ANTHROPIC_API_KEY = apiKeys.anthropic
    process.env.OPENROUTER_API_KEY = apiKeys.openrouter
    process.env.OLLAMA_ENDPOINT = apiKeys.ollama_endpoint
    process.env.LLM_PROVIDER = llmSettings.provider
    process.env.LLM_MODEL = llmSettings.model
    process.env.OLLAMA_MODEL = llmSettings.ollama_model || 'llama2'

    res.json({ success: true, message: 'Settings saved' })
  } catch (e) {
    console.error('POST /api/settings error:', e)
    res.status(500).json({ error: 'Failed to save settings' })
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

module.exports = router
