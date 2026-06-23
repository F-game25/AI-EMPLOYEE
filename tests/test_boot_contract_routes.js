'use strict';
// Desktop boot-contract tests (F1 + F2) — pure-module, zero external deps so they run in
// CI (which installs only root deps, not backend/node_modules, so express is unavailable).
// These cover the security-critical logic both features rely on:
//   F1 — localhost-or-auth gate: loopback bypasses auth, every remote caller hits requireAuth.
//   F2 — boot-phase validation: untrusted report is type/charset/length-checked + CRLF-stripped.
// The route handlers (auth-identity.js, health.js) are thin wrappers over these modules.

const assert = require('assert');

const { validateBootPhase } = require('../backend/lib/boot-phase');
const { isLoopback, makeLocalhostOrAuth, LOOPBACK } = require('../backend/middleware/localhost-or-auth');

let passed = 0;
let failed = 0;
function t(name, fn) {
  try { fn(); passed++; console.log(`  ok  ${name}`); }
  catch (e) { failed++; console.error(`  FAIL ${name}: ${e.message}`); }
}

// ── F2: validateBootPhase ─────────────────────────────────────────────────────
t('F2 valid phase, no detail', () => {
  assert.deepStrictEqual(validateBootPhase({ phase: 'react-rendered' }),
    { ok: true, value: { phase: 'react-rendered', detail: null } });
});
t('F2 valid phase + detail', () => {
  assert.strictEqual(validateBootPhase({ phase: 'auth', detail: 'loading' }).value.detail, 'loading');
});
t('F2 missing phase rejected', () => assert.strictEqual(validateBootPhase({}).ok, false));
t('F2 non-object body rejected', () => assert.strictEqual(validateBootPhase(null).ok, false));
t('F2 bad-charset phase rejected', () => assert.strictEqual(validateBootPhase({ phase: '../../etc!!' }).ok, false));
t('F2 over-long phase rejected', () => assert.strictEqual(validateBootPhase({ phase: 'x'.repeat(65) }).ok, false));
t('F2 non-string detail rejected', () => assert.strictEqual(validateBootPhase({ phase: 'a', detail: 42 }).ok, false));
t('F2 CR/LF stripped from detail (log-injection safe)', () => {
  const d = validateBootPhase({ phase: 'a', detail: 'a\r\nFAKE LOG LINE' }).value.detail;
  assert.ok(!/[\r\n]/.test(d), 'no CR/LF survives');
});
t('F2 detail capped at 200 chars', () => {
  assert.strictEqual(validateBootPhase({ phase: 'a', detail: 'y'.repeat(500) }).value.detail.length, 200);
});

// ── F1: localhost-or-auth ─────────────────────────────────────────────────────
t('F1 loopback addresses detected', () => {
  for (const ip of LOOPBACK) {
    assert.strictEqual(isLoopback({ socket: { remoteAddress: ip } }), true, `${ip} is loopback`);
  }
});
t('F1 non-loopback not detected', () => {
  assert.strictEqual(isLoopback({ socket: { remoteAddress: '10.0.0.5' } }), false);
  assert.strictEqual(isLoopback({ socket: { remoteAddress: '8.8.8.8' } }), false);
  assert.strictEqual(isLoopback({}), false, 'missing socket is not loopback');
});
t('F1 loopback bypasses auth (next called, requireAuth not consulted)', () => {
  let authCalled = false; let nexted = false;
  const mw = makeLocalhostOrAuth(() => { authCalled = true; });
  mw({ socket: { remoteAddress: '127.0.0.1' } }, {}, () => { nexted = true; });
  assert.ok(nexted && !authCalled, 'loopback must call next() and skip requireAuth');
});
t('F1 remote caller falls through to requireAuth', () => {
  let authCalled = false;
  const mw = makeLocalhostOrAuth(() => { authCalled = true; });
  mw({ socket: { remoteAddress: '8.8.8.8' } }, {}, () => {});
  assert.ok(authCalled, 'remote must be sent through requireAuth (deny-by-default)');
});
t('F1 spoofed X-Forwarded-For cannot fake loopback (raw socket only)', () => {
  let authCalled = false;
  const mw = makeLocalhostOrAuth(() => { authCalled = true; });
  // forged header claims loopback, but the raw socket is remote → still requires auth
  mw({ socket: { remoteAddress: '8.8.8.8' }, headers: { 'x-forwarded-for': '127.0.0.1' }, ip: '127.0.0.1' }, {}, () => {});
  assert.ok(authCalled, 'header spoof must not bypass auth');
});
t('F1 requires a requireAuth function', () => {
  assert.throws(() => makeLocalhostOrAuth(null), /requireAuth/);
});

console.log(`\nboot-contract (F1 + F2): ${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
