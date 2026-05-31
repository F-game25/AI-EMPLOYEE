# Phase 4.3: Settings Deployment Checklist

Pre-deployment verification checklist for Settings system (Phase 4.3).

---

## Pre-Deployment Verification

### Code Quality

- [ ] All test files created and syntactically valid
  ```bash
  python3 -m py_compile tests/test_settings_e2e.py
  node -c tests/test_settings_frontend.js
  node -c tests/test_settings_integration.js
  ```

- [ ] Backend routes functional
  ```bash
  node -c backend/routes/settings.js
  ```

- [ ] Validator module functional
  ```bash
  node -c backend/validators/settings-validator.js
  ```

- [ ] Frontend components compile
  ```bash
  cd frontend && npm run build 2>&1 | grep -i "error" && exit 1 || exit 0
  ```

- [ ] No linting errors
  ```bash
  npm run lint
  ```

### Test Coverage

- [ ] E2E tests pass (30+ cases)
  ```bash
  python3 -m pytest tests/test_settings_e2e.py -v
  # Expected: All tests PASS
  ```

- [ ] Frontend tests pass (20+ cases)
  ```bash
  node tests/test_settings_frontend.js
  # Expected: All tests PASS
  ```

- [ ] Integration tests pass (15+ cases)
  ```bash
  node tests/test_settings_integration.js
  # Expected: All tests PASS
  ```

- [ ] Existing API tests still pass
  ```bash
  python3 -m pytest tests/test_settings_api.js -v
  ```

- [ ] All tabs render without errors
  - [ ] API Keys tab
  - [ ] LLM Settings tab
  - [ ] Workspace tab
  - [ ] Notifications tab
  - [ ] Security tab
  - [ ] Advanced tab

### Encryption & Security

- [ ] API keys encrypted on save
  - [ ] Test: Save key → Verify encrypted in storage
  ```bash
  # Manual: POST /api/settings with real key, verify storage is encrypted
  ```

- [ ] API keys masked on GET response
  - [ ] Test: Fetch → Verify key masked (sk-****-a)
  ```bash
  # Manual: GET /api/settings, verify apiKeys are masked
  ```

- [ ] Slack webhook encrypted
  - [ ] Test: Save webhook → Verify encrypted

- [ ] Ollama endpoint not encrypted
  - [ ] Test: Save endpoint → Verify unencrypted

- [ ] Encryption/decryption roundtrip works
  ```bash
  # Test: encrypt('key') → decrypt(encrypted) === 'key'
  ```

- [ ] No API keys in logs
  - [ ] Check python-backend.log for secrets
  - [ ] Check node logs for secrets

- [ ] SETTINGS_ENCRYPTION_KEY set in production
  - [ ] Verify env var exists
  - [ ] Verify rotated from default

### Multi-Tenancy

- [ ] Tenant isolation verified
  - [ ] Tenant A and B have separate settings
  - [ ] Tenant A cannot see Tenant B's settings
  ```bash
  # Manual: Register 2 users, verify isolated settings
  ```

- [ ] Tenant context extracted correctly
  - [ ] GET /api/settings uses req.tenant.id
  - [ ] POST /api/settings uses req.tenant.id
  - [ ] Reset uses req.tenant.id

- [ ] Settings path uses tenant ID
  ```bash
  ~/.ai-employee/tenants/{tenant_id}/settings.json
  ```

- [ ] First tenant gets defaults
  - [ ] New tenant → GET /api/settings → returns defaults

- [ ] Tenant reset only affects that tenant
  - [ ] Reset Tenant A → Tenant B unchanged

### Validation Rules

- [ ] All 30+ validation rules implemented
  - [ ] API key format validation (anthropic, openrouter)
  - [ ] Ollama endpoint format validation
  - [ ] LLM provider validation
  - [ ] Model validation per provider
  - [ ] Temperature range validation (0-1)
  - [ ] Max tokens range validation (100-4096)
  - [ ] TopP range validation (0-1)
  - [ ] TopK range validation (0-100)
  - [ ] File type format validation (.ext)
  - [ ] File types non-empty validation
  - [ ] Max file size validation (> 0)
  - [ ] Max files per upload validation (>= 1)
  - [ ] Email format validation
  - [ ] Slack webhook format validation
  - [ ] Session timeout validation (>= 1)
  - [ ] Log level validation
  - [ ] Cache size validation (> 0)
  - [ ] Max concurrent tasks validation (>= 1)
  - [ ] Retry attempts validation (1-10)
  - [ ] Retry delay validation (>= 1)
  - [ ] And 10+ more...

- [ ] Validation errors are descriptive
  ```bash
  # Test: Invalid setting → Error message explains issue
  ```

- [ ] POST /validate works without saving
  ```bash
  # Test: POST /api/settings/validate → no side effects
  ```

- [ ] Validation prevents invalid saves
  ```bash
  # Test: POST /api/settings invalid → 400 error, not saved
  ```

### Provider Support

- [ ] Anthropic provider works
  - [ ] Valid key format: sk-ant-*
  - [ ] Test endpoint reachable
  - [ ] Model list includes Anthropic models
  ```bash
  # Test: POST /api/settings/test/anthropic
  ```

- [ ] OpenRouter provider works
  - [ ] Valid key format: sk-or-*
  - [ ] Test endpoint reachable
  - [ ] Model list includes OpenRouter models
  ```bash
  # Test: POST /api/settings/test/openrouter
  ```

- [ ] Ollama provider works
  - [ ] Valid endpoint format: http(s)://host:port
  - [ ] Test endpoint reachable
  - [ ] Model list includes Ollama models
  ```bash
  # Test: POST /api/settings/test/ollama
  ```

- [ ] Provider switching works
  - [ ] Change provider → Model options update
  - [ ] Switch anthropic → openrouter → ollama
  - [ ] Invalid model for provider caught

### API Endpoints

- [ ] GET /api/settings works
  - [ ] Returns all settings
  - [ ] Returns masked API keys
  - [ ] Uses tenant context
  - [ ] Performance: < 100ms

- [ ] POST /api/settings works
  - [ ] Saves all settings
  - [ ] Encrypts sensitive fields
  - [ ] Returns masked response
  - [ ] Updates env vars
  - [ ] Uses file locking
  - [ ] Performance: < 500ms

- [ ] POST /api/settings/validate works
  - [ ] Validates without saving
  - [ ] Returns validation errors
  - [ ] No side effects

- [ ] POST /api/settings/test/:provider works
  - [ ] Tests Anthropic connectivity
  - [ ] Tests OpenRouter connectivity
  - [ ] Tests Ollama connectivity
  - [ ] Returns success/failure

- [ ] POST /api/settings/reset works
  - [ ] Requires confirmed flag
  - [ ] Resets to defaults
  - [ ] Only affects current tenant

- [ ] DELETE /api/settings/:section/:key works
  - [ ] Deletes specific setting
  - [ ] Protects critical sections
  - [ ] Preserves other settings

### UI/UX

- [ ] All 6 tabs render
  - [ ] API Keys tab renders
  - [ ] LLM Settings tab renders
  - [ ] Workspace tab renders
  - [ ] Notifications tab renders
  - [ ] Security tab renders
  - [ ] Advanced tab renders

- [ ] Tab switching works
  - [ ] Click tab → content updates
  - [ ] No errors on switch
  - [ ] Scroll position reset

- [ ] Form inputs work
  - [ ] Text inputs accept values
  - [ ] Sliders update values
  - [ ] Toggles enable/disable
  - [ ] Checkboxes toggle
  - [ ] Selects change options

- [ ] Validation errors display
  - [ ] Invalid field gets red border
  - [ ] Error message displays
  - [ ] Multiple errors shown
  - [ ] Error clears on valid input

- [ ] Success toast appears
  - [ ] After save → success toast
  - [ ] Disappears after 3 seconds
  - [ ] Shows correct message

- [ ] Error toast appears
  - [ ] On save error → error toast
  - [ ] Shows error details
  - [ ] User can dismiss

- [ ] Loading state shown
  - [ ] Loading spinner on initial fetch
  - [ ] Saving spinner on POST
  - [ ] Disabled buttons while saving

- [ ] Responsiveness
  - [ ] Works on mobile
  - [ ] Works on tablet
  - [ ] Works on desktop
  - [ ] No layout breaks

### Performance

- [ ] Settings load quickly
  - [ ] GET /api/settings: < 100ms
  - [ ] No blocking operations

- [ ] Settings save quickly
  - [ ] POST /api/settings: < 500ms
  - [ ] No blocking file I/O

- [ ] Validation is fast
  - [ ] Inline validation: < 50ms
  - [ ] Server validation: < 200ms

- [ ] Provider test is responsive
  - [ ] Test timeout: 5 seconds
  - [ ] No hanging requests

- [ ] Frontend responsive
  - [ ] Tab switch: instant
  - [ ] Form input: no lag
  - [ ] Scrolling: smooth

### Error Handling

- [ ] 400 errors handled
  - [ ] Invalid request → 400 with message
  - [ ] Invalid data → 400 with errors

- [ ] 404 errors handled
  - [ ] Non-existent setting → 404
  - [ ] User-friendly message

- [ ] 500 errors handled
  - [ ] Server error → 500 with message
  - [ ] Error logged
  - [ ] User notified

- [ ] File system errors handled
  - [ ] Missing directory → created
  - [ ] File read error → graceful fallback
  - [ ] File write error → error response

- [ ] Network errors handled
  - [ ] Connection timeout → error message
  - [ ] Provider test failure → clear message

### Documentation

- [ ] PHASE_4_TESTING_GUIDE.md complete
  - [ ] All test files documented
  - [ ] Examples provided
  - [ ] CI/CD integration documented

- [ ] PHASE_4_DEPLOYMENT_CHECKLIST.md complete
  - [ ] All checks documented
  - [ ] Success criteria clear

- [ ] Code comments present
  - [ ] Complex logic documented
  - [ ] Validation rules explained
  - [ ] Encryption noted

- [ ] README updated
  - [ ] Settings feature documented
  - [ ] API endpoints documented
  - [ ] Usage examples provided

### Database/Storage

- [ ] Settings file created correctly
  ```bash
  ls -la ~/.ai-employee/tenants/default/settings.json
  ```

- [ ] File permissions correct
  ```bash
  stat ~/.ai-employee/tenants/default/settings.json
  # Should be readable/writable by app
  ```

- [ ] File locking works
  - [ ] Concurrent saves don't corrupt
  - [ ] fcntl locks functional

- [ ] Backup exists
  - [ ] Settings backed up before deploy
  - [ ] Can rollback if needed

### Integration Tests

- [ ] Run full test suite
  ```bash
  npm run test:settings:all
  ```

- [ ] All 50+ tests pass
  - [ ] 30+ E2E tests ✓
  - [ ] 20+ Frontend tests ✓
  - [ ] 15+ Integration tests ✓

- [ ] No test flakiness
  - [ ] Run 3x → same results
  - [ ] No race conditions
  - [ ] No timing issues

- [ ] Verification script passes
  ```bash
  bash scripts/verify-settings.sh
  # Expected: All checks PASS
  ```

### Production Readiness

- [ ] Environment variables set
  - [ ] SETTINGS_ENCRYPTION_KEY set
  - [ ] Not using default value
  - [ ] Securely stored

- [ ] Logging functional
  - [ ] Settings operations logged
  - [ ] Errors captured
  - [ ] No sensitive data in logs

- [ ] Monitoring ready
  - [ ] Metrics available
  - [ ] Alerts configured
  - [ ] Performance tracked

- [ ] Rollback plan exists
  - [ ] Previous version available
  - [ ] Rollback procedure documented
  - [ ] Tested

- [ ] Deployment plan exists
  - [ ] Deployment steps documented
  - [ ] Downtime requirements clear
  - [ ] Backup/restore tested

---

## Sign-Off

### Development Team
- [ ] Code complete
- [ ] Tests pass
- [ ] Documentation complete
- **Developer:** _________________ **Date:** _______

### QA Team
- [ ] Manual testing complete
- [ ] All checklist items verified
- [ ] No blockers found
- **QA Lead:** _________________ **Date:** _______

### DevOps/Operations
- [ ] Infrastructure ready
- [ ] Monitoring configured
- [ ] Rollback tested
- [ ] Ready for production
- **DevOps Lead:** _________________ **Date:** _______

### Product Manager
- [ ] Feature meets requirements
- [ ] User experience verified
- [ ] Documentation adequate
- **PM:** _________________ **Date:** _______

---

## Deployment

### Pre-Deployment

1. Create release branch
   ```bash
   git checkout -b release/phase-4.3
   ```

2. Update version
   ```bash
   npm version minor
   ```

3. Run final tests
   ```bash
   npm run test:settings:all
   bash scripts/verify-settings.sh
   ```

4. Commit
   ```bash
   git add .
   git commit -m "Phase 4.3: Settings Integration Testing & E2E Validation"
   git push origin release/phase-4.3
   ```

5. Create pull request
   ```bash
   # Create PR, request reviews
   ```

### Deployment

1. Merge to main
   ```bash
   git checkout main
   git merge release/phase-4.3
   ```

2. Deploy to staging
   ```bash
   npm start
   # Run smoke tests
   ```

3. Deploy to production
   ```bash
   # Follow deployment procedure
   # Monitor logs for errors
   ```

### Post-Deployment

1. Verify in production
   ```bash
   curl https://api.example.com/api/settings
   # Should return masked settings
   ```

2. Monitor metrics
   - Settings load time
   - Save success rate
   - Error rate
   - User feedback

3. Update status
   ```bash
   git tag phase-4.3-deployed
   git push origin phase-4.3-deployed
   ```

---

## Rollback

If issues discovered:

1. Identify issue
2. Stop current deployment
3. Restore previous version
   ```bash
   git checkout previous-tag
   npm start
   ```
4. Restore settings files
5. Verify functionality
6. Investigate root cause

---

## Success Criteria

Phase 4.3 is complete when:

✓ All 50+ tests pass  
✓ All 6 tabs render and function  
✓ All validation rules work  
✓ API keys encrypted/masked  
✓ Multi-tenant isolation verified  
✓ All 3 providers tested  
✓ Performance acceptable (< 500ms save)  
✓ No sensitive data in logs  
✓ Documentation complete  
✓ Team sign-off complete  

---

**Phase 4.3: Settings Integration Testing & E2E Validation**  
**Status: Ready for Deployment ✓**
