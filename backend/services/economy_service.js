'use strict';
const fs = require('fs');
const path = require('path');

let _runtimeState = null;
let _stateDir = null;

function init(runtimeState, stateDir) {
  _runtimeState = runtimeState;
  _stateDir = stateDir;
}

const statePath = (...parts) => path.join(_stateDir, ...parts);

function readJsonSafe(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch { return fallback; }
}

function readJsonlSafe(file, limit = 500) {
  try {
    const lines = fs.readFileSync(file, 'utf8').trim().split('\n').filter(Boolean);
    return lines.slice(-limit).map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
  } catch { return []; }
}

function walletSnapshot() {
  const wallet = readJsonSafe(statePath('wallet_vault.json'), null);
  if (!wallet) {
    return {
      state: 'disabled',
      configured: false,
      balance: { currency: 'USD', available: 0, pending: 0 },
      external_compute_enabled: false,
    };
  }
  return {
    state: 'live',
    configured: true,
    label: wallet.label,
    address: wallet.address,
    created_at: wallet.created_at,
    balance: wallet.balance || { currency: 'USD', available: 0, pending: 0 },
    external_compute_enabled: wallet.external_compute_enabled === true,
  };
}

function buildEconomySnapshot() {
  const rs = _runtimeState;
  const llmCalls = readJsonlSafe(statePath('llm_calls.jsonl'), 2000);
  const tokenTotals = llmCalls.reduce((acc, call) => {
    const agent = call.agent || call.route || 'unknown';
    if (!acc.by_agent[agent]) acc.by_agent[agent] = { agent, calls: 0, tokens: 0, cost: 0 };
    const tokens = Number(call.tokens || call.total_tokens || 0);
    const cost = Number(call.cost || call.cost_usd || 0);
    acc.tokens += tokens;
    acc.cost += cost;
    acc.by_agent[agent].calls += 1;
    acc.by_agent[agent].tokens += tokens;
    acc.by_agent[agent].cost += cost;
    return acc;
  }, { tokens: 0, cost: 0, by_agent: {} });

  const value = Number(rs.valueGenerated || 0);
  const revenue = Number(rs.revenueCents || 0) / 100;
  const cost = Number(tokenTotals.cost || 0);
  const profit = revenue - cost;

  const summary = {
    state: rs.pipelineRuns.length || revenue || tokenTotals.tokens ? 'live' : 'empty',
    source: 'node_runtime_state',
    updated_at: new Date().toISOString(),
    revenue: { total: revenue, daily: revenue, currency: 'USD', value_generated: value },
    cost: { token_cost: cost, total_cost: cost, tokens: tokenTotals.tokens },
    profit,
    roi: cost > 0 ? profit / cost : 0,
    tasks: {
      executed: rs.tasksExecuted,
      successful: rs.successfulTasks,
      failed: rs.failedTasks,
    },
    wallet: walletSnapshot(),
  };

  const ledger = [
    ...rs.pipelineRuns.map((run) => ({
      id: run.id,
      type: 'pipeline_value',
      status: run.status,
      amount: Number(run.estimated_roi || 0),
      currency: 'USD',
      description: `${run.pipeline} pipeline estimated value`,
      created_at: run.executed_at,
    })),
    ...readJsonlSafe(statePath('wallet_audit.jsonl'), 200).map((entry, index) => ({
      id: entry.id || `wallet-audit-${index}`,
      type: entry.event || 'wallet_audit',
      status: 'recorded',
      amount: Number(entry.details?.amount || entry.amount || 0),
      currency: entry.details?.currency || entry.currency || 'USD',
      description: entry.event || 'Wallet audit event',
      created_at: entry.ts,
      details: entry.details || entry,
    })),
  ];

  const costs = Object.values(tokenTotals.by_agent)
    .sort((a, b) => b.cost - a.cost)
    .map((row) => ({ ...row, cost: Number(row.cost.toFixed(6)) }));

  const pipelines = Object.entries(rs.objectiveState || {}).map(([id, pipeline]) => ({
    id,
    ...pipeline,
    state: pipeline.active ? 'live' : 'empty',
    updated_at: pipeline.current_objective?.updated_at || pipeline.current_objective?.created_at || null,
  }));

  return { summary, ledger, costs, pipelines };
}

module.exports = { init, walletSnapshot, buildEconomySnapshot };
