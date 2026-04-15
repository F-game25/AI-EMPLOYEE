'use strict';

const fs = require('fs');
const path = require('path');

function nowIso() {
  return new Date().toISOString();
}

function createOfflineSecuritySyncPolicy(options = {}) {
  const queueFile = options.queueFile || path.resolve(__dirname, '../../state/security_sync_queue.json');
  const historyFile = options.historyFile || path.resolve(__dirname, '../../state/security_sync_history.log');
  const deliver = typeof options.deliver === 'function' ? options.deliver : null;

  let online = true;
  let lastSyncAt = null;
  let lastError = null;
  let queue = [];

  function ensureParent(filePath) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
  }

  function persistQueue() {
    ensureParent(queueFile);
    fs.writeFileSync(
      queueFile,
      JSON.stringify({
        online,
        last_sync_at: lastSyncAt,
        last_error: lastError,
        queue,
      }, null, 2),
      'utf8',
    );
  }

  function appendHistory(event) {
    ensureParent(historyFile);
    fs.appendFileSync(historyFile, `${JSON.stringify(event)}\n`, 'utf8');
  }

  function loadQueue() {
    try {
      if (!fs.existsSync(queueFile)) return;
      const parsed = JSON.parse(fs.readFileSync(queueFile, 'utf8'));
      queue = Array.isArray(parsed.queue) ? parsed.queue : [];
      online = parsed.online !== false;
      lastSyncAt = parsed.last_sync_at || null;
      lastError = parsed.last_error || null;
    } catch (error) {
      queue = [];
      lastError = error && error.message ? error.message : 'queue_load_failed';
    }
  }

  function deliverOne(event) {
    if (deliver) {
      deliver(event);
    } else {
      appendHistory({
        ...event,
        delivered_at: nowIso(),
      });
    }
  }

  function enqueueEvent(eventType, payload = {}) {
    const event = {
      id: `sec-sync-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      ts: nowIso(),
      event_type: String(eventType || 'unknown_security_event'),
      payload: payload && typeof payload === 'object' ? payload : {},
    };
    if (!online) {
      queue.unshift(event);
      queue = queue.slice(0, 2000);
      persistQueue();
      return {
        status: 'queued_offline',
        queue_depth: queue.length,
      };
    }
    try {
      deliverOne(event);
      lastSyncAt = nowIso();
      lastError = null;
      persistQueue();
      return {
        status: 'synced',
        queue_depth: queue.length,
      };
    } catch (error) {
      queue.unshift(event);
      queue = queue.slice(0, 2000);
      lastError = error && error.message ? error.message : 'sync_failed';
      persistQueue();
      return {
        status: 'queued_after_error',
        queue_depth: queue.length,
        error: lastError,
      };
    }
  }

  function flush() {
    if (!online || queue.length === 0) {
      return { flushed: 0, remaining: queue.length, online };
    }
    let flushed = 0;
    while (queue.length > 0) {
      const next = queue.pop();
      try {
        deliverOne(next);
        flushed += 1;
      } catch (error) {
        queue.push(next);
        lastError = error && error.message ? error.message : 'flush_failed';
        break;
      }
    }
    if (flushed > 0) {
      lastSyncAt = nowIso();
      lastError = null;
    }
    persistQueue();
    return {
      flushed,
      remaining: queue.length,
      online,
      last_sync_at: lastSyncAt,
      last_error: lastError,
    };
  }

  function setOnline(nextOnline) {
    online = Boolean(nextOnline);
    persistQueue();
    if (online) return flush();
    return { online, remaining: queue.length, flushed: 0 };
  }

  function status() {
    return {
      online,
      queue_depth: queue.length,
      last_sync_at: lastSyncAt,
      last_error: lastError,
    };
  }

  loadQueue();

  return {
    enqueueEvent,
    flush,
    setOnline,
    status,
  };
}

module.exports = {
  createOfflineSecuritySyncPolicy,
};
