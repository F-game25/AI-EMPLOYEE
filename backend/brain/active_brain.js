'use strict';

const MAX_RECENT = 40;
const MAX_FAILURES = 50;

function nowIso() {
  return new Date().toISOString();
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function toKey(value, fallback = 'general') {
  return String(value || fallback).toLowerCase().trim() || fallback;
}

function messageIntent(message) {
  const text = String(message || '').toLowerCase();
  if (/(lead|prospect|outreach|pipeline|conversion)/.test(text)) return 'lead_generation';
  if (/(content|post|social|article|video|campaign)/.test(text)) return 'content_growth';
  if (/(report|metric|analytics|dashboard|insight)/.test(text)) return 'analytics';
  if (/(memory|learn|brain|strategy|decision)/.test(text)) return 'cognition';
  return 'general';
}

function normalizeLatencyMs(startedAt, finishedAt, fallback = 0) {
  if (!startedAt || !finishedAt) return Math.max(0, Number(fallback) || 0);
  const start = Date.parse(startedAt);
  const end = Date.parse(finishedAt);
  if (Number.isNaN(start) || Number.isNaN(end)) return Math.max(0, Number(fallback) || 0);
  return Math.max(0, end - start);
}

const state = {
  taskPatterns: new Map(),
  strategies: new Map(),
  failedAttempts: [],
  userPreferences: new Map(),
  performance: {
    total: 0,
    success: 0,
    failed: 0,
    avgLatencyMs: 0,
    avgConfidence: 0,
  },
  recentImprovements: [],
  decisionHistory: [],
  planIndex: new Map(),
};

function getPattern(intent) {
  const key = toKey(intent);
  if (!state.taskPatterns.has(key)) {
    state.taskPatterns.set(key, {
      intent: key,
      runs: 0,
      success: 0,
      failed: 0,
      subsystems: {},
      latest: nowIso(),
    });
  }
  return state.taskPatterns.get(key);
}

function getStrategy(intent, strategyName) {
  const intentKey = toKey(intent);
  const strategyKey = toKey(strategyName, 'balanced_execution');
  if (!state.strategies.has(intentKey)) {
    state.strategies.set(intentKey, new Map());
  }
  const byIntent = state.strategies.get(intentKey);
  if (!byIntent.has(strategyKey)) {
    byIntent.set(strategyKey, {
      strategy: strategyKey,
      intent: intentKey,
      runs: 0,
      success: 0,
      failed: 0,
      avgLatencyMs: 0,
      avgConfidence: 0,
      lastUsedAt: null,
    });
  }
  return byIntent.get(strategyKey);
}

function candidateStrategies(intent) {
  const intentKey = toKey(intent);
  const defaults = {
    lead_generation: ['lead_prioritize_then_route', 'conversion_fast_path'],
    content_growth: ['content_research_then_publish', 'audience_first_strategy'],
    analytics: ['signal_then_summary', 'kpi_anomaly_first'],
    cognition: ['memory_first_then_execute', 'confidence_gated_execution'],
    general: ['balanced_execution', 'safety_first_iteration'],
  };
  const existing = state.strategies.get(intentKey);
  if (!existing || existing.size === 0) return defaults[intentKey] || defaults.general;
  return Array.from(existing.values())
    .sort((a, b) => {
      const aRate = a.runs ? a.success / a.runs : 0;
      const bRate = b.runs ? b.success / b.runs : 0;
      if (bRate !== aRate) return bRate - aRate;
      return (a.avgLatencyMs || 0) - (b.avgLatencyMs || 0);
    })
    .map((s) => s.strategy)
    .slice(0, 3);
}

function chooseSubsystem(intent, preferredSubsystem) {
  const pattern = getPattern(intent);
  const ranked = Object.entries(pattern.subsystems || {})
    .map(([subsystem, stats]) => ({
      subsystem,
      successRate: stats.runs ? stats.success / stats.runs : 0,
      runs: stats.runs || 0,
    }))
    .sort((a, b) => {
      if (b.successRate !== a.successRate) return b.successRate - a.successRate;
      return b.runs - a.runs;
    });
  if (preferredSubsystem && ranked.length === 0) return preferredSubsystem;
  if (preferredSubsystem && ranked.length > 0 && ranked[0].successRate < 0.6) return preferredSubsystem;
  return ranked[0] ? ranked[0].subsystem : (preferredSubsystem || 'general');
}

function updatePreference(userId, message, strategyName) {
  const userKey = toKey(userId, 'user:default');
  const text = String(message || '').toLowerCase();
  if (!state.userPreferences.has(userKey)) {
    state.userPreferences.set(userKey, {
      userId: userKey,
      prefersDetail: 0,
      prefersSpeed: 0,
      preferredStrategies: {},
      updatedAt: nowIso(),
    });
  }
  const pref = state.userPreferences.get(userKey);
  if (/(detail|deep|thorough|explain|why)/.test(text)) pref.prefersDetail = clamp(pref.prefersDetail + 0.1, 0, 1);
  if (/(fast|quick|short|brief|now)/.test(text)) pref.prefersSpeed = clamp(pref.prefersSpeed + 0.1, 0, 1);
  const key = toKey(strategyName, 'balanced_execution');
  pref.preferredStrategies[key] = (pref.preferredStrategies[key] || 0) + 1;
  pref.updatedAt = nowIso();
  return pref;
}

function consult({
  taskId,
  message,
  subsystemHint,
  userId = 'user:default',
  executionPath = 'task->strategy->agent->action->result',
}) {
  const intent = messageIntent(message);
  const strategyOptions = candidateStrategies(intent);
  const chosenStrategy = strategyOptions[0] || 'balanced_execution';
  const chosenSubsystem = chooseSubsystem(intent, subsystemHint);
  const confidenceBase = 0.55;
  const pattern = getPattern(intent);
  const priorRuns = pattern.runs || 0;
  const historicalConfidence = priorRuns ? (pattern.success / priorRuns) : 0.5;
  const confidence = clamp((confidenceBase + historicalConfidence) / 2, 0.35, 0.97);
  const pref = updatePreference(userId, message, chosenStrategy);
  const reason = [
    `intent=${intent}`,
    `strategy=${chosenStrategy}`,
    `subsystem=${chosenSubsystem}`,
    `history_runs=${priorRuns}`,
    `user_detail_pref=${pref.prefersDetail.toFixed(2)}`,
    `user_speed_pref=${pref.prefersSpeed.toFixed(2)}`,
  ].join(' | ');

  const plan = {
    taskId,
    intent,
    subsystem: chosenSubsystem,
    strategy: chosenStrategy,
    alternatives: strategyOptions,
    confidence: Number(confidence.toFixed(3)),
    reasoning: reason,
    brain_assisted: true,
    execution_flow: executionPath,
    plannedAt: nowIso(),
  };

  state.planIndex.set(taskId, plan);
  state.decisionHistory.unshift(plan);
  state.decisionHistory = state.decisionHistory.slice(0, MAX_RECENT);
  return plan;
}

function _updateRunningAverage(currentAvg, currentCount, value) {
  if (currentCount <= 1) return value;
  return ((currentAvg * (currentCount - 1)) + value) / currentCount;
}

function feedback({
  taskId,
  status,
  subsystem,
  durationMs,
  userId = 'user:default',
  reward = null,
  notes = '',
}) {
  const plan = state.planIndex.get(taskId);
  if (!plan) return null;

  const intent = toKey(plan.intent);
  const strategy = toKey(plan.strategy);
  const pattern = getPattern(intent);
  pattern.runs += 1;
  pattern.latest = nowIso();
  if (!pattern.subsystems[subsystem]) {
    pattern.subsystems[subsystem] = { runs: 0, success: 0, failed: 0 };
  }
  pattern.subsystems[subsystem].runs += 1;

  const strategyStats = getStrategy(intent, strategy);
  strategyStats.runs += 1;
  strategyStats.lastUsedAt = nowIso();
  strategyStats.avgLatencyMs = _updateRunningAverage(
    strategyStats.avgLatencyMs || 0,
    strategyStats.runs,
    Number(durationMs) || 0,
  );
  strategyStats.avgConfidence = _updateRunningAverage(
    strategyStats.avgConfidence || 0,
    strategyStats.runs,
    Number(plan.confidence) || 0,
  );

  state.performance.total += 1;
  state.performance.avgLatencyMs = _updateRunningAverage(
    state.performance.avgLatencyMs || 0,
    state.performance.total,
    Number(durationMs) || 0,
  );
  state.performance.avgConfidence = _updateRunningAverage(
    state.performance.avgConfidence || 0,
    state.performance.total,
    Number(plan.confidence) || 0,
  );

  if (status === 'success') {
    pattern.success += 1;
    pattern.subsystems[subsystem].success += 1;
    strategyStats.success += 1;
    state.performance.success += 1;
    state.recentImprovements.unshift({
      ts: nowIso(),
      task_id: taskId,
      intent,
      strategy,
      subsystem,
      improvement: 'Strategy produced a successful execution path.',
      confidence: plan.confidence,
    });
    state.recentImprovements = state.recentImprovements.slice(0, MAX_RECENT);
  } else {
    pattern.failed += 1;
    pattern.subsystems[subsystem].failed += 1;
    strategyStats.failed += 1;
    state.performance.failed += 1;
    state.failedAttempts.unshift({
      ts: nowIso(),
      task_id: taskId,
      intent,
      strategy,
      subsystem,
      notes: notes || 'Execution failed',
      reward: reward !== null ? reward : -1,
    });
    state.failedAttempts = state.failedAttempts.slice(0, MAX_FAILURES);
  }

  updatePreference(userId, notes || '', strategy);
  state.planIndex.delete(taskId);
  return plan;
}

function taskInfluence(taskId) {
  return state.planIndex.get(taskId) || null;
}

function rebindPlan(oldTaskId, newTaskId) {
  const existing = state.planIndex.get(oldTaskId);
  if (!existing) return null;
  state.planIndex.delete(oldTaskId);
  const updated = { ...existing, taskId: newTaskId };
  state.planIndex.set(newTaskId, updated);
  return updated;
}

function _topStrategies(limit = 6) {
  const rows = [];
  state.strategies.forEach((byIntent) => {
    byIntent.forEach((entry) => rows.push(entry));
  });
  return rows
    .map((row) => ({
      strategy: row.strategy,
      intent: row.intent,
      runs: row.runs,
      success_rate: row.runs ? Number((row.success / row.runs).toFixed(3)) : 0,
      avg_latency_ms: Math.round(row.avgLatencyMs || 0),
      confidence: Number((row.avgConfidence || 0).toFixed(3)),
      last_used_at: row.lastUsedAt,
    }))
    .sort((a, b) => {
      if (b.success_rate !== a.success_rate) return b.success_rate - a.success_rate;
      return b.runs - a.runs;
    })
    .slice(0, limit);
}

function _topPatterns(limit = 6) {
  return Array.from(state.taskPatterns.values())
    .map((p) => ({
      intent: p.intent,
      runs: p.runs,
      success_rate: p.runs ? Number((p.success / p.runs).toFixed(3)) : 0,
      failed: p.failed,
      latest: p.latest,
    }))
    .sort((a, b) => b.runs - a.runs)
    .slice(0, limit);
}

function insights() {
  const total = state.performance.total || 0;
  return {
    active: true,
    updated_at: nowIso(),
    learned_strategies: _topStrategies(8),
    task_patterns: _topPatterns(8),
    failed_attempts: state.failedAttempts.slice(0, 10),
    user_preferences: Array.from(state.userPreferences.values()).slice(0, 8),
    recent_improvements: state.recentImprovements.slice(0, 10),
    performance_metrics: {
      total_tasks: total,
      success_rate: total ? Number((state.performance.success / total).toFixed(3)) : 0,
      failure_rate: total ? Number((state.performance.failed / total).toFixed(3)) : 0,
      avg_latency_ms: Math.round(state.performance.avgLatencyMs || 0),
      avg_confidence: Number((state.performance.avgConfidence || 0).toFixed(3)),
    },
    decisions: state.decisionHistory.slice(0, 12),
  };
}

module.exports = {
  consult,
  feedback,
  insights,
  taskInfluence,
  rebindPlan,
  normalizeLatencyMs,
};
