'use strict';

/**
 * Execution API Routes — Phase 3.3 Pipeline Visualization
 *
 * Real-time 10-phase pipeline execution tracking:
 * - GET /api/execution/pipeline/:taskId — Fetch complete execution trace
 * - GET /api/execution/active — List all in-progress executions
 * - POST /api/execution/trace/:taskId — Detailed trace log for debugging
 * - WebSocket updates via broadcaster
 */

const express = require('express');
const fs = require('fs');
const path = require('path');

const PHASE_NAMES = [
  'retrieve_relevant_nodes',
  'build_context',
  'classify_decision',
  'call_llm',
  'validate_tasks',
  'execute_tasks',
  'format_response',
  'update_graph',
  'monitor_and_improve',
  'validate_pipeline_integrity',
];

function createExecutionRouter(opts = {}) {
  const router = express.Router();
  const pipelineTraces = opts.pipelineTraces || new Map();
  const broadcaster = opts.broadcaster || null;

  /**
   * GET /api/execution/pipeline/:taskId
   * Fetch the complete 10-phase execution trace for a task
   */
  router.get('/pipeline/:taskId', (req, res) => {
    try {
      const { taskId } = req.params;
      const tenantId = req.tenant?.id || 'default';

      const traceKey = `${tenantId}:${taskId}`;
      let trace = pipelineTraces.get(traceKey);

      if (!trace) {
        trace = loadTraceFromState(tenantId, taskId);
      }

      if (!trace) {
        trace = {
          taskId,
          tenantId,
          createdAt: new Date().toISOString(),
          phases: createEmptyPhases(),
        };
      }

      res.json({
        ok: true,
        data: trace,
      });
    } catch (err) {
      console.error('Error fetching pipeline trace:', err);
      res.status(500).json({
        ok: false,
        error: 'Failed to fetch pipeline trace',
        details: err.message,
      });
    }
  });

  /**
   * GET /api/execution/active
   * List all in-progress task executions with phase progress
   */
  router.get('/active', (req, res) => {
    try {
      const tenantId = req.tenant?.id || 'default';
      const active = [];

      for (const [key, trace] of pipelineTraces) {
        if (!key.startsWith(`${tenantId}:`)) continue;
        if (trace.status !== 'running') continue;

        const currentPhase = trace.phases.findIndex(p => p.status === 'running');
        const progress = currentPhase >= 0
          ? Math.round(((currentPhase + 1) / 10) * 100)
          : 0;

        active.push({
          taskId: trace.taskId,
          status: trace.status,
          startTime: trace.startTime,
          currentPhase: currentPhase + 1,
          currentPhaseName: currentPhase >= 0 ? trace.phases[currentPhase].name : null,
          progress,
          phases: trace.phases.map(p => ({
            phase: p.phase,
            name: p.name,
            status: p.status,
            duration_ms: p.duration_ms,
          })),
        });
      }

      res.json({
        ok: true,
        data: active,
      });
    } catch (err) {
      console.error('Error fetching active tasks:', err);
      res.status(500).json({
        ok: false,
        error: 'Failed to fetch active tasks',
        details: err.message,
      });
    }
  });

  /**
   * POST /api/execution/trace/:taskId
   * Get detailed trace logs for debugging a specific task
   */
  router.post('/trace/:taskId', (req, res) => {
    try {
      const { taskId } = req.params;
      const tenantId = req.tenant?.id || 'default';

      const traceKey = `${tenantId}:${taskId}`;
      const trace = pipelineTraces.get(traceKey);

      if (!trace) {
        return res.status(404).json({
          ok: false,
          error: 'Task not found',
        });
      }

      // Build detailed trace with metrics
      const detailed = {
        taskId: trace.taskId,
        tenantId: trace.tenantId,
        startTime: trace.startTime,
        endTime: trace.endTime,
        status: trace.status,
        totalDuration_ms: trace.endTime
          ? new Date(trace.endTime) - new Date(trace.startTime)
          : null,
        phases: trace.phases.map(p => ({
          phase: p.phase,
          name: p.name,
          status: p.status,
          startTime: p.startTime,
          endTime: p.endTime,
          duration_ms: p.duration_ms,
          input: p.input,
          output: p.output,
          error: p.error,
        })),
        metrics: buildMetrics(trace),
      };

      // Load historical traces from JSONL if available
      const historicalTraces = loadHistoricalTraces(tenantId, taskId);
      if (historicalTraces.length > 0) {
        detailed.history = historicalTraces;
      }

      res.json({
        ok: true,
        data: detailed,
      });
    } catch (err) {
      console.error('Error fetching trace details:', err);
      res.status(500).json({
        ok: false,
        error: 'Failed to fetch trace details',
        details: err.message,
      });
    }
  });

  /**
   * POST /api/execution/phase-update
   * Internal endpoint for orchestrator to report phase transitions
   * (Called by backend systems to update pipeline state)
   */
  router.post('/phase-update', (req, res) => {
    try {
      const { taskId, phase, status, duration_ms, input, output, error } = req.body || {};
      const tenantId = req.tenant?.id || 'default';

      if (!taskId || !phase || !status) {
        return res.status(400).json({
          ok: false,
          error: 'Missing required fields: taskId, phase, status',
        });
      }

      if (phase < 1 || phase > 10) {
        return res.status(400).json({
          ok: false,
          error: 'Invalid phase number (must be 1-10)',
        });
      }

      const traceKey = `${tenantId}:${taskId}`;
      let trace = pipelineTraces.get(traceKey);

      if (!trace) {
        trace = {
          taskId,
          tenantId,
          startTime: new Date().toISOString(),
          endTime: null,
          status: 'running',
          phases: createEmptyPhases(),
        };
        pipelineTraces.set(traceKey, trace);
      }

      const p = trace.phases[phase - 1];
      if (p) {
        if (status === 'running') {
          p.startTime = new Date().toISOString();
          p.status = 'running';
        } else if (status === 'done') {
          p.endTime = new Date().toISOString();
          p.status = 'done';
          p.output = output;
          if (p.startTime) {
            p.duration_ms = new Date(p.endTime) - new Date(p.startTime);
          }
        } else if (status === 'failed') {
          p.endTime = new Date().toISOString();
          p.status = 'failed';
          p.error = error;
          if (p.startTime) {
            p.duration_ms = new Date(p.endTime) - new Date(p.startTime);
          }
          trace.status = 'failed';
        }

        if (input !== undefined) {
          p.input = input;
        }
      }

      // Broadcast phase update
      if (broadcaster) {
        broadcaster.broadcast('execution:phase-update', {
          type: 'phase-update',
          taskId,
          tenantId,
          phase,
          phaseName: PHASE_NAMES[phase - 1],
          status,
          duration_ms,
          timestamp: new Date().toISOString(),
        });
      }

      res.json({
        ok: true,
        data: trace,
      });
    } catch (err) {
      console.error('Error updating phase:', err);
      res.status(500).json({
        ok: false,
        error: 'Failed to update phase',
        details: err.message,
      });
    }
  });

  return {
    router,
    pipelineTraces,
    createPhaseUpdate,
    recordPhaseStart,
    recordPhaseComplete,
    recordPhaseError,
  };
}

/**
 * Create empty phase objects for all 10 phases
 */
function createEmptyPhases() {
  return PHASE_NAMES.map((name, idx) => ({
    phase: idx + 1,
    name,
    status: 'pending',
    startTime: null,
    endTime: null,
    duration_ms: null,
    input: null,
    output: null,
    error: null,
  }));
}

/**
 * Create a phase update message for WebSocket
 */
function createPhaseUpdate(phase, status, data = {}) {
  return {
    phase,
    phaseName: PHASE_NAMES[phase - 1],
    status,
    startTime: data.startTime || null,
    endTime: data.endTime || null,
    duration_ms: data.duration_ms || 0,
    error: data.error || null,
  };
}

/**
 * Record phase start in trace
 */
function recordPhaseStart(pipelineTraces, tenantId, taskId, phaseNum) {
  const traceKey = `${tenantId}:${taskId}`;
  let trace = pipelineTraces.get(traceKey);

  if (!trace) {
    trace = {
      taskId,
      tenantId,
      startTime: new Date().toISOString(),
      endTime: null,
      status: 'running',
      phases: createEmptyPhases(),
    };
    pipelineTraces.set(traceKey, trace);
  }

  const phase = trace.phases[phaseNum - 1];
  if (phase) {
    phase.status = 'running';
    phase.startTime = new Date().toISOString();
  }

  return trace;
}

/**
 * Record phase completion
 */
function recordPhaseComplete(pipelineTraces, tenantId, taskId, phaseNum, output = null, duration_ms = 0) {
  const traceKey = `${tenantId}:${taskId}`;
  let trace = pipelineTraces.get(traceKey);

  if (trace) {
    const phase = trace.phases[phaseNum - 1];
    if (phase) {
      phase.status = 'done';
      phase.endTime = new Date().toISOString();
      phase.output = output;
      phase.duration_ms = duration_ms || (
        phase.startTime ? new Date(phase.endTime) - new Date(phase.startTime) : 0
      );
    }
  }

  return trace;
}

/**
 * Record phase error
 */
function recordPhaseError(pipelineTraces, tenantId, taskId, phaseNum, error, duration_ms = 0) {
  const traceKey = `${tenantId}:${taskId}`;
  let trace = pipelineTraces.get(traceKey);

  if (trace) {
    const phase = trace.phases[phaseNum - 1];
    if (phase) {
      phase.status = 'failed';
      phase.endTime = new Date().toISOString();
      phase.error = typeof error === 'string' ? error : error?.message || 'Unknown error';
      phase.duration_ms = duration_ms || (
        phase.startTime ? new Date(phase.endTime) - new Date(phase.startTime) : 0
      );
    }
    trace.status = 'failed';
  }

  return trace;
}

/**
 * Load trace from persistent state (JSONL file)
 */
function loadTraceFromState(tenantId, taskId) {
  try {
    const stateDir = path.resolve(
      process.env.STATE_DIR || path.join(process.env.HOME || '/tmp', '.ai-employee', 'state')
    );
    const tracesFile = path.join(stateDir, 'execution_traces.jsonl');

    if (fs.existsSync(tracesFile)) {
      const lines = fs.readFileSync(tracesFile, 'utf-8').split('\n').filter(Boolean);
      const phaseMap = new Map();

      // Reconstruct trace from JSONL entries
      for (const line of lines) {
        try {
          const entry = JSON.parse(line);
          if (entry.taskId === taskId && entry.tenantId === tenantId) {
            phaseMap.set(entry.phase, entry);
          }
        } catch (e) {
          // Skip malformed lines
        }
      }

      if (phaseMap.size > 0) {
        const phases = createEmptyPhases();
        for (const [phaseNum, entry] of phaseMap) {
          if (phaseNum >= 1 && phaseNum <= 10) {
            const p = phases[phaseNum - 1];
            p.status = entry.status;
            p.duration_ms = entry.duration_ms;
            p.error = entry.error;
            if (entry.timestamp) {
              p.endTime = entry.timestamp;
            }
          }
        }

        return {
          taskId,
          tenantId,
          createdAt: new Date().toISOString(),
          phases,
        };
      }
    }
  } catch (err) {
    console.error('Error loading trace from state:', err);
  }

  return null;
}

/**
 * Load historical trace entries from JSONL for a specific task
 */
function loadHistoricalTraces(tenantId, taskId, limit = 100) {
  try {
    const stateDir = path.resolve(
      process.env.STATE_DIR || path.join(process.env.HOME || '/tmp', '.ai-employee', 'state')
    );
    const tracesFile = path.join(stateDir, 'execution_traces.jsonl');

    if (fs.existsSync(tracesFile)) {
      const lines = fs.readFileSync(tracesFile, 'utf-8').split('\n').filter(Boolean);
      const traces = [];

      for (const line of lines) {
        try {
          const entry = JSON.parse(line);
          if (entry.taskId === taskId && entry.tenantId === tenantId) {
            traces.push(entry);
          }
        } catch (e) {
          // Skip malformed lines
        }
      }

      return traces.slice(-limit);
    }
  } catch (err) {
    console.error('Error loading historical traces:', err);
  }

  return [];
}

/**
 * Build metrics from trace phases
 */
function buildMetrics(trace) {
  if (!trace || !trace.phases) return {};

  const metrics = {
    totalPhases: 10,
    completedPhases: trace.phases.filter(p => p.status === 'done').length,
    failedPhases: trace.phases.filter(p => p.status === 'failed').length,
    totalDuration_ms: 0,
    averagePhaseTime_ms: 0,
    phaseTimes: {},
  };

  let totalTime = 0;
  for (const phase of trace.phases) {
    if (phase.duration_ms) {
      totalTime += phase.duration_ms;
      metrics.phaseTimes[phase.name] = phase.duration_ms;
    }
  }

  metrics.totalDuration_ms = totalTime;
  if (metrics.completedPhases > 0) {
    metrics.averagePhaseTime_ms = Math.round(totalTime / metrics.completedPhases);
  }

  return metrics;
}

module.exports = {
  createExecutionRouter,
  createEmptyPhases,
  createPhaseUpdate,
  recordPhaseStart,
  recordPhaseComplete,
  recordPhaseError,
};
