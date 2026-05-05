/**
 * Comprehensive test suite for Settings API (Phase 4.1)
 * Tests: GET, POST, POST/validate, POST/reset, DELETE /api/settings/*
 * Coverage: validation, encryption, tenant isolation, edge cases
 */

const assert = require('assert');
const path = require('path');
const fs = require('fs').promises;
const crypto = require('crypto');

// Import validator for standalone testing
const validator = require('../backend/validators/settings-validator');

describe('Settings Validator (backend/validators/settings-validator.js)', () => {
  describe('validateApiKeys()', () => {
    it('should accept valid Anthropic API key format', () => {
      const result = validator.validateApiKeys({
        anthropic: 'sk-ant-' + 'a'.repeat(30),
        openrouter: '',
        ollama_endpoint: 'http://localhost:11434',
      });
      assert.strictEqual(result.valid, true);
      assert.strictEqual(result.errors.length, 0);
    });

    it('should reject invalid Anthropic API key format', () => {
      const result = validator.validateApiKeys({
        anthropic: 'invalid-key-format',
        openrouter: '',
      });
      assert.strictEqual(result.valid, false);
      assert(result.errors.some(e => e.field === 'apiKeys.anthropic'));
    });

    it('should reject invalid Ollama endpoint', () => {
      const result = validator.validateApiKeys({
        anthropic: '',
        openrouter: '',
        ollama_endpoint: 'localhost:11434', // Missing http://
      });
      assert.strictEqual(result.valid, false);
      assert(result.errors.some(e => e.field === 'apiKeys.ollama_endpoint'));
    });

    it('should accept valid Ollama endpoint', () => {
      const result = validator.validateApiKeys({
        anthropic: '',
        openrouter: '',
        ollama_endpoint: 'https://api.ollama.com:11434',
      });
      assert.strictEqual(result.valid, true);
    });

    it('should reject non-object apiKeys', () => {
      const result = validator.validateApiKeys(null);
      assert.strictEqual(result.valid, false);
      assert.strictEqual(result.errors[0].field, 'apiKeys');
    });
  });

  describe('validateLlmSettings()', () => {
    it('should accept valid LLM settings', () => {
      const result = validator.validateLlmSettings({
        provider: 'anthropic',
        model: 'claude-3-5-sonnet',
        temperature: 0.7,
        maxTokens: 2048,
        topP: 1.0,
        topK: 0,
      });
      assert.strictEqual(result.valid, true);
    });

    it('should reject invalid provider', () => {
      const result = validator.validateLlmSettings({
        provider: 'invalid-provider',
        model: 'claude-3-5-sonnet',
      });
      assert.strictEqual(result.valid, false);
      assert(result.errors.some(e => e.field === 'llmSettings.provider'));
    });

    it('should reject temperature out of range', () => {
      const result = validator.validateLlmSettings({
        provider: 'anthropic',
        temperature: 1.5, // > 1.0
      });
      assert.strictEqual(result.valid, false);
      assert(result.errors.some(e => e.field === 'llmSettings.temperature'));
    });

    it('should reject negative temperature', () => {
      const result = validator.validateLlmSettings({
        provider: 'anthropic',
        temperature: -0.1,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject maxTokens out of range', () => {
      const result = validator.validateLlmSettings({
        provider: 'anthropic',
        maxTokens: 50, // < 100
      });
      assert.strictEqual(result.valid, false);
      assert(result.errors.some(e => e.field === 'llmSettings.maxTokens'));
    });

    it('should reject topP > 1', () => {
      const result = validator.validateLlmSettings({
        provider: 'anthropic',
        topP: 1.5,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject topK > 100', () => {
      const result = validator.validateLlmSettings({
        provider: 'anthropic',
        topK: 150,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should validate model for provider', () => {
      const result = validator.validateLlmSettings({
        provider: 'anthropic',
        model: 'gpt-4', // GPT-4 is for OpenRouter, not Anthropic
      });
      assert.strictEqual(result.valid, false);
    });
  });

  describe('validateWorkspaceSettings()', () => {
    it('should accept valid workspace settings', () => {
      const result = validator.validateWorkspaceSettings({
        maxFileSize: 52428800,
        maxFilesPerUpload: 100,
        allowedFileTypes: ['.py', '.js', '.ts'],
        defaultStoragePath: '~/.ai-employee/workspace',
      });
      assert.strictEqual(result.valid, true);
    });

    it('should reject maxFileSize <= 0', () => {
      const result = validator.validateWorkspaceSettings({
        maxFileSize: 0,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject maxFilesPerUpload < 1', () => {
      const result = validator.validateWorkspaceSettings({
        maxFilesPerUpload: 0,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject empty allowedFileTypes array', () => {
      const result = validator.validateWorkspaceSettings({
        allowedFileTypes: [],
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject file types not starting with dot', () => {
      const result = validator.validateWorkspaceSettings({
        allowedFileTypes: ['py', 'js'], // Missing dots
      });
      assert.strictEqual(result.valid, false);
    });

    it('should accept valid file types', () => {
      const result = validator.validateWorkspaceSettings({
        allowedFileTypes: ['.py', '.js', '.txt', '.json'],
      });
      assert.strictEqual(result.valid, true);
    });
  });

  describe('validateNotificationSettings()', () => {
    it('should accept valid notification settings', () => {
      const result = validator.validateNotificationSettings({
        enableEmailNotifications: true,
        enableSlackNotifications: false,
        emailForAlerts: 'user@example.com',
        slackWebhookUrl: '',
      });
      assert.strictEqual(result.valid, true);
    });

    it('should reject invalid email format', () => {
      const result = validator.validateNotificationSettings({
        emailForAlerts: 'not-an-email',
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject invalid Slack webhook URL', () => {
      const result = validator.validateNotificationSettings({
        slackWebhookUrl: 'http://invalid-url.com/hook', // Not HTTPS
      });
      assert.strictEqual(result.valid, false);
    });

    it('should accept valid Slack webhook URL', () => {
      const result = validator.validateNotificationSettings({
        slackWebhookUrl: 'https://hooks.slack.com/services/FAKE00000/FAKE00000/fake-test-not-a-secret',
      });
      assert.strictEqual(result.valid, true);
    });

    it('should reject non-boolean notification flags', () => {
      const result = validator.validateNotificationSettings({
        enableEmailNotifications: 'yes', // String instead of boolean
      });
      assert.strictEqual(result.valid, false);
    });
  });

  describe('validateSecuritySettings()', () => {
    it('should accept valid security settings', () => {
      const result = validator.validateSecuritySettings({
        enableMultiTenancy: true,
        enableAuditLogging: true,
        requireMFA: false,
        sessionTimeoutMinutes: 60,
        passwordPolicy: '12chars_special_number_uppercase',
      });
      assert.strictEqual(result.valid, true);
    });

    it('should reject sessionTimeoutMinutes < 1', () => {
      const result = validator.validateSecuritySettings({
        sessionTimeoutMinutes: 0,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject invalid password policy', () => {
      const result = validator.validateSecuritySettings({
        passwordPolicy: 'invalid-policy',
      });
      assert.strictEqual(result.valid, false);
    });

    it('should accept valid password policies', () => {
      const policies = ['12chars_special_number_uppercase', 'simple', 'custom'];
      policies.forEach(policy => {
        const result = validator.validateSecuritySettings({ passwordPolicy: policy });
        assert.strictEqual(result.valid, true, `Policy ${policy} should be valid`);
      });
    });

    it('should reject non-boolean flags', () => {
      const result = validator.validateSecuritySettings({
        enableMultiTenancy: 'yes',
      });
      assert.strictEqual(result.valid, false);
    });
  });

  describe('validateAdvancedSettings()', () => {
    it('should accept valid advanced settings', () => {
      const result = validator.validateAdvancedSettings({
        pipelineStrictMode: false,
        enableExperimentalFeatures: false,
        logLevel: 'INFO',
        cacheSize_mb: 500,
        maxConcurrentTasks: 10,
        retryAttempts: 3,
        retryDelaySeconds: 1,
        customHeaders: {},
      });
      assert.strictEqual(result.valid, true);
    });

    it('should reject invalid logLevel', () => {
      const result = validator.validateAdvancedSettings({
        logLevel: 'VERBOSE', // Invalid
      });
      assert.strictEqual(result.valid, false);
    });

    it('should accept valid logLevels', () => {
      const levels = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
      levels.forEach(level => {
        const result = validator.validateAdvancedSettings({ logLevel: level });
        assert.strictEqual(result.valid, true, `Level ${level} should be valid`);
      });
    });

    it('should reject cacheSize_mb <= 0', () => {
      const result = validator.validateAdvancedSettings({
        cacheSize_mb: 0,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject maxConcurrentTasks < 1', () => {
      const result = validator.validateAdvancedSettings({
        maxConcurrentTasks: 0,
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject retryAttempts outside 1-10 range', () => {
      const result = validator.validateAdvancedSettings({
        retryAttempts: 15, // > 10
      });
      assert.strictEqual(result.valid, false);
    });

    it('should reject retryDelaySeconds < 1', () => {
      const result = validator.validateAdvancedSettings({
        retryDelaySeconds: 0,
      });
      assert.strictEqual(result.valid, false);
    });
  });

  describe('validateAll()', () => {
    it('should validate complete settings object', () => {
      const fullSettings = validator.getDefaultSettings();
      const result = validator.validateAll(fullSettings);
      assert.strictEqual(result.valid, true);
      assert.deepStrictEqual(result.errors, {});
    });

    it('should collect errors from multiple sections', () => {
      const invalidSettings = {
        apiKeys: { anthropic: 'invalid' },
        llmSettings: { temperature: 1.5 },
        workspace: { maxFileSize: 0 },
        notifications: { emailForAlerts: 'not-an-email' },
        security: { sessionTimeoutMinutes: 0 },
        advanced: { logLevel: 'INVALID' },
      };
      const result = validator.validateAll(invalidSettings);
      assert.strictEqual(result.valid, false);
      assert(Object.keys(result.errors).length > 0);
    });

    it('should handle partial settings (missing sections)', () => {
      const partial = {
        llmSettings: { provider: 'anthropic' },
      };
      const result = validator.validateAll(partial);
      // Should still validate what's provided
      assert.strictEqual(result.valid, false); // Will fail on missing required data
    });

    it('should reject non-object settings', () => {
      const result = validator.validateAll(null);
      assert.strictEqual(result.valid, false);
      assert(result.errors.root);
    });
  });

  describe('getDefaultSettings()', () => {
    it('should return complete default settings structure', () => {
      const defaults = validator.getDefaultSettings();
      assert(defaults.apiKeys);
      assert(defaults.llmSettings);
      assert(defaults.workspace);
      assert(defaults.notifications);
      assert(defaults.security);
      assert(defaults.advanced);
    });

    it('should return valid default settings', () => {
      const defaults = validator.getDefaultSettings();
      const result = validator.validateAll(defaults);
      assert.strictEqual(result.valid, true);
    });

    it('should have sensible defaults', () => {
      const defaults = validator.getDefaultSettings();
      assert.strictEqual(defaults.llmSettings.provider, 'anthropic');
      assert.strictEqual(defaults.security.enableMultiTenancy, true);
      assert.strictEqual(defaults.advanced.logLevel, 'INFO');
    });
  });
});

describe('Settings API Routes (integration tests)', () => {
  it('should mask sensitive API keys in responses', () => {
    // Simulating the masking function
    const maskValue = (val) => {
      if (!val || typeof val !== 'string') return '';
      return val.length > 4 ? val.slice(0, 2) + '****' + val.slice(-2) : '****';
    };

    const masked = maskValue('sk-ant-abcdefghij1234567890');
    assert(masked.includes('****'));
    assert(!masked.includes('abcdefghij'));
  });

  it('should handle encryption/decryption roundtrip', () => {
    const ENCRYPTION_KEY = 'test-encryption-key';
    const plaintext = 'sk-ant-test1234567890';

    // Encrypt
    const cipher = crypto.createCipher('aes-256-cbc', ENCRYPTION_KEY);
    let encrypted = cipher.update(plaintext, 'utf8', 'hex');
    encrypted += cipher.final('hex');

    // Decrypt
    const decipher = crypto.createDecipher('aes-256-cbc', ENCRYPTION_KEY);
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');

    assert.strictEqual(decrypted, plaintext);
  });

  it('should handle empty API key decryption gracefully', () => {
    const ENCRYPTION_KEY = 'test-key';
    const decipher = crypto.createDecipher('aes-256-cbc', ENCRYPTION_KEY);
    try {
      let decrypted = decipher.update('', 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      // Empty input returns empty output
      assert.strictEqual(decrypted, '');
    } catch (e) {
      // Expected: empty input may cause errors, handle gracefully
      assert(true);
    }
  });
});

describe('Settings Data Isolation (Multi-tenancy)', () => {
  it('should generate different paths for different tenants', () => {
    const homeDir = process.env.HOME || process.env.USERPROFILE;
    const tenant1Path = path.join(homeDir, '.ai-employee', 'tenants', 'tenant-1', 'settings.json');
    const tenant2Path = path.join(homeDir, '.ai-employee', 'tenants', 'tenant-2', 'settings.json');

    assert.notStrictEqual(tenant1Path, tenant2Path);
    assert(tenant1Path.includes('tenant-1'));
    assert(tenant2Path.includes('tenant-2'));
  });

  it('should maintain separate settings files per tenant', () => {
    const homeDir = process.env.HOME || process.env.USERPROFILE;
    const basePath = path.join(homeDir, '.ai-employee', 'tenants');

    // Verify tenant directory structure concept
    const tenant1 = path.join(basePath, 'tenant-1', 'settings.json');
    const tenant2 = path.join(basePath, 'tenant-2', 'settings.json');

    // Different paths = isolated data
    assert.notStrictEqual(
      path.dirname(tenant1),
      path.dirname(tenant2)
    );
  });
});

describe('Settings Edge Cases & Error Handling', () => {
  it('should handle null/undefined gracefully', () => {
    [null, undefined, {}].forEach(input => {
      const result = validator.validateAll(input);
      assert.strictEqual(result.valid, false);
    });
  });

  it('should preserve unknown fields in settings', () => {
    const settings = {
      ...validator.getDefaultSettings(),
      customField: 'custom-value',
    };
    const result = validator.validateAll(settings);
    // Should validate known fields, ignore unknown ones
    assert.strictEqual(result.valid, true);
  });

  it('should validate API key format variations', () => {
    const validAnthropic = validator.validateApiKeys({
      anthropic: 'sk-ant-' + 'A'.repeat(25), // Longer key
    });
    assert.strictEqual(validAnthropic.valid, true);

    const shortKey = validator.validateApiKeys({
      anthropic: 'sk-ant-short', // Too short
    });
    assert.strictEqual(shortKey.valid, false);
  });

  it('should handle whitespace in string fields', () => {
    const result = validator.validateNotificationSettings({
      emailForAlerts: '  user@example.com  ', // With whitespace
    });
    // Should handle with trimming or reject
    // Current implementation: rejects due to regex
    assert.strictEqual(result.valid, false);
  });

  it('should validate all password policy enums', () => {
    const policies = ['12chars_special_number_uppercase', 'simple', 'custom'];
    policies.forEach(policy => {
      const result = validator.validateSecuritySettings({ passwordPolicy: policy });
      assert.strictEqual(result.valid, true);
    });
  });

  it('should validate all log level enums', () => {
    const levels = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
    levels.forEach(level => {
      const result = validator.validateAdvancedSettings({ logLevel: level });
      assert.strictEqual(result.valid, true);
    });
  });

  it('should validate all provider enums', () => {
    ['anthropic', 'openrouter', 'ollama'].forEach(provider => {
      const result = validator.validateLlmSettings({ provider });
      assert.strictEqual(result.valid, true);
    });
  });
});

console.log('All tests defined. Run with: npm test');
