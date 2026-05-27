'use strict';

function createRouteRateLimit({ max = 60, windowMs = 60_000, keyPrefix = 'route' } = {}) {
  const buckets = new Map();
  return function rateLimit(req, res, next) {
    const rawIp = req.ip || req.connection?.remoteAddress || 'unknown';
    const key = `${keyPrefix}:${rawIp}`;
    const now = Date.now();
    const hits = (buckets.get(key) || []).filter((ts) => now - ts < windowMs);
    hits.push(now);
    buckets.set(key, hits);
    if (hits.length > max) {
      res.set('Retry-After', String(Math.ceil(windowMs / 1000)));
      return res.status(429).json({ ok: false, error: 'Rate limit exceeded' });
    }
    next();
  };
}

module.exports = { createRouteRateLimit };
