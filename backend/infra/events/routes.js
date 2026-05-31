'use strict';

/**
 * Event bus management routes.
 *   GET  /api/events/stats     — bus statistics + transport health
 *   GET  /api/events/dlq       — last N dead-letter queue entries
 *   POST /api/events/dlq/retry — replay a DLQ entry by id
 *   POST /api/events/publish   — manual publish (admin only)
 */

const { Router } = require('express');
const { getEventBus, EVENT_TYPES } = require('./bus');
const router = Router();

router.get('/stats', async (req, res) => {
  try {
    const bus = await getEventBus();
    res.json({
      ok: true,
      stats: bus.stats,
      transports: bus.transports,
      dlq_size: bus.dlq.size,
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

router.get('/dlq', async (req, res) => {
  const n = Math.min(parseInt(req.query.n) || 50, 500);
  const bus = await getEventBus();
  res.json({ ok: true, entries: bus.dlq.peek(n), total: bus.dlq.size });
});

// Admin: manually publish an event (for testing / recovery)
router.post('/publish', async (req, res) => {
  const { type, payload, tenant_id } = req.body || {};
  if (!type || !payload) return res.status(400).json({ ok: false, error: 'type and payload required' });
  if (!Object.values(EVENT_TYPES).includes(type)) {
    return res.status(400).json({ ok: false, error: `Unknown event type: ${type}` });
  }
  const bus = await getEventBus();
  const envelope = await bus.publish(type, payload, { tenant_id: tenant_id || 'system' });
  res.json({ ok: true, envelope });
});

module.exports = router;
