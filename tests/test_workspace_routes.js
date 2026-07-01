process.env.JWT_SECRET_KEY = process.env.JWT_SECRET_KEY || 'ci-test-secret-not-real';
const assert = require('assert');
const path = require('path');
const os = require('os');
const fs = require('fs');

// Regression coverage for the CodeRabbit review on PR #335
// (backend/routes/workspace.js): tenant context must fail closed instead of
// silently defaulting to "default", and file lookups must use an exact id
// match instead of String.startsWith (which lets a short/colliding id select
// the wrong file in the same tenant's directory).
//
// Dispatches through the router itself (not a plucked-out single handler) so
// the router.use(requireTenant()) gate registered ahead of the routes is
// actually exercised, not bypassed.
const router = require('../backend/routes/workspace');

function dispatch(method, url, { tenantId } = {}) {
  const req = {
    method: method.toUpperCase(),
    url,
    originalUrl: url,
    headers: {},
    tenant: tenantId ? { tenantId } : undefined,
  };
  return new Promise((resolve, reject) => {
    const res = {
      statusCode: 200,
      status(code) { this.statusCode = code; return this; },
      json(body) { resolve({ status: this.statusCode, body }); return this; },
      download(filePath) {
        try { resolve({ status: this.statusCode, body: fs.readFileSync(filePath, 'utf8') }); }
        catch (err) { reject(err); }
        return this;
      },
    };
    router(req, res, (err) => {
      if (err) return reject(err);
      // Fell through the whole router with no route matching / handling it.
      resolve({ status: 404, body: { ok: false, error: 'unhandled' } });
    });
  });
}

(async () => {
  const tenantId = 'wsroute-test-' + Date.now();
  const tenantRoot = path.join(os.homedir(), '.ai-employee', 'tenants', tenantId);
  const dir = path.join(tenantRoot, 'workspace', 'uploads');

  try {
    // 1. No tenant context -> router.use(requireTenant()) must reject before
    // any handler runs, not silently fall back to "default".
    const noTenant = await dispatch('GET', '/files', {});
    assert.equal(noTenant.status, 401, `expected 401 with no tenant context, got ${noTenant.status}: ${JSON.stringify(noTenant.body)}`);
    console.log('[✓] no tenant context -> 401 (fail closed, not defaulted to "default")');

    // 2. Valid tenant, nothing uploaded yet.
    const listEmpty = await dispatch('GET', '/files', { tenantId });
    assert.equal(listEmpty.status, 200);
    assert.deepEqual(listEmpty.body, { files: [] });
    console.log('[✓] valid tenant with no uploads -> 200 empty list');

    // 3. Seed two files with a colliding prefix and verify exact-match resolution.
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'abc.txt'), 'short-id-file');
    fs.writeFileSync(path.join(dir, 'abcdef.txt'), 'colliding-prefix-file');

    const downloadShort = await dispatch('GET', '/download/abc', { tenantId });
    assert.equal(downloadShort.status, 200);
    assert.equal(downloadShort.body, 'short-id-file', 'exact-match regression: prefix collision resolved the wrong file');
    console.log('[✓] exact fileId match resolves "abc", not the colliding "abcdef"');

    const downloadMissing = await dispatch('GET', '/download/nonexistent', { tenantId });
    assert.equal(downloadMissing.status, 404);
    console.log('[✓] unknown fileId -> 404');

    const deleted = await dispatch('DELETE', '/files/abc', { tenantId });
    assert.equal(deleted.status, 200);
    assert(!fs.existsSync(path.join(dir, 'abc.txt')), 'delete must remove the exact-matched file');
    assert(fs.existsSync(path.join(dir, 'abcdef.txt')), 'delete must not touch the colliding "abcdef" file');
    console.log('[✓] delete removes the exact-matched file only, leaves the colliding one intact');

    console.log('[✓] workspace routes regression tests passed');
  } finally {
    fs.rmSync(tenantRoot, { recursive: true, force: true });
  }
})().catch(err => {
  console.error(err);
  process.exit(1);
});
