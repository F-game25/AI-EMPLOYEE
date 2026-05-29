const path = require('path');

const VALID_PROVIDERS = ['anthropic', 'openrouter', 'ollama'];
const VALID_LOG_LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
const VALID_PASSWORD_POLICIES = ['12chars_special_number_uppercase', 'simple', 'custom'];
const VALID_MODELS = {
  anthropic: ['claude-3-5-sonnet', 'claude-3-5-haiku', 'claude-3-opus', 'claude-3-sonnet'],
  openrouter: ['gpt-4', 'gpt-3.5-turbo', 'mistral-medium', 'llama-2-70b'],
  ollama: ['llama2', 'mistral', 'neural-chat', 'dolphin-mixtral'],
};

/**
 * Validate API keys section
 */
function validateApiKeys(keys) {
  const errors = [];
  if (!keys || typeof keys !== 'object') {
    errors.push({ field: 'apiKeys', message: 'apiKeys must be an object' });
    return { valid: false, errors };
  }

  // Check ollama_endpoint format if provided
  if (keys.ollama_endpoint && typeof keys.ollama_endpoint === 'string') {
    if (!keys.ollama_endpoint.startsWith('http://') && !keys.ollama_endpoint.startsWith('https://')) {
      errors.push({
        field: 'apiKeys.ollama_endpoint',
        message: 'Ollama endpoint must start with http:// or https://',
      });
    }
  }

  // Anthropic key format: sk-ant-*
  if (keys.anthropic && typeof keys.anthropic === 'string') {
    if (keys.anthropic && !keys.anthropic.match(/^sk-ant-[a-zA-Z0-9]{15,}$/)) {
      errors.push({
        field: 'apiKeys.anthropic',
        message: 'Invalid Anthropic API key format (expected sk-ant-...)',
      });
    }
  }

  // OpenRouter key format: sk-or-*
  if (keys.openrouter && typeof keys.openrouter === 'string') {
    if (keys.openrouter && !keys.openrouter.match(/^(sk-or-|Bearer\s)?[a-zA-Z0-9]{20,}$/)) {
      errors.push({
        field: 'apiKeys.openrouter',
        message: 'Invalid OpenRouter API key format',
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate LLM settings section
 */
function validateLlmSettings(settings) {
  const errors = [];
  if (!settings || typeof settings !== 'object') {
    errors.push({ field: 'llmSettings', message: 'llmSettings must be an object' });
    return { valid: false, errors };
  }

  // Validate provider
  if (!settings.provider || !VALID_PROVIDERS.includes(settings.provider)) {
    errors.push({
      field: 'llmSettings.provider',
      message: `Provider must be one of: ${VALID_PROVIDERS.join(', ')}`,
    });
  }

  // Validate model for the selected provider
  if (settings.model && settings.provider) {
    const validModels = VALID_MODELS[settings.provider] || [];
    if (validModels.length > 0 && !validModels.includes(settings.model)) {
      errors.push({
        field: 'llmSettings.model',
        message: `Invalid model for ${settings.provider}. Valid models: ${validModels.join(', ')}`,
      });
    }
  }

  // Validate temperature (0-1)
  if (typeof settings.temperature === 'number') {
    if (settings.temperature < 0 || settings.temperature > 1) {
      errors.push({
        field: 'llmSettings.temperature',
        message: 'Temperature must be between 0 and 1',
      });
    }
  }

  // Validate maxTokens (100-4096)
  if (typeof settings.maxTokens === 'number') {
    if (settings.maxTokens < 100 || settings.maxTokens > 4096) {
      errors.push({
        field: 'llmSettings.maxTokens',
        message: 'maxTokens must be between 100 and 4096',
      });
    }
  }

  // Validate topP (0-1)
  if (typeof settings.topP === 'number') {
    if (settings.topP < 0 || settings.topP > 1) {
      errors.push({
        field: 'llmSettings.topP',
        message: 'topP must be between 0 and 1',
      });
    }
  }

  // Validate topK (0-100)
  if (typeof settings.topK === 'number') {
    if (settings.topK < 0 || settings.topK > 100) {
      errors.push({
        field: 'llmSettings.topK',
        message: 'topK must be between 0 and 100',
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate workspace settings section
 */
function validateWorkspaceSettings(settings) {
  const errors = [];
  if (!settings || typeof settings !== 'object') {
    errors.push({ field: 'workspace', message: 'workspace must be an object' });
    return { valid: false, errors };
  }

  // Validate maxFileSize (> 0)
  if (typeof settings.maxFileSize === 'number') {
    if (settings.maxFileSize <= 0) {
      errors.push({
        field: 'workspace.maxFileSize',
        message: 'maxFileSize must be greater than 0',
      });
    }
  }

  // Validate maxFilesPerUpload (>= 1)
  if (typeof settings.maxFilesPerUpload === 'number') {
    if (settings.maxFilesPerUpload < 1) {
      errors.push({
        field: 'workspace.maxFilesPerUpload',
        message: 'maxFilesPerUpload must be at least 1',
      });
    }
  }

  // Validate allowedFileTypes is array and non-empty
  if (Array.isArray(settings.allowedFileTypes)) {
    if (settings.allowedFileTypes.length === 0) {
      errors.push({
        field: 'workspace.allowedFileTypes',
        message: 'allowedFileTypes array cannot be empty',
      });
    }
    // Validate each file type starts with dot
    settings.allowedFileTypes.forEach((type, idx) => {
      if (typeof type !== 'string' || !type.startsWith('.')) {
        errors.push({
          field: `workspace.allowedFileTypes[${idx}]`,
          message: 'File types must be strings starting with a dot (e.g., ".py")',
        });
      }
    });
  }

  // Validate defaultStoragePath is valid
  if (typeof settings.defaultStoragePath === 'string') {
    if (!settings.defaultStoragePath) {
      errors.push({
        field: 'workspace.defaultStoragePath',
        message: 'defaultStoragePath cannot be empty',
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate notification settings section
 */
function validateNotificationSettings(settings) {
  const errors = [];
  if (!settings || typeof settings !== 'object') {
    errors.push({ field: 'notifications', message: 'notifications must be an object' });
    return { valid: false, errors };
  }

  // Validate enableEmailNotifications is boolean
  if (typeof settings.enableEmailNotifications !== 'undefined' && typeof settings.enableEmailNotifications !== 'boolean') {
    errors.push({
      field: 'notifications.enableEmailNotifications',
      message: 'enableEmailNotifications must be a boolean',
    });
  }

  // Validate enableSlackNotifications is boolean
  if (typeof settings.enableSlackNotifications !== 'undefined' && typeof settings.enableSlackNotifications !== 'boolean') {
    errors.push({
      field: 'notifications.enableSlackNotifications',
      message: 'enableSlackNotifications must be a boolean',
    });
  }

  // Validate email format
  if (settings.emailForAlerts && typeof settings.emailForAlerts === 'string') {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(settings.emailForAlerts)) {
      errors.push({
        field: 'notifications.emailForAlerts',
        message: 'Invalid email format',
      });
    }
  }

  // Validate Slack webhook URL
  if (settings.slackWebhookUrl && typeof settings.slackWebhookUrl === 'string') {
    if (!settings.slackWebhookUrl.startsWith('https://hooks.slack.com')) {
      errors.push({
        field: 'notifications.slackWebhookUrl',
        message: 'Invalid Slack webhook URL (must start with https://hooks.slack.com)',
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate security settings section
 */
function validateSecuritySettings(settings) {
  const errors = [];
  if (!settings || typeof settings !== 'object') {
    errors.push({ field: 'security', message: 'security must be an object' });
    return { valid: false, errors };
  }

  // Validate enableMultiTenancy is boolean
  if (typeof settings.enableMultiTenancy !== 'undefined' && typeof settings.enableMultiTenancy !== 'boolean') {
    errors.push({
      field: 'security.enableMultiTenancy',
      message: 'enableMultiTenancy must be a boolean',
    });
  }

  // Validate enableAuditLogging is boolean
  if (typeof settings.enableAuditLogging !== 'undefined' && typeof settings.enableAuditLogging !== 'boolean') {
    errors.push({
      field: 'security.enableAuditLogging',
      message: 'enableAuditLogging must be a boolean',
    });
  }

  // Validate requireMFA is boolean
  if (typeof settings.requireMFA !== 'undefined' && typeof settings.requireMFA !== 'boolean') {
    errors.push({
      field: 'security.requireMFA',
      message: 'requireMFA must be a boolean',
    });
  }

  // Validate sessionTimeoutMinutes (>= 1)
  if (typeof settings.sessionTimeoutMinutes === 'number') {
    if (settings.sessionTimeoutMinutes < 1) {
      errors.push({
        field: 'security.sessionTimeoutMinutes',
        message: 'sessionTimeoutMinutes must be at least 1',
      });
    }
  }

  // Validate passwordPolicy
  if (settings.passwordPolicy && !VALID_PASSWORD_POLICIES.includes(settings.passwordPolicy)) {
    errors.push({
      field: 'security.passwordPolicy',
      message: `passwordPolicy must be one of: ${VALID_PASSWORD_POLICIES.join(', ')}`,
    });
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate advanced settings section
 */
function validateAdvancedSettings(settings) {
  const errors = [];
  if (!settings || typeof settings !== 'object') {
    errors.push({ field: 'advanced', message: 'advanced must be an object' });
    return { valid: false, errors };
  }

  // Validate pipelineStrictMode is boolean
  if (typeof settings.pipelineStrictMode !== 'undefined' && typeof settings.pipelineStrictMode !== 'boolean') {
    errors.push({
      field: 'advanced.pipelineStrictMode',
      message: 'pipelineStrictMode must be a boolean',
    });
  }

  // Validate enableExperimentalFeatures is boolean
  if (typeof settings.enableExperimentalFeatures !== 'undefined' && typeof settings.enableExperimentalFeatures !== 'boolean') {
    errors.push({
      field: 'advanced.enableExperimentalFeatures',
      message: 'enableExperimentalFeatures must be a boolean',
    });
  }

  // Validate logLevel
  if (settings.logLevel && !VALID_LOG_LEVELS.includes(settings.logLevel)) {
    errors.push({
      field: 'advanced.logLevel',
      message: `logLevel must be one of: ${VALID_LOG_LEVELS.join(', ')}`,
    });
  }

  // Validate cacheSize_mb (> 0)
  if (typeof settings.cacheSize_mb === 'number') {
    if (settings.cacheSize_mb <= 0) {
      errors.push({
        field: 'advanced.cacheSize_mb',
        message: 'cacheSize_mb must be greater than 0',
      });
    }
  }

  // Validate maxConcurrentTasks (>= 1)
  if (typeof settings.maxConcurrentTasks === 'number') {
    if (settings.maxConcurrentTasks < 1) {
      errors.push({
        field: 'advanced.maxConcurrentTasks',
        message: 'maxConcurrentTasks must be at least 1',
      });
    }
  }

  // Validate retryAttempts (1-10)
  if (typeof settings.retryAttempts === 'number') {
    if (settings.retryAttempts < 1 || settings.retryAttempts > 10) {
      errors.push({
        field: 'advanced.retryAttempts',
        message: 'retryAttempts must be between 1 and 10',
      });
    }
  }

  // Validate retryDelaySeconds (>= 1)
  if (typeof settings.retryDelaySeconds === 'number') {
    if (settings.retryDelaySeconds < 1) {
      errors.push({
        field: 'advanced.retryDelaySeconds',
        message: 'retryDelaySeconds must be at least 1',
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate all settings sections together
 */
function validateAll(settings) {
  const result = {
    valid: true,
    errors: {},
  };

  if (!settings || typeof settings !== 'object') {
    result.valid = false;
    result.errors.root = ['settings must be an object'];
    return result;
  }

  // Validate each section
  const sections = {
    apiKeys: validateApiKeys(settings.apiKeys),
    llmSettings: validateLlmSettings(settings.llmSettings),
    workspace: validateWorkspaceSettings(settings.workspace),
    notifications: validateNotificationSettings(settings.notifications),
    security: validateSecuritySettings(settings.security),
    advanced: validateAdvancedSettings(settings.advanced),
  };

  // Collect errors by section
  Object.entries(sections).forEach(([section, validation]) => {
    if (!validation.valid) {
      result.valid = false;
      result.errors[section] = validation.errors;
    }
  });

  return result;
}

/**
 * Get default settings template
 */
function getDefaultSettings() {
  return {
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
      topP: 1.0,
      topK: 0,
      ollama_model: 'llama2',
    },
    workspace: {
      maxFileSize: 52428800, // 50MB
      maxFilesPerUpload: 100,
      allowedFileTypes: ['.py', '.js', '.ts', '.json', '.txt', '.md', '.csv', '.yaml', '.yml', '.sh', '.java', '.cpp', '.c'],
      defaultStoragePath: '~/.ai-employee/workspace',
    },
    notifications: {
      enableEmailNotifications: true,
      enableSlackNotifications: false,
      slackWebhookUrl: '',
      emailForAlerts: 'user@example.com',
    },
    security: {
      enableMultiTenancy: true,
      enableAuditLogging: true,
      requireMFA: false,
      sessionTimeoutMinutes: 60,
      passwordPolicy: '12chars_special_number_uppercase',
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
    updates: {
      auto_update_enabled: false,
      update_channel: 'stable',     // stable | beta
      update_interval_minutes: 60,  // how often the daemon polls (min 15)
      auto_restart_on_update: true, // restart Node/Python after applying update
      watchdog_enabled: true,       // health watchdog runs regardless of auto-update
      watchdog_interval_seconds: 30,
      watchdog_max_failures: 3,     // consecutive failures before restart attempt
    },
  };
}

module.exports = {
  validateApiKeys,
  validateLlmSettings,
  validateWorkspaceSettings,
  validateNotificationSettings,
  validateSecuritySettings,
  validateAdvancedSettings,
  validateAll,
  getDefaultSettings,
  VALID_PROVIDERS,
  VALID_LOG_LEVELS,
  VALID_PASSWORD_POLICIES,
};
