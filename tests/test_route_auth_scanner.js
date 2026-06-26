'use strict';

/**
 * test_route_auth_scanner.js — Unit tests for route_auth_scanner.js.
 *
 * Tests the scanner's core logic in isolation without booting the server.
 * Exercises five scenarios:
 *   1. A seeded unprotected sensitive route is flagged (exit non-zero).
 *   2. An allowlisted public route passes even without auth.
 *   3. A protected (auth-gated) sensitive route passes.
 *   4. RBAC guards (requireScope / withRole) count as auth.
 *   5. Missing config exits non-zero (fail-closed).
 *
 * Mirror of tests/test_boot_contract_routes.js / test_update_endpoint_auth.js style:
 * standalone node script, process.exit on failure.
 */

const assert = require('assert');
const path   = require('path');
const fs     = require('fs');
const os     = require('os');
const { execSync } = require('child_process');

const REPO_ROOT    = path.resolve(__dirname, '..');
const SCANNER_PATH = path.join(REPO_ROOT, 'backend', 'security', 'route_auth_scanner.js');
const TMP_ROOT     = fs.mkdtempSync(path.join(os.tmpdir(), 'rauth-test-'));

let passed = 0;
let failed = 0;

function ok(name)       { console.log(`  ok  ${name}`); passed++; }
function fail(name, e)  { console.error(`  FAIL ${name}: ${e.message || e}`); failed++; }

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Create a self-contained fake repo in a sub-directory of TMP_ROOT.
 * Returns the path to the repo root.
 */
function makeFakeRepo(label) {
  const dir = path.join(TMP_ROOT, label.replace(/\s+/g, '-'));
  fs.mkdirSync(path.join(dir, 'backend', 'routes'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'runtime', 'config'), { recursive: true });
  return dir;
}

/**
 * Write a minimal security.yml with route_auth config to a fake repo.
 */
function writeConfig(repoDir, { publicAllowlist = [], sensitivePrefixes = [] } = {}) {
  const listYml = (items) =>
    items.length
      ? '\n' + items.map((i) => `    - "${i}"`).join('\n')
      : ' []';

  const yml = [
    '# Test-generated security.yml',
    'app:',
    '  name: "test"',
    'route_auth:',
    `  public_allowlist:${listYml(publicAllowlist)}`,
    `  sensitive_prefixes:${listYml(sensitivePrefixes)}`,
    '',
  ].join('\n');

  fs.writeFileSync(path.join(repoDir, 'runtime', 'config', 'security.yml'), yml, 'utf8');
}

/**
 * Write a minimal backend/server.js with the given route registrations.
 */
function writeServerJs(repoDir, routes) {
  const lines = ["'use strict';"];
  for (const { method, routePath, middlewares } of routes) {
    const mwPart = middlewares.length ? middlewares.join(', ') + ', ' : '';
    lines.push(`app.${method}('${routePath}', ${mwPart}(req, res) => {});`);
  }
  lines.push('');
  fs.writeFileSync(path.join(repoDir, 'backend', 'server.js'), lines.join('\n'), 'utf8');
}

/**
 * Build a patched copy of the scanner that reads from `repoDir` instead of
 * the real repo root (controlled by REPO_ROOT constant).
 * Returns path to the patched scanner script.
 */
function buildPatchedScanner(repoDir) {
  const scannerSrc = fs.readFileSync(SCANNER_PATH, 'utf8');
  const patched = scannerSrc.replace(
    /const REPO_ROOT = path\.resolve\(__dirname,[^;]+;/,
    `const REPO_ROOT = ${JSON.stringify(repoDir)};`
  );
  const patchedPath = path.join(repoDir, '_scanner.js');
  fs.writeFileSync(patchedPath, patched, 'utf8');
  return patchedPath;
}

/**
 * Run the patched scanner and return { exitCode, stdout, stderr }.
 */
function runScanner(repoDir, args = '') {
  const scannerPath = buildPatchedScanner(repoDir);
  try {
    const stdout = execSync(`node ${JSON.stringify(scannerPath)} ${args}`, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { exitCode: 0, stdout, stderr: '' };
  } catch (err) {
    return { exitCode: err.status || 1, stdout: err.stdout || '', stderr: err.stderr || '' };
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

// Test 1: unprotected sensitive route is flagged.
try {
  const repo = makeFakeRepo('t1-unprotected');
  writeConfig(repo, {
    sensitivePrefixes: ['secrets', 'forge'],
    publicAllowlist:   [],
  });
  writeServerJs(repo, [
    { method: 'get',  routePath: '/api/secrets/list', middlewares: [] },         // no auth
    { method: 'post', routePath: '/api/forge/run',    middlewares: ['requireAuth'] },
  ]);

  const { exitCode, stdout } = runScanner(repo);

  assert.strictEqual(exitCode, 1, 'exit code must be 1 when a sensitive route lacks auth');
  assert.ok(
    stdout.includes('/api/secrets/list') || stdout.includes('secrets'),
    'flagged route path must appear in output'
  );
  assert.ok(
    stdout.toUpperCase().includes('FLAGGED'),
    'output must contain the word FLAGGED'
  );

  ok('unprotected sensitive route is flagged (exit 1)');
} catch (e) { fail('unprotected sensitive route is flagged (exit 1)', e); }

// Test 2: allowlisted public route passes.
try {
  const repo = makeFakeRepo('t2-allowlisted');
  writeConfig(repo, {
    sensitivePrefixes: ['secrets', 'sandbox'],
    publicAllowlist:   ['/api/sandbox/public-demo'],
  });
  writeServerJs(repo, [
    // Hits 'sandbox' sensitive prefix but is explicitly allowlisted.
    { method: 'get', routePath: '/api/sandbox/public-demo', middlewares: [] },
    // Genuinely auth-protected.
    { method: 'get', routePath: '/api/sandbox/execute',     middlewares: ['requireAuth'] },
  ]);

  const { exitCode, stdout } = runScanner(repo);

  assert.strictEqual(exitCode, 0,
    'exit code must be 0 when the only ungated route is explicitly allowlisted');
  assert.ok(
    stdout.includes('No ungated') || stdout.includes('FLAGGED (0)'),
    'output must confirm no ungated sensitive routes'
  );

  ok('allowlisted public route passes (exit 0)');
} catch (e) { fail('allowlisted public route passes (exit 0)', e); }

// Test 3: all sensitive routes protected → exit 0.
try {
  const repo = makeFakeRepo('t3-protected');
  writeConfig(repo, {
    sensitivePrefixes: ['secrets', 'rag', 'memory'],
    publicAllowlist:   [],
  });
  writeServerJs(repo, [
    { method: 'get',    routePath: '/api/secrets/list',  middlewares: ['requireAuth'] },
    { method: 'post',   routePath: '/api/rag/query',     middlewares: ['requireAuth'] },
    { method: 'delete', routePath: '/api/memory/clear',  middlewares: ['requireAuth'] },
  ]);

  const { exitCode, stdout } = runScanner(repo);

  assert.strictEqual(exitCode, 0, 'exit code must be 0 when all sensitive routes are auth-gated');
  assert.ok(stdout.includes('No ungated'), 'output must confirm no ungated sensitive routes');

  ok('protected sensitive route passes (exit 0)');
} catch (e) { fail('protected sensitive route passes (exit 0)', e); }

// Test 4: RBAC guards count as auth.
try {
  const repo = makeFakeRepo('t4-rbac');
  writeConfig(repo, {
    sensitivePrefixes: ['evolution', 'deployment'],
    publicAllowlist:   [],
  });
  writeServerJs(repo, [
    { method: 'post', routePath: '/api/evolution/apply', middlewares: ['requireScope'] },
    { method: 'post', routePath: '/api/deployment/push', middlewares: ['withRole'] },
  ]);

  const { exitCode } = runScanner(repo);

  assert.strictEqual(exitCode, 0, 'RBAC guards (requireScope / withRole) must count as auth');
  ok('RBAC guards (requireScope / withRole) count as auth (exit 0)');
} catch (e) { fail('RBAC guards (requireScope / withRole) count as auth (exit 0)', e); }

// Test 5: missing config exits non-zero (fail-closed).
try {
  const repo = makeFakeRepo('t5-no-config');
  // No security.yml written — scanner must fail-closed.
  writeServerJs(repo, [
    { method: 'get', routePath: '/api/secrets/peek', middlewares: ['requireAuth'] },
  ]);

  const { exitCode, stdout } = runScanner(repo);

  assert.strictEqual(exitCode, 1, 'missing config must cause exit 1 (fail-closed)');
  assert.ok(
    stdout.toLowerCase().includes('missing') ||
    stdout.toLowerCase().includes('not found') ||
    stdout.toLowerCase().includes('fail-closed'),
    'output must warn about missing config'
  );

  ok('missing config exits non-zero (fail-closed)');
} catch (e) { fail('missing config exits non-zero (fail-closed)', e); }

// ── Cleanup and result ────────────────────────────────────────────────────────

try { fs.rmSync(TMP_ROOT, { recursive: true, force: true }); } catch (_) {}

console.log(`\nroute-auth-scanner: ${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
