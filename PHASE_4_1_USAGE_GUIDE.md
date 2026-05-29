# Phase 4.1 Settings API Usage Guide

## Quick Start

### 1. Get Current Settings
Retrieve all settings for the authenticated user/tenant.

```bash
curl http://localhost:8787/api/settings
```

**Response:**
```json
{
  "apiKeys": {
    "anthropic": "sk****90",
    "openrouter": "",
    "ollama_endpoint": "http://localhost:11434"
  },
  "llmSettings": {
    "provider": "anthropic",
    "model": "claude-3-5-sonnet",
    "temperature": 0.7,
    "maxTokens": 2048,
    "topP": 1.0,
    "topK": 0,
    "ollama_model": "llama2"
  },
  "workspace": {
    "maxFileSize": 52428800,
    "maxFilesPerUpload": 100,
    "allowedFileTypes": [".py", ".js", ".ts", ".json", ".txt", ".md"],
    "defaultStoragePath": "~/.ai-employee/workspace"
  },
  "notifications": {
    "enableEmailNotifications": true,
    "enableSlackNotifications": false,
    "slackWebhookUrl": "",
    "emailForAlerts": "user@example.com"
  },
  "security": {
    "enableMultiTenancy": true,
    "enableAuditLogging": true,
    "requireMFA": false,
    "sessionTimeoutMinutes": 60,
    "passwordPolicy": "12chars_special_number_uppercase"
  },
  "advanced": {
    "pipelineStrictMode": false,
    "enableExperimentalFeatures": false,
    "logLevel": "INFO",
    "cacheSize_mb": 500,
    "maxConcurrentTasks": 10,
    "retryAttempts": 3,
    "retryDelaySeconds": 1,
    "customHeaders": {}
  },
  "updatedAt": "2026-05-05T12:34:56.000Z"
}
```

---

## API Key Management

### Set Anthropic API Key

```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": {
      "anthropic": "sk-ant-abcdefghijklmnopqrstuvwxyz",
      "openrouter": "",
      "ollama_endpoint": "http://localhost:11434"
    },
    "llmSettings": {
      "provider": "anthropic",
      "model": "claude-3-5-sonnet",
      "temperature": 0.7,
      "maxTokens": 2048,
      "topP": 1.0,
      "topK": 0
    },
    "workspace": {
      "maxFileSize": 52428800,
      "maxFilesPerUpload": 100,
      "allowedFileTypes": [".py", ".js", ".ts", ".json"],
      "defaultStoragePath": "~/.ai-employee/workspace"
    },
    "notifications": {
      "enableEmailNotifications": true,
      "enableSlackNotifications": false,
      "slackWebhookUrl": "",
      "emailForAlerts": "user@example.com"
    },
    "security": {
      "enableMultiTenancy": true,
      "enableAuditLogging": true,
      "requireMFA": false,
      "sessionTimeoutMinutes": 60,
      "passwordPolicy": "12chars_special_number_uppercase"
    },
    "advanced": {
      "pipelineStrictMode": false,
      "enableExperimentalFeatures": false,
      "logLevel": "INFO",
      "cacheSize_mb": 500,
      "maxConcurrentTasks": 10,
      "retryAttempts": 3,
      "retryDelaySeconds": 1,
      "customHeaders": {}
    }
  }'
```

### Test API Key

```bash
curl -X POST http://localhost:8787/api/settings/test/anthropic
```

**Success Response:**
```json
{
  "success": true,
  "message": "Connected to Anthropic API"
}
```

**Failure Response:**
```json
{
  "success": false,
  "message": "No Anthropic API key configured"
}
```

---

## LLM Provider Configuration

### Switch to OpenRouter

```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": {
      "anthropic": "",
      "openrouter": "sk-or-your-openrouter-key",
      "ollama_endpoint": "http://localhost:11434"
    },
    "llmSettings": {
      "provider": "openrouter",
      "model": "gpt-4",
      "temperature": 0.7,
      "maxTokens": 2048,
      "topP": 1.0,
      "topK": 0
    },
    "workspace": { /* ... */ },
    "notifications": { /* ... */ },
    "security": { /* ... */ },
    "advanced": { /* ... */ }
  }'
```

### Switch to Ollama

```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": {
      "anthropic": "",
      "openrouter": "",
      "ollama_endpoint": "http://localhost:11434"
    },
    "llmSettings": {
      "provider": "ollama",
      "model": "llama2",
      "temperature": 0.7,
      "maxTokens": 2048,
      "topP": 1.0,
      "topK": 0,
      "ollama_model": "mistral"
    },
    "workspace": { /* ... */ },
    "notifications": { /* ... */ },
    "security": { /* ... */ },
    "advanced": { /* ... */ }
  }'
```

### Test Ollama Connection

```bash
curl -X POST http://localhost:8787/api/settings/test/ollama
```

---

## Validation Examples

### Validate Before Saving

Use the validate endpoint to check settings without saving them:

```bash
curl -X POST http://localhost:8787/api/settings/validate \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": { "anthropic": "invalid-key" },
    "llmSettings": { "provider": "anthropic", "temperature": 0.7 },
    "workspace": { "maxFileSize": 100 },
    "notifications": {},
    "security": {},
    "advanced": {}
  }'
```

**Response (Validation Errors):**
```json
{
  "valid": false,
  "message": "Validation failed",
  "errors": {
    "apiKeys": [
      {
        "field": "apiKeys.anthropic",
        "message": "Invalid Anthropic API key format (expected sk-ant-...)"
      }
    ],
    "workspace": [
      {
        "field": "workspace.maxFileSize",
        "message": "maxFileSize must be greater than 0"
      }
    ]
  }
}
```

### Valid Validation Response

```bash
curl -X POST http://localhost:8787/api/settings/validate \
  -H "Content-Type: application/json" \
  -d '{ /* valid settings */ }'
```

**Response:**
```json
{
  "valid": true,
  "message": "Settings are valid"
}
```

---

## Notifications Configuration

### Enable Slack Notifications

```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": { /* ... */ },
    "llmSettings": { /* ... */ },
    "workspace": { /* ... */ },
    "notifications": {
      "enableEmailNotifications": true,
      "enableSlackNotifications": true,
      "slackWebhookUrl": "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX",
      "emailForAlerts": "user@example.com"
    },
    "security": { /* ... */ },
    "advanced": { /* ... */ }
  }'
```

---

## Security Configuration

### Update Password Policy

```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": { /* ... */ },
    "llmSettings": { /* ... */ },
    "workspace": { /* ... */ },
    "notifications": { /* ... */ },
    "security": {
      "enableMultiTenancy": true,
      "enableAuditLogging": true,
      "requireMFA": true,
      "sessionTimeoutMinutes": 30,
      "passwordPolicy": "12chars_special_number_uppercase"
    },
    "advanced": { /* ... */ }
  }'
```

### Enable Strict Pipeline Mode

```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": { /* ... */ },
    "llmSettings": { /* ... */ },
    "workspace": { /* ... */ },
    "notifications": { /* ... */ },
    "security": { /* ... */ },
    "advanced": {
      "pipelineStrictMode": true,
      "enableExperimentalFeatures": false,
      "logLevel": "DEBUG",
      "cacheSize_mb": 1000,
      "maxConcurrentTasks": 5,
      "retryAttempts": 5,
      "retryDelaySeconds": 2,
      "customHeaders": {}
    }
  }'
```

---

## Reset and Cleanup

### Reset All Settings to Factory Defaults

```bash
curl -X POST http://localhost:8787/api/settings/reset \
  -H "Content-Type: application/json" \
  -d '{ "confirmed": true }'
```

**Important:** Requires `confirmed: true` to prevent accidental resets.

### Delete Specific Setting

```bash
# Delete OpenRouter API key
curl -X DELETE http://localhost:8787/api/settings/apiKeys/openrouter

# Delete Slack webhook
curl -X DELETE http://localhost:8787/api/settings/notifications/slackWebhookUrl

# Delete custom header
curl -X DELETE http://localhost:8787/api/settings/advanced/customHeaders
```

---

## Error Handling

### Common Validation Errors

#### Invalid API Key Format
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "apiKeys": [
      {
        "field": "apiKeys.anthropic",
        "message": "Invalid Anthropic API key format (expected sk-ant-...)"
      }
    ]
  }
}
```

#### Temperature Out of Range
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "llmSettings": [
      {
        "field": "llmSettings.temperature",
        "message": "Temperature must be between 0 and 1"
      }
    ]
  }
}
```

#### Invalid Email Format
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "notifications": [
      {
        "field": "notifications.emailForAlerts",
        "message": "Invalid email format"
      }
    ]
  }
}
```

---

## Batch Update Example

Update multiple settings sections at once:

```bash
curl -X POST http://localhost:8787/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "apiKeys": {
      "anthropic": "sk-ant-new-key-here",
      "openrouter": "",
      "ollama_endpoint": "https://ollama.example.com:11434"
    },
    "llmSettings": {
      "provider": "anthropic",
      "model": "claude-3-5-sonnet",
      "temperature": 0.5,
      "maxTokens": 4096,
      "topP": 0.95,
      "topK": 40,
      "ollama_model": "llama2"
    },
    "workspace": {
      "maxFileSize": 104857600,
      "maxFilesPerUpload": 200,
      "allowedFileTypes": [".py", ".js", ".ts", ".java", ".go", ".rs"],
      "defaultStoragePath": "/mnt/workspace"
    },
    "notifications": {
      "enableEmailNotifications": true,
      "enableSlackNotifications": true,
      "slackWebhookUrl": "https://hooks.slack.com/services/...",
      "emailForAlerts": "alerts@company.com"
    },
    "security": {
      "enableMultiTenancy": true,
      "enableAuditLogging": true,
      "requireMFA": true,
      "sessionTimeoutMinutes": 30,
      "passwordPolicy": "12chars_special_number_uppercase"
    },
    "advanced": {
      "pipelineStrictMode": true,
      "enableExperimentalFeatures": true,
      "logLevel": "DEBUG",
      "cacheSize_mb": 1000,
      "maxConcurrentTasks": 20,
      "retryAttempts": 5,
      "retryDelaySeconds": 2,
      "customHeaders": {
        "X-Custom-Header": "value"
      }
    }
  }'
```

---

## Best Practices

1. **Always validate before saving**: Use POST /api/settings/validate to check settings first
2. **Keep API keys secure**: Never log or share API keys in plain text
3. **Use environment variables**: Store sensitive keys in environment variables
4. **Test connectivity**: Use POST /api/settings/test/:provider to verify API access
5. **Monitor logs**: Enable DEBUG logging when troubleshooting configuration issues
6. **Regular backups**: Backup settings files periodically
7. **Update gradually**: Change one section at a time when possible to identify issues
8. **Review defaults**: Always check default settings for new installations
9. **Tenant isolation**: Ensure tenant IDs are properly set in JWT tokens
10. **Encryption key**: Set SETTINGS_ENCRYPTION_KEY environment variable in production

---

## Troubleshooting

### API Key Not Working
1. Verify key format: `sk-ant-[15+ characters]` for Anthropic
2. Test with POST /api/settings/test/anthropic
3. Check key hasn't been revoked in provider console
4. Verify SETTINGS_ENCRYPTION_KEY if key appears encrypted in file

### Settings Not Persisting
1. Check file permissions: `chmod 700 ~/.ai-employee/tenants/{tenant_id}/`
2. Verify disk space available
3. Check settings file is valid JSON
4. Review error logs for write failures

### Validation Failures
1. Review error message for specific field
2. Check field type (number vs string)
3. Verify enum values are correct
4. Use POST /api/settings/validate to debug

### Multi-Tenant Issues
1. Verify tenant ID in JWT token
2. Check tenant directory exists: `~/.ai-employee/tenants/{tenant_id}/`
3. Ensure unique tenant IDs across deployments
4. Review tenant context in middleware

---

## Performance Tuning

### Reduce Cache Size (Lower Memory)
```json
"advanced": {
  "cacheSize_mb": 100
}
```

### Increase Concurrency (Higher Load)
```json
"advanced": {
  "maxConcurrentTasks": 50
}
```

### Faster Retries (Interactive Use)
```json
"advanced": {
  "retryAttempts": 2,
  "retryDelaySeconds": 0.5
}
```

### Aggressive Caching (Batch Operations)
```json
"advanced": {
  "cacheSize_mb": 2000,
  "maxConcurrentTasks": 100
}
```
