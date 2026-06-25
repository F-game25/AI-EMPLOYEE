'use strict';

/**
 * test_jwt_alg_pin.js — Regression guard (M1-T7).
 *
 * Every `jwt.verify(...)` in backend/ MUST pin an `algorithms:` option, so a
 * token signed with an unexpected algorithm (e.g. alg:none, or RS256 abused as
 * HMAC) can never be accepted. This locks the pins applied across the 10 HMAC
 * verify sites + the OIDC asymmetric path. Static check — no server boot.
 *
 * Standalone node script; process.exit(1) on failure (matches CI test-node style).
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const BACKEND = path.resolve(__dirname, '..', 'backend');

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === 'node_modules') continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.name.endsWith('.js')) out.push(p);
  }
  return out;
}

// Balanced-parens slice of the call starting at the '(' index (handles
// multi-line calls where the options object spans several lines).
function callText(src, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === '(') depth++;
    else if (src[i] === ')') {
      depth--;
      if (depth === 0) return src.slice(openIdx, i + 1);
    }
  }
  return src.slice(openIdx, openIdx + 400);
}

let checked = 0;
const offenders = [];

for (const file of walk(BACKEND)) {
  const src = fs.readFileSync(file, 'utf8');
  const re = /jwt\.verify\s*\(/g; // jwt.verify only — not jwt.decode / jwt.sign
  let m;
  while ((m = re.exec(src)) !== null) {
    const openIdx = m.index + m[0].length - 1; // position of '('
    const text = callText(src, openIdx);
    checked++;
    if (!/algorithms\s*:/.test(text)) {
      offenders.push(`${path.relative(BACKEND, file)}: ${text.replace(/\s+/g, ' ').slice(0, 90)}`);
    }
  }
}

console.log(`jwt.verify calls checked: ${checked}, unpinned: ${offenders.length}`);
assert.ok(checked > 0, 'expected to find at least one jwt.verify call');
assert.strictEqual(
  offenders.length, 0,
  `jwt.verify without an algorithms pin (alg-confusion risk):\n  ${offenders.join('\n  ')}`
);
console.log('jwt-alg-pin: OK — every jwt.verify pins algorithms');
