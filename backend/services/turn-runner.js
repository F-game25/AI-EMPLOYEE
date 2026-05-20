'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

const STATE_DIR = path.resolve(
  process.env.STATE_DIR
    || path.join(process.env.AI_EMPLOYEE_HOME || process.env.AI_HOME || path.join(os.homedir(), '.ai-employee'), 'state'),
);
const TURN_LOG = path.join(STATE_DIR, 'turns.jsonl');

function nowIso() {
  return new Date().toISOString();
}

function safeId(prefix) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function compactError(error) {
  if (!error) return null;
  if (typeof error === 'string') return error.slice(0, 1000);
  return String(error.message || error).slice(0, 1000);
}

function appendTurnLog(turn) {
  try {
    fs.mkdirSync(STATE_DIR, { recursive: true });
    fs.appendFileSync(TURN_LOG, JSON.stringify(turn) + '\n', 'utf8');
  } catch (_) {
    // Best effort only. Runtime responses must never depend on telemetry writes.
  }
}

function normalizeArtifact(item, source = 'turn') {
  if (!item || typeof item !== 'object') return null;
  const name = item.name || item.filename || (item.path ? path.basename(item.path) : null);
  return {
    id: item.id || item.artifact_id || (name ? `artifact:${name}` : safeId('artifact')),
    name: name || 'artifact',
    path: item.path || null,
    url: item.url || (name ? `/api/artifacts/${encodeURIComponent(name)}` : null),
    type: item.type || item.artifact_type || 'file',
    source: item.source || source,
    size: item.size || item.bytes || null,
    created_at: item.created_at || item.timestamp || nowIso(),
  };
}

function normalizeAction(step, index = 0) {
  if (!step || typeof step !== 'object') return null;
  const action = step.action || step.step || step.name || `step_${index + 1}`;
  const status = step.status || (step.success === false ? 'failed' : 'completed');
  const error = compactError(step.error);
  return {
    id: step.id || step.task_id || `${index + 1}`,
    action,
    label: step.description || step.label || action,
    status,
    started_at: step.started_at || step.startedAt || null,
    completed_at: step.completed_at || step.finished_at || step.completedAt || null,
    output: step.output || null,
    error,
    proof: step.proof || null,
  };
}

function proofFromMemory(memoryTrace) {
  if (!memoryTrace) return [];
  const proof = [{
    type: 'memory_trace',
    label: 'Memory context checked',
    status: memoryTrace.degraded ? 'degraded' : 'live',
    trace_id: memoryTrace.trace_id || null,
    confidence: memoryTrace.confidence || 0,
  }];
  for (const citation of (memoryTrace.citations || []).slice(0, 6)) {
    proof.push({
      type: 'citation',
      label: citation.title || citation.source || citation.url || 'Memory citation',
      url: citation.url || null,
      source: citation.source || null,
    });
  }
  return proof;
}

function proofFromExecution(result) {
  const proof = [];
  if (Array.isArray(result.proof)) proof.push(...result.proof);
  for (const artifact of result.attachments || result.artifacts || []) {
    const normalized = normalizeArtifact(artifact, 'execution-engine');
    if (normalized) {
      proof.push({
        type: 'artifact',
        label: normalized.name,
        url: normalized.url,
        path: normalized.path,
        artifact_id: normalized.id,
      });
    }
  }
  for (const action of result.step_actions || []) {
    proof.push({
      type: 'tool_result',
      label: action.action || 'Tool action',
      status: action.status || 'completed',
    });
  }
  if (typeof result.steps === 'number') {
    proof.push({
      type: 'execution_trace',
      label: `${result.steps} execution step${result.steps === 1 ? '' : 's'} completed`,
      status: result.success === false ? 'failed' : 'completed',
    });
  }
  return proof;
}

function formatTeammateReply({ input, rawReply, source, proof, errors, degraded }) {
  const cleanReply = String(rawReply || '').trim();
  const blocked = errors && errors.length > 0;
  const proofLine = proof && proof.length
    ? proof.slice(0, 4).map((p) => p.label || p.type).filter(Boolean).join(', ')
    : 'No durable artifact was produced for this turn.';
  const result = cleanReply || (blocked ? 'I could not complete the request.' : 'The request completed.');
  return [
    `I understood: ${String(input || '').slice(0, 240)}`,
    `I did: ${source || 'system'}${degraded ? ' (degraded)' : ''}`,
    `Result:\n${result}`,
    `Proof: ${proofLine}`,
    blocked ? `Blocked by: ${errors.map((e) => e.message || e).join('; ')}` : null,
  ].filter(Boolean).join('\n\n');
}

function withTimeout(promise, timeoutMs) {
  let timer = null;
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve(null), timeoutMs);
    if (typeof timer.unref === 'function') timer.unref();
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

function createTurnRunner(deps) {
  const broadcast = (event, data) => {
    try {
      if (deps.broadcaster && typeof deps.broadcaster.broadcast === 'function') {
        deps.broadcaster.broadcast(event, data);
      }
    } catch (_) {}
  };

  async function runTurn(options = {}) {
    const input = String(options.message || options.task || '').trim();
    if (!input) throw new Error('message required');

    const turnId = options.turnId || safeId('turn');
    const userId = options.userId || 'user:default';
    const tenantId = options.tenantId || 'default';
    const kind = options.kind || 'chat';
    const labels = Array.from(new Set([kind, options.source || 'unknown', ...(options.labels || [])]));
    const actions = [];
    const artifacts = [];
    const proof = [];
    const approvals = [];
    const errors = [];
    let degraded = false;
    let source = 'unhandled';
    let assistantReply = '';
    let pyPayload = null;
    let memoryTrace = null;

    const run = deps.createWorkflowRun({
      name: kind === 'task' ? 'Task Workflow' : 'Chat Workflow',
      source: options.source || kind,
      goal: input,
    });

    const queued = deps.orchestrator.submitTask(input, {
      userId,
      workflow: { runId: run.run_id, parentTaskId: null },
      labels,
      memory: null,
    });
    deps.attachWorkflowNode({ runId: run.run_id, queued, taskName: input, parentTaskId: null });
    deps.addActivity(`[TURN] ${turnId} submitted: ${input}`, 'task');

    broadcast('turn:started', {
      turn_id: turnId,
      task_id: queued.taskId,
      workflow_run: run.run_id,
      user_id: userId,
      tenant_id: tenantId,
      input,
      kind,
      status: 'running',
      ts: Date.now(),
    });
    broadcast('orchestrator:queued', { ...queued, turn_id: turnId });

    try {
      broadcast('turn:thinking', { turn_id: turnId, task_id: queued.taskId, message: 'Retrieving memory context' });
      memoryTrace = await deps.collectHybridMemoryContext(input, {
        userId,
        sessionId: run.run_id,
        taskId: queued.taskId,
        mode: kind === 'task' ? 'main_ai_task' : 'main_ai_chat',
        maxTokens: 1200,
      });
      if (memoryTrace) {
        proof.push(...proofFromMemory(memoryTrace));
        actions.push({
          id: 'memory',
          action: 'memory_context',
          label: 'Memory context retrieval',
          status: memoryTrace.degraded ? 'degraded' : 'completed',
          proof: { trace_id: memoryTrace.trace_id, confidence: memoryTrace.confidence },
        });
        deps.appendDecision(run, {
          ts: nowIso(),
          task_id: queued.taskId,
          type: 'memory_router_preflight',
          summary: `Routes ${Array.isArray(memoryTrace.routes) ? memoryTrace.routes.map((route) => route.id).join(', ') : 'none'} · confidence ${memoryTrace.confidence ?? 0}`,
          trace_id: memoryTrace.trace_id,
        });
        broadcast('memory:router:trace', {
          trace_id: memoryTrace.trace_id,
          task_id: queued.taskId,
          routes: memoryTrace.routes,
          confidence: memoryTrace.confidence,
          degraded: memoryTrace.degraded,
        });
      }

      if (kind === 'task' && await deps.isPythonBackendUp()) {
        broadcast('action:started', { turn_id: turnId, task_id: queued.taskId, action: 'agent_controller' });
        try {
          pyPayload = await deps.requestPythonJSON('/api/tasks/run', 'POST', {
            task: input,
            user_id: userId,
            workflow_run: run.run_id,
            memory_context: deps.compactMemoryTraceForModel(memoryTrace),
          }, {
            headers: options.authHeader ? { Authorization: options.authHeader } : {},
            timeoutMs: 30000,
          });
          if (pyPayload && pyPayload.ok) {
            source = 'agent_controller';
            assistantReply = `AgentController completed ${Array.isArray(pyPayload.tasks) ? pyPayload.tasks.length : 0} task(s).`;
            for (const task of pyPayload.tasks || []) {
              const action = normalizeAction({
                id: task.task_id,
                action: task.skill,
                status: task.status,
                output: task.output,
                error: task.error,
              }, actions.length);
              if (action) actions.push(action);
            }
            proof.push({
              type: 'agent_controller_result',
              label: `Performance ${pyPayload.performance_score ?? 'n/a'} / success ${pyPayload.success_rate ?? 'n/a'}`,
              status: 'completed',
            });
          } else {
            degraded = true;
            errors.push({ stage: 'agent_controller', message: `Python returned ${pyPayload?._http_status || 'non-ok'}` });
          }
        } catch (error) {
          degraded = true;
          errors.push({ stage: 'agent_controller', message: compactError(error) });
        }
        broadcast('action:completed', { turn_id: turnId, task_id: queued.taskId, action: 'agent_controller', status: source === 'agent_controller' ? 'completed' : 'failed' });
      }

      if (!assistantReply) {
        broadcast('action:started', { turn_id: turnId, task_id: queued.taskId, action: 'real_execution_engine' });
        const execResult = await withTimeout(deps.runPythonExecution(input), options.executionTimeoutMs || 120000);
        if (execResult && execResult.is_goal && execResult.reply) {
          source = 'execution-engine';
          assistantReply = execResult.reply;
          for (const item of execResult.attachments || []) {
            const artifact = normalizeArtifact(item, 'execution-engine');
            if (artifact) artifacts.push(artifact);
          }
          for (const step of execResult.step_actions || []) {
            const action = normalizeAction(step, actions.length);
            if (action) actions.push(action);
          }
          proof.push(...proofFromExecution(execResult));
          degraded = degraded || execResult.success === false;
        }
        broadcast('action:completed', { turn_id: turnId, task_id: queued.taskId, action: 'real_execution_engine', status: assistantReply ? 'completed' : 'skipped' });
      }

      if (!assistantReply && await deps.isPythonBackendUp()) {
        broadcast('action:started', { turn_id: turnId, task_id: queued.taskId, action: 'python_llm' });
        try {
          pyPayload = await deps.requestPythonChatPayload(input, options.modelRoute, userId, memoryTrace);
          const pyReply = pyPayload && (pyPayload.response || pyPayload.reply);
          if (pyReply) {
            source = 'python-llm';
            assistantReply = deps.applyStructuredFormat(pyReply, 'AI Employee');
            for (const item of pyPayload.artifacts || []) {
              const artifact = normalizeArtifact(item, 'python-llm');
              if (artifact) artifacts.push(artifact);
            }
            if (pyPayload.proof && Array.isArray(pyPayload.proof)) proof.push(...pyPayload.proof);
            if (pyPayload.trace_id) proof.push({ type: 'trace', label: `Trace ${pyPayload.trace_id}`, trace_id: pyPayload.trace_id });
            degraded = degraded || pyPayload.degraded === true;
          }
        } catch (error) {
          degraded = true;
          errors.push({ stage: 'python_llm', message: compactError(error) });
        }
        broadcast('action:completed', { turn_id: turnId, task_id: queued.taskId, action: 'python_llm', status: assistantReply ? 'completed' : 'failed' });
      }

      if (!assistantReply) {
        try {
          const ollamaReply = await deps.requestOllamaChat(input, memoryTrace);
          if (ollamaReply) {
            source = 'ollama';
            assistantReply = deps.applyStructuredFormat(ollamaReply, 'Ollama');
            // A real local-LLM answer is not degraded — only the keyword node-fallback is.
            proof.push({ type: 'local_llm', label: 'Answered locally via Ollama', status: 'completed' });
          }
        } catch (error) {
          errors.push({ stage: 'ollama', message: compactError(error) });
        }
      }

      if (!assistantReply) {
        source = 'node-fallback';
        degraded = true;
        assistantReply = deps.buildLocalFallbackReply(input, queued);
        proof.push({ type: 'fallback', label: 'Local fallback response; no external execution proof', status: 'fallback' });
      }
    } catch (error) {
      source = 'turn-runner';
      degraded = true;
      errors.push({ stage: 'turn_runner', message: compactError(error) });
      assistantReply = deps.buildLocalFallbackReply(input, queued);
    }

    const status = errors.length && !assistantReply ? 'failed' : 'completed';
    const proofReady = proof.length > 0 || artifacts.length > 0;
    const teammateReply = formatTeammateReply({
      input,
      rawReply: assistantReply,
      source,
      proof: [...proof, ...artifacts.map((a) => ({ type: 'artifact', label: a.name, url: a.url }))],
      errors,
      degraded,
    });

    const turn = {
      ok: status !== 'failed',
      turn_id: turnId,
      task_id: queued.taskId,
      taskId: queued.taskId,
      workflow_run: run.run_id,
      user_id: userId,
      tenant_id: tenantId,
      input,
      intent: queued.subsystem || kind,
      status,
      assistant_reply: teammateReply,
      reply: teammateReply,
      content: teammateReply,
      response: teammateReply,
      raw_reply: assistantReply,
      actions,
      artifacts,
      attachments: artifacts,
      proof,
      approvals,
      degraded,
      errors,
      trace_id: memoryTrace?.trace_id || pyPayload?.trace_id || null,
      source,
      memory_router: memoryTrace ? {
        trace_id: memoryTrace.trace_id,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      } : null,
      created_at: nowIso(),
    };

    appendTurnLog(turn);
    if (proofReady) broadcast('proof:ready', turn);
    for (const artifact of artifacts) broadcast('artifact:created', { turn_id: turnId, task_id: queued.taskId, artifact });
    broadcast(status === 'failed' ? 'turn:failed' : 'turn:completed', turn);
    broadcast('orchestrator:message', {
      turn_id: turnId,
      taskId: queued.taskId,
      message: teammateReply,
      proof,
      artifacts,
      actions,
      degraded,
      source,
      subsystem: queued.subsystem || 'orchestrator',
      timestamp: nowIso(),
    });

    return turn;
  }

  return { runTurn };
}

module.exports = { createTurnRunner };
