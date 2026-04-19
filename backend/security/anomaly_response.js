'use strict';

function createAnomalyResponder(options = {}) {
  const sampleSnapshot = options.sampleSnapshot;
  const getMode = options.getMode;
  const setMode = options.setMode;
  const stopAllAgents = options.stopAllAgents;
  const addActivity = options.addActivity || (() => {});
  const appendAutoFixLog = options.appendAutoFixLog || (() => {});
  const emitObservabilityEvent = options.emitObservabilityEvent || (() => {});
  const gatewayProtector = options.gatewayProtector;

  const state = {
    last_actions: [],
    enabled: true,
  };

  function trackAction(type, detail) {
    const row = {
      type,
      ts: new Date().toISOString(),
      detail,
    };
    state.last_actions.unshift(row);
    state.last_actions = state.last_actions.slice(0, 100);
    appendAutoFixLog({
      type: 'anomaly_response',
      action: type,
      detail,
    });
    emitObservabilityEvent('anomaly_response', {
      action: type,
      ...detail,
    });
    return row;
  }

  function evaluate() {
    if (!state.enabled || typeof sampleSnapshot !== 'function') {
      return { actions: [], reason: 'disabled' };
    }

    const snapshot = sampleSnapshot();
    const errors = Number((snapshot.metrics || {}).errors_per_minute || 0);
    const actions = [];
    const gateway = gatewayProtector && typeof gatewayProtector.status === 'function'
      ? gatewayProtector.status()
      : null;
    const honeypotHits5m = gateway ? Number(gateway.honeypot_hits_5m || 0) : 0;

    if (errors >= 6 && typeof getMode === 'function' && typeof setMode === 'function') {
      const currentMode = String(getMode() || '').toUpperCase();
      if (currentMode !== 'MANUAL') {
        const next = setMode('MANUAL');
        addActivity('[SECURITY] Anomaly response forced MANUAL mode', 'system');
        actions.push(trackAction('set_mode_manual', {
          reason: 'error_spike',
          errors_per_minute: errors,
          mode: next,
        }));
      }
    }

    if (errors >= 10 && typeof stopAllAgents === 'function') {
      stopAllAgents();
      addActivity('[SECURITY] Anomaly response paused all agents', 'system');
      actions.push(trackAction('stop_all_agents', {
        reason: 'critical_error_spike',
        errors_per_minute: errors,
      }));
    }

    if (honeypotHits5m >= 3 && gatewayProtector && typeof gatewayProtector.setStrictMode === 'function') {
      gatewayProtector.setStrictMode(true, 'honeypot_hits');
      actions.push(trackAction('gateway_strict_mode', {
        reason: 'honeypot_activity',
        honeypot_hits_5m: honeypotHits5m,
      }));
    }

    return {
      actions,
      snapshot: {
        errors_per_minute: errors,
        honeypot_hits_5m: honeypotHits5m,
      },
    };
  }

  function status() {
    return {
      enabled: state.enabled,
      recent_actions: state.last_actions.slice(0, 20),
    };
  }

  function setEnabled(enabled) {
    state.enabled = Boolean(enabled);
    return state.enabled;
  }

  return {
    evaluate,
    status,
    setEnabled,
  };
}

module.exports = {
  createAnomalyResponder,
};
