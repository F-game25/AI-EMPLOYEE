from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout.strip())


def test_secret_store_alias_and_redaction():
    out = _run_node(
        """
const { SecretStore } = require('./backend/security/secrets');
const store = new SecretStore({ AZTSA_GATEWAY_KEY: 'super-secret-key' });
const value = store.get('API_GATEWAY_KEY', { aliases: ['AZTSA_GATEWAY_KEY'] });
const redacted = SecretStore.redact(value);
console.log(JSON.stringify({ value, redacted }));
"""
    )
    assert out["value"] == "super-secret-key"
    assert out["redacted"].startswith("su")
    assert out["redacted"].endswith("ey")


def test_offline_security_sync_queues_then_flushes(tmp_path):
    queue_file = tmp_path / "sync_queue.json"
    history_file = tmp_path / "sync_history.log"
    out = _run_node(
        f"""
const {{ createOfflineSecuritySyncPolicy }} = require('./backend/security/offline_sync_policy');
const sync = createOfflineSecuritySyncPolicy({{
  queueFile: {json.dumps(str(queue_file))},
  historyFile: {json.dumps(str(history_file))},
}});
const offline = sync.setOnline(false);
const queued = sync.enqueueEvent('security_gateway_block', {{ reason: 'test' }});
const online = sync.setOnline(true);
console.log(JSON.stringify({{ offline, queued, online, final: sync.status() }}));
"""
    )
    assert out["queued"]["status"] == "queued_offline"
    assert out["online"]["flushed"] >= 1
    assert out["final"]["queue_depth"] == 0
    assert history_file.exists()


def test_api_gateway_honeypot_and_api_key_enforcement():
    out = _run_node(
        """
const { SecretStore } = require('./backend/security/secrets');
const { createApiGatewayProtector } = require('./backend/security/api_gateway');
const events = [];
const protector = createApiGatewayProtector({
  secretStore: new SecretStore({ API_GATEWAY_KEY: 'k1' }),
  emitObservabilityEvent: (eventType, payload) => events.push({ eventType, payload }),
});
function runRequest(req) {
  const response = {
    _status: 200,
    body: null,
    headers: {},
    set(key, value) { this.headers[key] = value; },
    status(code) { this._status = code; return this; },
    json(body) { this.body = body; return this; },
  };
  let nextCalled = false;
  protector.middleware(req, response, () => { nextCalled = true; });
  return { status: response._status, body: response.body, nextCalled };
}
const honeypot = runRequest({
  method: 'GET',
  path: '/admin',
  originalUrl: '/api/admin',
  ip: '1.1.1.1',
  socket: { remoteAddress: '1.1.1.1' },
  get: () => '',
});
const blocked = runRequest({
  method: 'POST',
  path: '/tasks/run',
  originalUrl: '/api/tasks/run',
  ip: '1.1.1.1',
  socket: { remoteAddress: '1.1.1.1' },
  get: (name) => (name === 'content-length' ? '10' : ''),
});
const allowed = runRequest({
  method: 'POST',
  path: '/tasks/run',
  originalUrl: '/api/tasks/run',
  ip: '1.1.1.1',
  socket: { remoteAddress: '1.1.1.1' },
  get: (name) => {
    if (name === 'x-api-key') return 'k1';
    if (name === 'content-length') return '10';
    return '';
  },
});
console.log(JSON.stringify({ honeypot, blocked, allowed, eventsCount: events.length, status: protector.status() }));
"""
    )
    assert out["honeypot"]["status"] == 200
    assert out["blocked"]["status"] == 401
    assert out["allowed"]["nextCalled"] is True
    assert out["status"]["honeypot_events"] >= 1
    assert out["eventsCount"] >= 1


def test_anomaly_response_forces_manual_and_strict_mode():
    out = _run_node(
        """
const { createAnomalyResponder } = require('./backend/security/anomaly_response');
let mode = 'AUTO';
let stopCalls = 0;
let strictEnabled = false;
const responder = createAnomalyResponder({
  sampleSnapshot: () => ({ metrics: { errors_per_minute: 8 } }),
  getMode: () => mode,
  setMode: (next) => { mode = next; return mode; },
  stopAllAgents: () => { stopCalls += 1; },
  gatewayProtector: {
    status: () => ({ honeypot_hits_5m: 3 }),
    setStrictMode: (enabled) => { strictEnabled = enabled; },
  },
});
const result = responder.evaluate();
console.log(JSON.stringify({ result, mode, stopCalls, strictEnabled }));
"""
    )
    assert out["mode"] == "MANUAL"
    assert out["strictEnabled"] is True
    assert len(out["result"]["actions"]) >= 2
