/**
 * Tests for makeRateLimit and makeTTLCache factories.
 * Inlined here to avoid coupling to server.js internals.
 */
"use strict";

let passed = 0;
let failed = 0;

function assert(cond, msg) {
  if (cond) {
    console.log(`  ✓ ${msg}`);
    passed++;
  } else {
    console.error(`  ✗ ${msg}`);
    failed++;
  }
}

// ── Factories (mirrored from server.js) ──────────────────────────────────────

function makeRateLimit(max, windowMs = 60_000) {
  const buckets = new Map();
  return (req, res, next) => {
    const ip = req.ip || "unknown";
    const now = Date.now();
    const hits = (buckets.get(ip) || []).filter((t) => now - t < windowMs);
    hits.push(now);
    buckets.set(ip, hits);
    if (hits.length > max) {
      res.set("Retry-After", Math.ceil(windowMs / 1000));
      return res.status(429).json({ ok: false, error: "Rate limit exceeded" });
    }
    next();
  };
}

function makeTTLCache(ttlMs = 30_000) {
  let _cache = null;
  let _expiry = 0;
  return (req, res, next) => {
    if (_cache && Date.now() < _expiry) {
      res.set("X-Cache", "HIT");
      return res.json(_cache);
    }
    const _json = res.json.bind(res);
    res.json = (body) => {
      _cache = body;
      _expiry = Date.now() + ttlMs;
      res.set("X-Cache", "MISS");
      return _json(body);
    };
    next();
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeReq(ip = "127.0.0.1") {
  return { ip };
}

function makeRes() {
  const headers = {};
  let statusCode = 200;
  let body = null;
  const res = {
    headers,
    statusCode,
    set(k, v) { headers[k] = v; },
    status(code) { statusCode = code; res.statusCode = code; return res; },
    json(b) { body = b; return res; },
    getBody() { return body; },
    getHeader(k) { return headers[k]; },
  };
  return res;
}

// ── makeRateLimit tests ───────────────────────────────────────────────────────

console.log("\nRate limit tests:");

{
  const rl = makeRateLimit(3, 60_000);
  const req = makeReq("1.2.3.4");
  let nextCalled = 0;

  for (let i = 0; i < 3; i++) {
    const res = makeRes();
    rl(req, res, () => nextCalled++);
  }
  assert(nextCalled === 3, "allows up to max requests");

  const res = makeRes();
  rl(req, res, () => nextCalled++);
  assert(nextCalled === 3, "blocks 4th request (does not call next)");
  assert(res.statusCode === 429, "returns 429 on limit exceeded");
  assert(res.getBody()?.error === "Rate limit exceeded", "returns error message");
  assert(res.getHeader("Retry-After") > 0, "sets Retry-After header");
}

{
  // Different IPs are tracked separately
  const rl = makeRateLimit(1, 60_000);
  let nextCalled = 0;
  rl(makeReq("10.0.0.1"), makeRes(), () => nextCalled++);
  rl(makeReq("10.0.0.2"), makeRes(), () => nextCalled++);
  assert(nextCalled === 2, "different IPs have independent buckets");
}

{
  // Window expiry: use a tiny window and fake time via date trick
  const rl = makeRateLimit(1, 1); // 1ms window
  const req = makeReq("9.9.9.9");
  let nextCalled = 0;
  rl(req, makeRes(), () => nextCalled++);

  // Wait 2ms so the window expires
  const start = Date.now();
  while (Date.now() - start < 5) { /* spin */ }

  rl(req, makeRes(), () => nextCalled++);
  assert(nextCalled === 2, "expired window resets bucket — second request allowed");
}

// ── makeTTLCache tests ────────────────────────────────────────────────────────

console.log("\nTTL cache tests:");

{
  const cache = makeTTLCache(60_000);
  const req = makeReq();
  let nextCalled = 0;

  // First call — MISS, populate cache
  const res1 = makeRes();
  cache(req, res1, () => { nextCalled++; res1.json({ value: 42 }); });
  assert(nextCalled === 1, "first call invokes next (MISS)");
  assert(res1.getHeader("X-Cache") === "MISS", "first call sets X-Cache: MISS");

  // Second call — HIT from cache
  const res2 = makeRes();
  cache(req, res2, () => nextCalled++);
  assert(nextCalled === 1, "second call does NOT invoke next (HIT)");
  assert(res2.getHeader("X-Cache") === "HIT", "second call sets X-Cache: HIT");
  assert(res2.getBody()?.value === 42, "cached body returned on HIT");
}

{
  // TTL expiry
  const cache = makeTTLCache(1); // 1ms TTL
  const req = makeReq();
  let nextCalled = 0;

  const res1 = makeRes();
  cache(req, res1, () => { nextCalled++; res1.json({ v: 1 }); });

  const start = Date.now();
  while (Date.now() - start < 5) { /* spin */ }

  const res2 = makeRes();
  cache(req, res2, () => { nextCalled++; res2.json({ v: 2 }); });
  assert(nextCalled === 2, "expired TTL causes cache miss — next called again");
  assert(res2.getHeader("X-Cache") === "MISS", "stale cache emits MISS");
}

// ── Summary ───────────────────────────────────────────────────────────────────

console.log(`\nRate limit + cache: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
