'use strict';

/**
 * Content Security Policy (CSP) Headers
 *
 * Implements defense-in-depth against XSS, clickjacking, and data exfiltration
 */

const LOG = '[CSP]';

/**
 * CSP middleware: set security headers on all responses
 */
function csrfProtection(req, res, next) {
  // Prevent MIME-type sniffing (blocks MSIE from interpreting files as HTML)
  res.setHeader('X-Content-Type-Options', 'nosniff');

  // Prevent clickjacking — disallow framing entirely
  res.setHeader('X-Frame-Options', 'DENY');

  // Control referrer exposure
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');

  // Prevent MIME-confusion attacks (block all external resources unless explicitly allowed)
  res.setHeader(
    'Content-Security-Policy',
    [
      "default-src 'self'", // Only allow same-origin by default
      "script-src 'self' 'wasm-unsafe-eval'", // Allow WASM, block inline scripts
      "style-src 'self' 'unsafe-inline'", // Allow inline styles (needed for styled-components)
      "img-src 'self' data: https:", // Allow data URLs and images
      "font-src 'self' data:", // Allow inline fonts
      "connect-src 'self' wss: ws:", // Allow WebSocket connections
      "frame-ancestors 'none'", // Prevent embedding in iframes
      "base-uri 'self'", // Prevent base tag injection
      "form-action 'self'", // Restrict form submissions
      "upgrade-insecure-requests", // Upgrade HTTP to HTTPS
    ].join('; ')
  );

  // HSTS: enforce HTTPS for 1 year (including subdomains)
  res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');

  // Permissions policy (formerly Feature-Policy)
  res.setHeader(
    'Permissions-Policy',
    [
      'geolocation=()',
      'microphone=()',
      'camera=()',
      'payment=()',
      'usb=()',
      'magnetometer=()',
      'gyroscope=()',
      'accelerometer=()',
    ].join(', ')
  );

  next();
}

/**
 * Compute SRI (Subresource Integrity) hash for a script/stylesheet
 * Use this to generate integrity hashes for critical bundles
 */
function computeSRIHash(content, algorithm = 'sha384') {
  const crypto = require('crypto');
  const hash = crypto.createHash(algorithm);
  hash.update(content);
  return `${algorithm}-${hash.digest('base64')}`;
}

/**
 * CSP violation report middleware
 * Logs CSP violations for monitoring
 */
function cspViolationReporter(req, res, next) {
  if (req.path === '/__csp-violation-report') {
    const violation = req.body || {};
    console.warn(`${LOG} CSP Violation:`, {
      blocked_uri: violation['blocked-uri'],
      violation_type: violation['violation-type'],
      source_file: violation['source-file'],
      line_number: violation['line-number'],
    });
    return res.status(204).send();
  }
  next();
}

module.exports = {
  csrfProtection,
  computeSRIHash,
  cspViolationReporter,
};
