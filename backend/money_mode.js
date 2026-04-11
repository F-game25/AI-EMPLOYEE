'use strict';

const TEMPLATE_LIBRARY = {
  acquisition: {
    name: 'Enterprise Acquisition Engine',
    objective: 'Increase qualified pipeline with higher intent leads',
    kpis: ['qualified_leads', 'cost_per_lead', 'meeting_rate'],
    cadence: ['collect_signals', 'score_accounts', 'launch_outreach'],
  },
  conversion: {
    name: 'Enterprise Conversion Accelerator',
    objective: 'Move active opportunities to revenue faster',
    kpis: ['response_rate', 'conversion_rate', 'velocity_days'],
    cadence: ['segment_opportunities', 'personalize_offer', 'close_follow_up'],
  },
  retention: {
    name: 'Enterprise Expansion & Retention Loop',
    objective: 'Protect and expand existing customer revenue',
    kpis: ['retention_rate', 'upsell_rate', 'customer_health'],
    cadence: ['detect_risk', 'trigger_playbook', 'expand_account'],
  },
};
const CONFIDENCE_MIN = 0.2;
const CONFIDENCE_MAX = 0.97;
const CONFIDENCE_BASE = 0.55;
const CONFIDENCE_PRESSURE_WEIGHT = 0.05;

function _firstMatch(message, patterns, fallback) {
  const msg = String(message || '').toLowerCase();
  const found = Object.entries(patterns).find(([, rx]) => rx.test(msg));
  return found ? found[0] : fallback;
}

function classifyMoneyIntent(message, subsystem = 'general') {
  const explicit = _firstMatch(message, {
    conversion: /close|deal|proposal|contract|convert|revenue|roi|opportunit/,
    retention: /retention|renew|churn|upsell|expand|health|customer/,
    acquisition: /lead|prospect|pipeline|outreach|demand|traffic|audience/,
  }, null);
  if (explicit) return explicit;
  if (subsystem === 'doctor') return 'retention';
  if (subsystem === 'memory') return 'acquisition';
  return 'conversion';
}

function buildMoneyTemplate({ message, subsystem, mode, runningAgents, totalAgents }) {
  const intent = classifyMoneyIntent(message, subsystem);
  const base = TEMPLATE_LIBRARY[intent];
  const pressure = Math.max(0, (Number(totalAgents) || 1) - (Number(runningAgents) || 0));
  const confidence = Math.max(
    CONFIDENCE_MIN,
    Math.min(CONFIDENCE_MAX, CONFIDENCE_BASE + pressure * CONFIDENCE_PRESSURE_WEIGHT),
  );
  return {
    enabled: mode === 'MONEYMODE',
    intent,
    template: base.name,
    objective: base.objective,
    kpis: base.kpis,
    cadence: base.cadence,
    adjustments: {
      subsystem_focus: subsystem || 'general',
      execution_pressure: pressure,
      confidence: Math.round(confidence * 1000) / 1000,
    },
  };
}

function buildThinkingSummary(mode, template, robotSignal) {
  const location = robotSignal && robotSignal.location ? robotSignal.location : 'idle';
  const robot = robotSignal && robotSignal.agentName ? robotSignal.agentName : 'No active robot';
  if (mode === 'MONEYMODE' && template) {
    return `${robot} at ${location} executing ${template.intent} plan`;
  }
  return `${robot} at ${location} in ${mode} mode`;
}

module.exports = {
  buildMoneyTemplate,
  buildThinkingSummary,
};
