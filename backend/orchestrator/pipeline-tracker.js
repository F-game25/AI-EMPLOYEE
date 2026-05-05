'use strict';

/**
 * Pipeline Tracker — Real-time 10-phase execution tracking
 *
 * Tracks execution of the unified pipeline across all 10 phases:
 * 1. retrieve_relevant_nodes
 * 2. build_context
 * 3. classify_decision
 * 4. call_llm
 * 5. validate_tasks
 * 6. execute_tasks
 * 7. format_response
 * 8. update_graph
 * 9. monitor_and_improve
 * 10. validate_pipeline_integrity
 */

const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');

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

class PipelineTracker extends EventEmitter {
  constructor(opts = {}) {
    super();
    this.traces = new Map(); // tenantId:taskId → execution trace
    this.tracesFile = opts.tracesFile || path.join(
      process.env.HOME || '/tmp',
      '.ai-employee',
      'state',
      'execution_traces.jsonl'
    );
    this.broadcaster = opts.broadcaster || null;
  }

  /**
   * Start tracking a new task
   * @param {string} taskId - Task identifier (UUID)
   * @param {string} tenantId - Tenant identifier (default: 'default')
   * @returns {object} Initial execution trace
   */
  startTask(taskId, tenantId = 'default') {
    const traceKey = `${tenantId}:${taskId}`;
    const trace = {
      taskId,
      tenantId,
      startTime: new Date().toISOString(),
      endTime: null,
      status: 'running',
      phases: PHASE_NAMES.map((name, idx) => ({
        phase: idx + 1,
        name,
        status: 'pending',
        startTime: null,
        endTime: null,
        duration_ms: null,
        input: null,
        output: null,
        error: null,
      })),
    };
    this.traces.set(traceKey, trace);
    return trace;
  }

  /**
   * Mark phase start
   */
  markPhaseStart(taskId, phaseNum, tenantId = 'default') {
    const traceKey = `${tenantId}:${taskId}`;
    const trace = this.traces.get(traceKey);
    if (!trace) return null;

    const phase = trace.phases[phaseNum - 1];
    if (phase) {
      phase.status = 'running';
      phase.startTime = new Date().toISOString();
    }

    this.emit('phase-started', { taskId, tenantId, phase: phaseNum });
    this.broadcaster?.broadcast('execution:phase-started', {
      type: 'phase-started',
      taskId,
      tenantId,
      phase: phaseNum,
      phaseName: PHASE_NAMES[phaseNum - 1],
      timestamp: phase.startTime,
    });

    return trace;
  }

  /**
   * Mark phase complete with output
   */
  markPhaseComplete(taskId, phaseNum, output = null, tenantId = 'default') {
    const traceKey = `${tenantId}:${taskId}`;
    const trace = this.traces.get(traceKey);
    if (!trace) return null;

    const phase = trace.phases[phaseNum - 1];
    if (phase) {
      phase.endTime = new Date().toISOString();
      phase.status = 'done';
      phase.output = output;
      if (phase.startTime) {
        phase.duration_ms = new Date(phase.endTime) - new Date(phase.startTime);
      }
      this.appendTrace(trace, phaseNum, 'done');
    }

    this.emit('phase-completed', { taskId, tenantId, phase: phaseNum, output });
    this.broadcaster?.broadcast('execution:phase-completed', {
      type: 'phase-completed',
      taskId,
      tenantId,
      phase: phaseNum,
      phaseName: PHASE_NAMES[phaseNum - 1],
      duration_ms: phase.duration_ms,
      timestamp: phase.endTime,
    });

    return trace;
  }

  /**
   * Mark phase failed with error
   */
  markPhaseFailed(taskId, phaseNum, error = null, tenantId = 'default') {
    const traceKey = `${tenantId}:${taskId}`;
    const trace = this.traces.get(traceKey);
    if (!trace) return null;

    const phase = trace.phases[phaseNum - 1];
    if (phase) {
      phase.endTime = new Date().toISOString();
      phase.status = 'failed';
      phase.error = typeof error === 'string' ? error : error?.message || 'Unknown error';
      if (phase.startTime) {
        phase.duration_ms = new Date(phase.endTime) - new Date(phase.startTime);
      }
      trace.status = 'failed';
      this.appendTrace(trace, phaseNum, 'failed', phase.error);
    }

    this.emit('phase-failed', { taskId, tenantId, phase: phaseNum, error: phase.error });
    this.broadcaster?.broadcast('execution:phase-failed', {
      type: 'phase-failed',
      taskId,
      tenantId,
      phase: phaseNum,
      phaseName: PHASE_NAMES[phaseNum - 1],
      error: phase.error,
      duration_ms: phase.duration_ms,
      timestamp: phase.endTime,
    });

    return trace;
  }

  /**
   * Get complete execution trace for a task
   */
  getTaskPipeline(taskId, tenantId = 'default') {
    const traceKey = `${tenantId}:${taskId}`;
    return this.traces.get(traceKey);
  }

  /**
   * Get all active task pipelines
   */
  getActivePipelines(tenantId = 'default') {
    const result = [];
    for (const [key, trace] of this.traces) {
      if (key.startsWith(`${tenantId}:`) && trace.status === 'running') {
        result.push(trace);
      }
    }
    return result;
  }

  /**
   * Mark task complete
   */
  completeTask(taskId, tenantId = 'default') {
    const traceKey = `${tenantId}:${taskId}`;
    const trace = this.traces.get(traceKey);
    if (trace) {
      trace.endTime = new Date().toISOString();
      trace.status = 'completed';
    }
    return trace;
  }

  /**
   * Append trace to JSONL file (append-only)
   */
  appendTrace(trace, phaseNum, status, error = null) {
    try {
      const dir = path.dirname(this.tracesFile);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }

      const phase = trace.phases[phaseNum - 1];
      const entry = {
        timestamp: new Date().toISOString(),
        taskId: trace.taskId,
        tenantId: trace.tenantId,
        phase: phaseNum,
        phaseName: PHASE_NAMES[phaseNum - 1],
        status,
        duration_ms: phase?.duration_ms || null,
        input_summary: phase?.input ? JSON.stringify(phase.input).slice(0, 100) : null,
        output_summary: phase?.output ? JSON.stringify(phase.output).slice(0, 100) : null,
        error: error || null,
      };

      fs.appendFileSync(this.tracesFile, JSON.stringify(entry) + '\n', 'utf8');
    } catch (err) {
      console.error('Failed to append trace:', err);
    }
  }

  /**
   * Clean up old traces from memory (keep last 1000)
   */
  cleanup() {
    if (this.traces.size > 1000) {
      const keys = Array.from(this.traces.keys());
      const toDelete = keys.slice(0, Math.floor(keys.length / 2));
      toDelete.forEach(k => this.traces.delete(k));
    }
  }
}

module.exports = PipelineTracker;
