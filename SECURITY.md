# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in AI Employee, please report it responsibly:

1. **Do NOT** create a public GitHub issue
2. Email the maintainer privately with full details
3. Allow reasonable time for the issue to be addressed before public disclosure

## Security Features (openclaw-2)

AI Employee integrates the security model from openclaw-2, providing:

### Authentication & Authorization
- **JWT-based** token authentication with configurable expiration
- **Bcrypt** password hashing (cost factor 12)
- Configurable token lifetime and session limits
- Rate limiting on all authentication endpoints

### Input Validation
- Path traversal prevention (`InputSanitizer.validate_path`)
- Filename sanitization (`InputSanitizer.sanitize_filename`)
- Input length caps and null-byte filtering
- SQL injection prevention when a database is used

### Encryption
- **AES-256-GCM** encryption for data at rest (via Fernet)
- **PBKDF2** key derivation (100,000 iterations, SHA-256)
- Cryptographically secure random token generation
- SHA-256 hashing utilities

### Network Security
- Localhost-only binding by default (`127.0.0.1`)
- Strict CORS origin controls
- HTTP security headers on every response:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security`
  - `Content-Security-Policy: default-src 'self'`

### Privacy
- Telemetry and analytics **disabled by default**
- Optional blocking of all external API calls
- Local data storage only
- Configurable data retention policies

### Audit Logging
- Every HTTP request and response logged (security-relevant events)
- Failed authentication attempts recorded
- API call audit trail
- Structured JSON log format

---

## Security Best Practices for Deployment

### Network Security

#### ✅ DO
- Keep the server bound to `127.0.0.1` for local-only access
- Use VPN or SSH tunnelling if remote access is needed
- Place behind a reverse proxy (nginx) if exposing to the network
- Use firewall rules to restrict access to authorised IPs

#### ❌ DON'T
- Expose directly to the internet without additional security layers
- Disable rate limiting
- Run with `debug: true` in production
- Bind to `0.0.0.0` unless properly secured

### Authentication

#### ✅ DO
- Set `JWT_SECRET_KEY` via environment variable (never in config files)
- Use strong passwords: 12+ characters, mixed case, numbers, special chars
- Rotate JWT secrets regularly (every 90 days recommended)
- Use unique secrets per installation

#### ❌ DON'T
- Use the placeholder default JWT secret
- Store passwords in plain text
- Disable password complexity requirements

### Configuration & Secrets

#### ✅ DO
- Use `security.local.yml` for local overrides (gitignored)
- Store all secrets in environment variables
- Review startup security warnings
- Generate a fresh JWT secret on every new installation:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

#### ❌ DON'T
- Commit `security.local.yml` or `.env` to version control
- Store API keys in configuration files
- Ignore security warnings on startup

---

## Security Checklist

Before running in production:

- [ ] `JWT_SECRET_KEY` changed from the default placeholder
- [ ] Strong passwords configured
- [ ] Application bound to localhost only (or properly secured if networked)
- [ ] Rate limiting enabled (`security.rate_limit_enabled: true`)
- [ ] Encryption at rest enabled (`privacy.encrypt_data_at_rest: true`)
- [ ] Telemetry disabled (`privacy.telemetry_enabled: false`)
- [ ] Audit logging enabled (`logging.audit_enabled: true`)
- [ ] Security headers verified (check with `curl -I http://127.0.0.1:8787`)
- [ ] Dependencies updated (`pip install -r requirements.txt --upgrade`)
- [ ] File permissions secured (`chmod 600 .env security.local.yml`)
- [ ] No secrets committed to version control

---

## Configuration

### Environment Variables

```bash
# Required
export JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# Optional AI provider keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

### security.yml / security.local.yml

Place a `security.local.yml` alongside `server.py` (gitignored) to override
any settings from `runtime/config/security.yml`:

```yaml
security:
  access_token_expire_minutes: 15   # Shorter token lifetime
  min_password_length: 16           # Stricter passwords
  rate_limit_per_minute: 30         # Tighter rate limit

privacy:
  external_api_calls_disabled: true  # Maximum privacy
```

---

## Known Limitations

This implementation protects against:
- ✅ External network access (localhost-only default)
- ✅ Brute force (rate limiting)
- ✅ Path traversal (input validation)
- ✅ XSS (input sanitisation + CSP headers)
- ✅ CSRF (token-based auth)
- ✅ Session hijacking (secure JWTs with expiry)
- ✅ Weak passwords (strength requirements)

Out of scope:
- Physical access to the machine
- OS-level vulnerabilities
- Hardware attacks
- Social engineering

---

## Incident Response

If you suspect a security incident:

1. **Isolate** — stop the application and disconnect from the network
2. **Assess** — review `logs/audit.log` for suspicious activity
3. **Contain** — identify and remove the threat
4. **Recover** — restore from a clean backup if needed
5. **Learn** — document the incident and improve controls

---

**Last Updated**: 2026-03-25  
**Version**: 2.0.0 (openclaw-2 security model)
