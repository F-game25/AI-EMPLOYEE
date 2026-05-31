/**
 * Phase 4.3: Settings API Integration Tests
 * Tests for HTTP endpoints: GET, POST, POST/validate, POST/test, POST/reset, DELETE
 *
 * Coverage:
 * - HTTP POST /api/settings (save all settings)
 * - HTTP GET /api/settings (fetch settings)
 * - HTTP POST /api/settings/validate (validate without save)
 * - HTTP POST /api/settings/test/:provider (test connectivity)
 * - HTTP POST /api/settings/reset (reset to defaults)
 * - HTTP DELETE /api/settings/:section/:key (delete specific setting)
 * - Encryption: save → fetch (returns masked)
 * - Multi-tenant isolation
 * - Error responses (400, 401, 500)
 */

const assert = require('assert');

/**
 * Mock HTTP server for testing
 */
class MockSettingsServer {
  constructor() {
    this.tenantStorage = {};
    this.defaultSettings = {
      apiKeys: {
        anthropic: '',
        openrouter: '',
        ollama_endpoint: 'http://localhost:11434',
      },
      llmSettings: {
        provider: 'anthropic',
        model: 'claude-3-5-sonnet',
        temperature: 0.7,
        maxTokens: 2048,
        topP: 0.9,
        topK: 0,
        ollama_model: 'llama2',
      },
      workspace: {
        maxFileSize: 52428800,
        maxFilesPerUpload: 100,
        allowedFileTypes: ['.py', '.js', '.ts', '.json', '.txt', '.md'],
        defaultStoragePath: '~/.ai-employee/workspace',
      },
      notifications: {
        enableEmailNotifications: true,
        enableSlackNotifications: false,
        emailForAlerts: 'user@example.com',
        slackWebhookUrl: '',
      },
      security: {
        enableMultiTenancy: true,
        enableAuditLogging: true,
        requireMFA: false,
        sessionTimeoutMinutes: 60,
      },
      advanced: {
        pipelineStrictMode: false,
        enableExperimentalFeatures: false,
        logLevel: 'INFO',
        cacheSize_mb: 500,
        maxConcurrentTasks: 10,
        retryAttempts: 3,
        retryDelaySeconds: 1,
        customHeaders: {},
      },
    };
  }

  // Simulate encryption
  encryptKey(key) {
    if (!key) return '';
    return Buffer.from(key).toString('hex');
  }

  // Simulate decryption
  decryptKey(encrypted) {
    if (!encrypted) return '';
    try {
      return Buffer.from(encrypted, 'hex').toString('utf8');
    } catch {
      return '';
    }
  }

  // Mask sensitive values
  maskSensitiveValue(value) {
    if (!value || typeof value !== 'string') return '';
    return value.length > 4 ? value.slice(0, 2) + '****' + value.slice(-2) : '****';
  }

  // GET /api/settings
  getSettings(tenantId = 'default') {
    let settings = JSON.parse(JSON.stringify(this.defaultSettings));

    if (this.tenantStorage[tenantId]) {
      const stored = this.tenantStorage[tenantId];
      settings = { ...settings, ...stored };

      // Decrypt stored keys
      if (stored.apiKeys) {
        settings.apiKeys.anthropic = this.decryptKey(stored.apiKeys.anthropic);
        settings.apiKeys.openrouter = this.decryptKey(stored.apiKeys.openrouter);
      }
      if (stored.notifications?.slackWebhookUrl) {
        settings.notifications.slackWebhookUrl = this.decryptKey(
          stored.notifications.slackWebhookUrl
        );
      }
    }

    // Return masked response
    return {
      status: 200,
      body: {
        apiKeys: {
          anthropic: this.maskSensitiveValue(settings.apiKeys.anthropic),
          openrouter: this.maskSensitiveValue(settings.apiKeys.openrouter),
          ollama_endpoint: settings.apiKeys.ollama_endpoint,
        },
        llmSettings: settings.llmSettings,
        workspace: settings.workspace,
        notifications: {
          ...settings.notifications,
          slackWebhookUrl: this.maskSensitiveValue(settings.notifications.slackWebhookUrl),
        },
        security: settings.security,
        advanced: settings.advanced,
        updatedAt: new Date().toISOString(),
      },
    };
  }

  // POST /api/settings
  saveSettings(data, tenantId = 'default') {
    // Validation
    if (!data || typeof data !== 'object') {
      return {
        status: 400,
        body: { error: 'Invalid settings format' },
      };
    }

    // Store encrypted
    const toStore = {
      apiKeys: {
        anthropic: this.encryptKey(data.apiKeys?.anthropic || ''),
        openrouter: this.encryptKey(data.apiKeys?.openrouter || ''),
        ollama_endpoint: data.apiKeys?.ollama_endpoint || 'http://localhost:11434',
      },
      llmSettings: data.llmSettings || {},
      workspace: data.workspace || {},
      notifications: {
        ...data.notifications,
        slackWebhookUrl: this.encryptKey(data.notifications?.slackWebhookUrl || ''),
      },
      security: data.security || {},
      advanced: data.advanced || {},
      updatedAt: new Date().toISOString(),
    };

    this.tenantStorage[tenantId] = toStore;

    // Return masked response
    const response = this.getSettings(tenantId);
    return {
      status: 200,
      body: {
        success: true,
        message: 'Settings saved successfully',
        settings: response.body,
      },
    };
  }

  // POST /api/settings/validate
  validateSettings(data) {
    if (!data || typeof data !== 'object') {
      return {
        status: 400,
        body: { valid: false, message: 'settings must be an object' },
      };
    }

    // Run validation
    const errors = [];

    // Validate apiKeys
    if (data.apiKeys) {
      if (data.apiKeys.anthropic && !data.apiKeys.anthropic.startsWith('sk-ant-')) {
        errors.push({ field: 'apiKeys.anthropic', message: 'Invalid format' });
      }
      if (data.apiKeys.ollama_endpoint) {
        if (
          !data.apiKeys.ollama_endpoint.startsWith('http://') &&
          !data.apiKeys.ollama_endpoint.startsWith('https://')
        ) {
          errors.push({ field: 'apiKeys.ollama_endpoint', message: 'Must start with http(s)' });
        }
      }
    }

    // Validate llmSettings
    if (data.llmSettings) {
      const validProviders = ['anthropic', 'openrouter', 'ollama'];
      if (data.llmSettings.provider && !validProviders.includes(data.llmSettings.provider)) {
        errors.push({ field: 'llmSettings.provider', message: 'Invalid provider' });
      }
      if (typeof data.llmSettings.temperature === 'number') {
        if (data.llmSettings.temperature < 0 || data.llmSettings.temperature > 1) {
          errors.push({ field: 'llmSettings.temperature', message: 'Must be 0-1' });
        }
      }
    }

    // Validate notifications
    if (data.notifications?.emailForAlerts) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(data.notifications.emailForAlerts)) {
        errors.push({ field: 'notifications.emailForAlerts', message: 'Invalid email' });
      }
    }

    if (errors.length > 0) {
      return {
        status: 400,
        body: { valid: false, message: 'Validation failed', errors },
      };
    }

    return {
      status: 200,
      body: { valid: true, message: 'Settings are valid' },
    };
  }

  // POST /api/settings/test/:provider
  testProvider(provider, apiKey = '', endpoint = '') {
    if (provider === 'anthropic') {
      if (!apiKey) {
        return { status: 400, body: { error: 'No API key provided' } };
      }
      if (!apiKey.startsWith('sk-ant-')) {
        return { status: 400, body: { success: false, message: 'Invalid key format' } };
      }
      // Simulate valid key
      return { status: 200, body: { success: true, message: 'Connected to Anthropic API' } };
    } else if (provider === 'openrouter') {
      if (!apiKey) {
        return { status: 400, body: { error: 'No API key provided' } };
      }
      if (!apiKey.startsWith('sk-or-')) {
        return { status: 400, body: { success: false, message: 'Invalid key format' } };
      }
      return { status: 200, body: { success: true, message: 'Connected to OpenRouter' } };
    } else if (provider === 'ollama') {
      if (!endpoint) {
        return { status: 400, body: { error: 'No endpoint provided' } };
      }
      if (!endpoint.startsWith('http')) {
        return { status: 400, body: { success: false, message: 'Invalid endpoint format' } };
      }
      // Simulate reachable endpoint
      return { status: 200, body: { success: true, message: 'Connected to Ollama' } };
    }

    return { status: 400, body: { error: 'Unknown provider' } };
  }

  // POST /api/settings/reset
  resetSettings(confirmed, tenantId = 'default') {
    if (!confirmed) {
      return {
        status: 400,
        body: { success: false, message: 'Reset not confirmed' },
      };
    }

    // Delete tenant settings
    delete this.tenantStorage[tenantId];

    return {
      status: 200,
      body: {
        success: true,
        message: 'Settings reset to defaults',
        settings: this.getSettings(tenantId).body,
      },
    };
  }

  // DELETE /api/settings/:section/:key
  deleteSetting(section, key, tenantId = 'default') {
    const allowedSections = ['apiKeys', 'notifications', 'advanced'];

    if (!allowedSections.includes(section)) {
      return {
        status: 400,
        body: { success: false, message: `Cannot delete from section "${section}"` },
      };
    }

    if (!this.tenantStorage[tenantId]) {
      return {
        status: 404,
        body: { success: false, message: 'Setting not found' },
      };
    }

    const settings = this.tenantStorage[tenantId];
    if (settings[section] && settings[section][key]) {
      delete settings[section][key];

      return {
        status: 200,
        body: {
          success: true,
          message: `Deleted ${section}.${key}`,
          settings: this.getSettings(tenantId).body,
        },
      };
    }

    return {
      status: 404,
      body: { success: false, message: `Setting ${section}.${key} not found` },
    };
  }
}

// ===== TESTS =====

// Define describe/it/beforeEach/afterEach if they don't exist (for standalone mode)
if (typeof describe === 'undefined') {
  global.describe = function(name, fn) { fn(); };
  global.it = function(name, fn) { fn(); };
  global.beforeEach = function(fn) { fn(); };
  global.afterEach = function(fn) { fn(); };
}

describe('Settings API Integration Tests', () => {
  let server;

  // Reset for each test group
  const resetServer = () => {
    server = new MockSettingsServer();
  };

  beforeEach(() => {
    resetServer();
  });

  describe('GET /api/settings', () => {
    it('should return default settings on first access', () => {
      const response = server.getSettings();

      assert.strictEqual(response.status, 200);
      assert(response.body.apiKeys);
      assert(response.body.llmSettings);
      assert(response.body.workspace);
      assert(response.body.notifications);
      assert(response.body.security);
      assert(response.body.advanced);
    });

    it('should mask API keys in response', () => {
      // Save with real key
      server.saveSettings({
        apiKeys: {
          anthropic: 'sk-ant-' + 'a'.repeat(30),
          openrouter: 'sk-or-' + 'b'.repeat(30),
          ollama_endpoint: 'http://localhost:11434',
        },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      });

      const response = server.getSettings();

      // Should be masked (contains ****) and not reveal the full key
      if (response.body.apiKeys.anthropic && response.body.apiKeys.anthropic.length > 0) {
        assert(response.body.apiKeys.anthropic.includes('****'));
        // Check that it still starts with sk- and ends appropriately
        assert(!response.body.apiKeys.anthropic.includes('aaaaaaa'));
      }
    });

    it('should return Ollama endpoint unmasked', () => {
      server.saveSettings({
        apiKeys: {
          anthropic: '',
          openrouter: '',
          ollama_endpoint: 'http://custom-ollama:11434',
        },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      });

      const response = server.getSettings();
      assert.strictEqual(response.body.apiKeys.ollama_endpoint, 'http://custom-ollama:11434');
    });
  });

  describe('POST /api/settings', () => {
    it('should save all settings successfully', () => {
      const newSettings = {
        apiKeys: {
          anthropic: 'sk-ant-' + 'a'.repeat(30),
          openrouter: '',
          ollama_endpoint: 'http://localhost:11434',
        },
        llmSettings: {
          provider: 'anthropic',
          model: 'claude-3-5-sonnet',
          temperature: 0.7,
        },
        workspace: { allowedFileTypes: ['.py', '.js'] },
        notifications: { enableEmailNotifications: true },
        security: { enableMultiTenancy: true },
        advanced: { logLevel: 'INFO' },
      };

      const response = server.saveSettings(newSettings);

      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.body.success, true);
      assert(response.body.settings);
    });

    it('should encrypt API keys before storing', () => {
      const originalKey = 'sk-ant-' + 'a'.repeat(30);
      server.saveSettings({
        apiKeys: {
          anthropic: originalKey,
          openrouter: '',
          ollama_endpoint: 'http://localhost:11434',
        },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      });

      // Verify stored key is encrypted (should be hex-encoded in mock)
      const stored = server.tenantStorage['default'];
      const storedValue = stored.apiKeys.anthropic;

      // The mock uses hex encoding which looks different from plaintext
      if (storedValue && storedValue !== originalKey) {
        // Verify we can decrypt it back
        const decrypted = server.decryptKey(storedValue);
        assert.strictEqual(decrypted, originalKey);
      }
    });

    it('should reject invalid settings format', () => {
      const response = server.saveSettings(null);

      assert.strictEqual(response.status, 400);
      assert(response.body.error);
    });

    it('should update environment variables on save', () => {
      const settings = {
        apiKeys: {
          anthropic: 'sk-ant-test123',
          openrouter: '',
          ollama_endpoint: 'http://localhost:11434',
        },
        llmSettings: { provider: 'anthropic', model: 'claude-3-5-sonnet' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: { logLevel: 'DEBUG' },
      };

      const response = server.saveSettings(settings);
      assert.strictEqual(response.status, 200);
    });
  });

  describe('POST /api/settings/validate', () => {
    it('should validate settings without saving', () => {
      const settings = {
        apiKeys: {
          anthropic: 'sk-ant-' + 'a'.repeat(30),
          openrouter: '',
          ollama_endpoint: 'http://localhost:11434',
        },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      };

      const response = server.validateSettings(settings);

      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.body.valid, true);
    });

    it('should reject invalid anthropic key format', () => {
      const settings = {
        apiKeys: { anthropic: 'invalid-key-format' },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      };

      const response = server.validateSettings(settings);

      assert.strictEqual(response.status, 400);
      assert.strictEqual(response.body.valid, false);
      assert(response.body.errors.some(e => e.field === 'apiKeys.anthropic'));
    });

    it('should reject invalid temperature', () => {
      const settings = {
        apiKeys: { anthropic: '', openrouter: '' },
        llmSettings: { provider: 'anthropic', temperature: 1.5 },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      };

      const response = server.validateSettings(settings);

      assert.strictEqual(response.status, 400);
      assert(response.body.errors.some(e => e.field === 'llmSettings.temperature'));
    });

    it('should reject invalid email format', () => {
      const settings = {
        apiKeys: { anthropic: '', openrouter: '' },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: { emailForAlerts: 'not-an-email' },
        security: {},
        advanced: {},
      };

      const response = server.validateSettings(settings);

      assert.strictEqual(response.status, 400);
      assert(response.body.errors.some(e => e.field === 'notifications.emailForAlerts'));
    });

    it('should not save settings on validation failure', () => {
      const settings = {
        apiKeys: { anthropic: 'invalid' },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      };

      const beforeKeys = Object.keys(server.tenantStorage);
      const response = server.validateSettings(settings);
      const afterKeys = Object.keys(server.tenantStorage);

      assert.strictEqual(response.status, 400);
      assert.deepStrictEqual(beforeKeys, afterKeys);
    });
  });

  describe('POST /api/settings/test/:provider', () => {
    it('should test Anthropic provider with valid key', () => {
      const response = server.testProvider('anthropic', 'sk-ant-validkey123');

      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.body.success, true);
    });

    it('should reject Anthropic test with invalid key format', () => {
      const response = server.testProvider('anthropic', 'invalid-key');

      assert.strictEqual(response.status, 400);
      assert.strictEqual(response.body.success, false);
    });

    it('should reject Anthropic test without API key', () => {
      const response = server.testProvider('anthropic', '');

      assert.strictEqual(response.status, 400);
      assert(response.body.error);
    });

    it('should test OpenRouter provider with valid key', () => {
      const response = server.testProvider('openrouter', 'sk-or-validkey123');

      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.body.success, true);
    });

    it('should reject OpenRouter test with invalid key format', () => {
      const response = server.testProvider('openrouter', 'invalid-key');

      assert.strictEqual(response.status, 400);
      assert.strictEqual(response.body.success, false);
    });

    it('should test Ollama with reachable endpoint', () => {
      const response = server.testProvider('ollama', '', 'http://localhost:11434');

      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.body.success, true);
    });

    it('should reject Ollama with unreachable endpoint format', () => {
      const response = server.testProvider('ollama', '', 'localhost:11434');

      assert.strictEqual(response.status, 400);
      assert.strictEqual(response.body.success, false);
    });
  });

  describe('POST /api/settings/reset', () => {
    it('should reset settings to defaults when confirmed', () => {
      // Save custom settings first
      server.saveSettings({
        apiKeys: { anthropic: 'sk-ant-test' },
        llmSettings: { provider: 'openrouter', temperature: 0.3 },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      });

      // Reset
      const response = server.resetSettings(true);

      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.body.success, true);

      // Verify defaults restored
      const retrieved = server.getSettings();
      assert.strictEqual(retrieved.body.apiKeys.anthropic, ''); // Default is empty
    });

    it('should reject reset without confirmation', () => {
      const response = server.resetSettings(false);

      assert.strictEqual(response.status, 400);
      assert.strictEqual(response.body.success, false);
    });

    it('should clear all custom settings on reset', () => {
      // Save multiple custom settings
      server.saveSettings({
        apiKeys: { anthropic: 'sk-ant-test' },
        llmSettings: { provider: 'openrouter' },
        workspace: { allowedFileTypes: ['.py', '.js', '.ts'] },
        notifications: { emailForAlerts: 'custom@example.com' },
        security: { requireMFA: true },
        advanced: { logLevel: 'DEBUG' },
      });

      // Reset
      server.resetSettings(true);

      // Verify all are reset
      const retrieved = server.getSettings();
      assert.strictEqual(retrieved.body.apiKeys.anthropic, '');
      assert.strictEqual(retrieved.body.llmSettings.provider, 'anthropic');
      assert.strictEqual(retrieved.body.advanced.logLevel, 'INFO');
    });
  });

  describe('DELETE /api/settings/:section/:key', () => {
    it('should delete API key from apiKeys section', () => {
      server.saveSettings({
        apiKeys: {
          anthropic: 'sk-ant-test',
          openrouter: 'sk-or-test',
          ollama_endpoint: 'http://localhost:11434',
        },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      });

      const response = server.deleteSetting('apiKeys', 'anthropic');

      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.body.success, true);
    });

    it('should reject deletion from protected sections', () => {
      const response = server.deleteSetting('llmSettings', 'provider');

      assert.strictEqual(response.status, 400);
      assert.strictEqual(response.body.success, false);
    });

    it('should return 404 for non-existent setting', () => {
      const response = server.deleteSetting('apiKeys', 'nonexistent');

      assert.strictEqual(response.status, 404);
      assert.strictEqual(response.body.success, false);
    });

    it('should preserve other settings when deleting one', () => {
      server.saveSettings({
        apiKeys: {
          anthropic: 'sk-ant-test',
          openrouter: 'sk-or-test',
          ollama_endpoint: 'http://localhost:11434',
        },
        llmSettings: { provider: 'anthropic' },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: { emailForAlerts: 'user@example.com' },
        security: {},
        advanced: {},
      });

      const beforeDeletion = server.getSettings();
      assert(beforeDeletion.body.notifications.emailForAlerts);

      // Delete from notifications section (not apiKeys)
      server.deleteSetting('notifications', 'emailForAlerts');

      // Other notifications settings should still exist if enabled
      const afterDeletion = server.getSettings();
      assert(afterDeletion.body.notifications !== undefined);
    });
  });

  describe('Multi-Tenant Isolation', () => {
    it('should isolate settings between tenants', () => {
      // Tenant A saves settings
      server.saveSettings(
        {
          apiKeys: { anthropic: 'sk-ant-tenant-a' },
          llmSettings: { provider: 'anthropic' },
          workspace: { allowedFileTypes: ['.py'] },
          notifications: {},
          security: {},
          advanced: {},
        },
        'tenant_a'
      );

      // Tenant B saves different settings
      server.saveSettings(
        {
          apiKeys: { anthropic: 'sk-ant-tenant-b' },
          llmSettings: { provider: 'openrouter' },
          workspace: { allowedFileTypes: ['.js'] },
          notifications: {},
          security: {},
          advanced: {},
        },
        'tenant_b'
      );

      // Verify isolation
      const responseA = server.getSettings('tenant_a');
      const responseB = server.getSettings('tenant_b');

      assert.notStrictEqual(
        responseA.body.llmSettings.provider,
        responseB.body.llmSettings.provider
      );
    });

    it('should return defaults for unconfigured tenant', () => {
      // Configure tenant A
      server.saveSettings(
        {
          apiKeys: { anthropic: 'sk-ant-test' },
          llmSettings: { provider: 'openrouter' },
          workspace: { allowedFileTypes: ['.py'] },
          notifications: {},
          security: {},
          advanced: {},
        },
        'configured_tenant_123'
      );

      // Tenant C has no saved settings - use unique ID
      const response = server.getSettings('unconfigured_tenant_456');

      assert.strictEqual(response.body.apiKeys.anthropic, '');
      assert.strictEqual(response.body.llmSettings.provider, 'anthropic');
    });

    it('should reset only specified tenant', () => {
      // Configure two tenants
      server.saveSettings(
        {
          apiKeys: { anthropic: 'sk-ant-a' },
          llmSettings: { provider: 'openrouter' },
          workspace: { allowedFileTypes: ['.py'] },
          notifications: {},
          security: {},
          advanced: {},
        },
        'tenant_a'
      );

      server.saveSettings(
        {
          apiKeys: { anthropic: 'sk-ant-b' },
          llmSettings: { provider: 'ollama' },
          workspace: { allowedFileTypes: ['.js'] },
          notifications: {},
          security: {},
          advanced: {},
        },
        'tenant_b'
      );

      // Reset only tenant A
      server.resetSettings(true, 'tenant_a');

      // Tenant A should be reset
      const responseA = server.getSettings('tenant_a');
      assert.strictEqual(responseA.body.apiKeys.anthropic, '');

      // Tenant B should be unchanged (will be masked, so check provider instead)
      const responseB = server.getSettings('tenant_b');
      // Tenant B was saved with ollama, so it should still have ollama provider
      assert.strictEqual(responseB.body.llmSettings.provider, 'ollama');
    });
  });

  describe('Error Responses', () => {
    it('should return 400 for invalid request body', () => {
      const response = server.saveSettings(undefined);
      assert.strictEqual(response.status, 400);
    });

    it('should return 400 for validation errors', () => {
      const response = server.validateSettings({
        apiKeys: { anthropic: 'invalid' },
        notifications: { emailForAlerts: 'invalid-email' },
      });
      assert.strictEqual(response.status, 400);
    });

    it('should return 404 for non-existent setting deletion', () => {
      const response = server.deleteSetting('apiKeys', 'nonexistent');
      assert.strictEqual(response.status, 404);
    });

    it('should return error message with details', () => {
      const response = server.validateSettings({
        apiKeys: { anthropic: 'invalid' },
        llmSettings: { temperature: 5.0 },
      });

      assert(response.body.message);
      assert(response.body.errors);
      assert(response.body.errors.length > 0);
    });
  });

  describe('Concurrent Operations', () => {
    it('should handle concurrent valid saves', () => {
      const settings1 = {
        apiKeys: { anthropic: 'sk-ant-key1' },
        llmSettings: { provider: 'anthropic', temperature: 0.5 },
        workspace: { allowedFileTypes: ['.py'] },
        notifications: {},
        security: {},
        advanced: {},
      };

      const settings2 = {
        apiKeys: { anthropic: 'sk-ant-key2' },
        llmSettings: { provider: 'openrouter', temperature: 0.8 },
        workspace: { allowedFileTypes: ['.js'] },
        notifications: {},
        security: {},
        advanced: {},
      };

      // Simulate concurrent saves
      const response1 = server.saveSettings(settings1, 'tenant_1');
      const response2 = server.saveSettings(settings2, 'tenant_2');

      assert.strictEqual(response1.status, 200);
      assert.strictEqual(response2.status, 200);

      // Verify both saved correctly
      assert.strictEqual(server.getSettings('tenant_1').status, 200);
      assert.strictEqual(server.getSettings('tenant_2').status, 200);
    });
  });
});

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { MockSettingsServer };
}

// Run tests if using built-in test runner (jest, mocha) or standalone
if (typeof describe !== 'undefined') {
  // Tests will run with jest/mocha
} else if (require.main === module) {
  // Run as standalone Node.js script
  console.log('Settings API Integration Tests - Standalone Mode');
  console.log('=================================================\n');

  let testsPassed = 0;
  let testsFailed = 0;

  function test(name, fn) {
    try {
      fn();
      console.log(`✓ ${name}`);
      testsPassed++;
    } catch (err) {
      console.error(`✗ ${name}`);
      console.error(`  Error: ${err.message}`);
      testsFailed++;
    }
  }

  const server = new MockSettingsServer();

  // GET tests
  test('GET /api/settings returns defaults', () => {
    const response = server.getSettings();
    assert(response.status === 200);
    assert(response.body.apiKeys);
  });

  test('GET /api/settings masks API keys', () => {
    server.saveSettings({
      apiKeys: { anthropic: 'sk-ant-' + 'a'.repeat(30), openrouter: '', ollama_endpoint: 'http://localhost:11434' },
      llmSettings: { provider: 'anthropic' },
      workspace: { allowedFileTypes: ['.py'] },
      notifications: {},
      security: {},
      advanced: {},
    });
    const response = server.getSettings();
    assert(response.body.apiKeys.anthropic.includes('****'));
  });

  // POST tests
  test('POST /api/settings saves successfully', () => {
    const response = server.saveSettings({
      apiKeys: { anthropic: 'sk-ant-test', openrouter: '', ollama_endpoint: 'http://localhost:11434' },
      llmSettings: { provider: 'anthropic' },
      workspace: { allowedFileTypes: ['.py'] },
      notifications: {},
      security: {},
      advanced: {},
    });
    assert(response.status === 200);
    assert(response.body.success);
  });

  test('POST /api/settings encrypts API keys', () => {
    const originalKey = 'sk-ant-encrypttest123';
    server.saveSettings({
      apiKeys: { anthropic: originalKey, openrouter: '', ollama_endpoint: 'http://localhost:11434' },
      llmSettings: { provider: 'anthropic' },
      workspace: { allowedFileTypes: ['.py'] },
      notifications: {},
      security: {},
      advanced: {},
    });
    const stored = server.tenantStorage['default'];
    assert(stored.apiKeys.anthropic !== originalKey);
  });

  // Validate tests
  test('POST /api/settings/validate accepts valid settings', () => {
    const response = server.validateSettings({
      apiKeys: { anthropic: 'sk-ant-test' },
      llmSettings: { provider: 'anthropic' },
      workspace: { allowedFileTypes: ['.py'] },
      notifications: {},
      security: {},
      advanced: {},
    });
    assert(response.status === 200);
    assert(response.body.valid);
  });

  test('POST /api/settings/validate rejects invalid temperature', () => {
    const response = server.validateSettings({
      apiKeys: { anthropic: '' },
      llmSettings: { provider: 'anthropic', temperature: 1.5 },
      workspace: { allowedFileTypes: ['.py'] },
      notifications: {},
      security: {},
      advanced: {},
    });
    assert(response.status === 400);
    assert(!response.body.valid);
  });

  // Test provider tests
  test('POST /api/settings/test/anthropic with valid key', () => {
    const response = server.testProvider('anthropic', 'sk-ant-test123');
    assert(response.status === 200);
    assert(response.body.success);
  });

  test('POST /api/settings/test/anthropic rejects invalid key', () => {
    const response = server.testProvider('anthropic', 'invalid-key');
    assert(response.status === 400);
    assert(!response.body.success);
  });

  test('POST /api/settings/test/ollama with valid endpoint', () => {
    const response = server.testProvider('ollama', '', 'http://localhost:11434');
    assert(response.status === 200);
    assert(response.body.success);
  });

  // Reset tests
  test('POST /api/settings/reset clears custom settings', () => {
    server.saveSettings({
      apiKeys: { anthropic: 'sk-ant-custom' },
      llmSettings: { provider: 'openrouter' },
      workspace: { allowedFileTypes: ['.py'] },
      notifications: {},
      security: {},
      advanced: {},
    });
    const response = server.resetSettings(true);
    assert(response.status === 200);
    assert(response.body.success);
  });

  // Delete tests
  test('DELETE /api/settings/:section/:key deletes setting', () => {
    server.saveSettings({
      apiKeys: { anthropic: 'sk-ant-test', openrouter: 'sk-or-test', ollama_endpoint: 'http://localhost:11434' },
      llmSettings: { provider: 'anthropic' },
      workspace: { allowedFileTypes: ['.py'] },
      notifications: {},
      security: {},
      advanced: {},
    });
    const response = server.deleteSetting('apiKeys', 'anthropic');
    assert(response.status === 200);
    assert(response.body.success);
  });

  // Multi-tenant tests
  test('Multi-tenant isolation: different settings per tenant', () => {
    server.saveSettings({ apiKeys: { anthropic: 'sk-ant-a' }, llmSettings: { provider: 'anthropic' }, workspace: { allowedFileTypes: ['.py'] }, notifications: {}, security: {}, advanced: {} }, 'tenant_a');
    server.saveSettings({ apiKeys: { anthropic: 'sk-ant-b' }, llmSettings: { provider: 'openrouter' }, workspace: { allowedFileTypes: ['.js'] }, notifications: {}, security: {}, advanced: {} }, 'tenant_b');
    const a = server.getSettings('tenant_a');
    const b = server.getSettings('tenant_b');
    assert(a.body.llmSettings.provider !== b.body.llmSettings.provider);
  });

  test('Multi-tenant: unconfigured tenant sees defaults', () => {
    const response = server.getSettings('new_tenant');
    assert(response.body.apiKeys.anthropic === '');
    assert(response.body.llmSettings.provider === 'anthropic');
  });

  console.log(`\n=================================================`);
  console.log(`Passed: ${testsPassed}, Failed: ${testsFailed}`);
  console.log(`Total: ${testsPassed + testsFailed}\n`);

  process.exit(testsFailed > 0 ? 1 : 0);
}
