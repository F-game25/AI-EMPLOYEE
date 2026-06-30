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
const CONTRACT_VERSION = 'turn_result_v1';

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

function detectApprovalRequirement(input, kind) {
  const text = String(input || '').toLowerCase();
  const isMoneyOrExternal = (
    kind === 'money'
    || /\b(money mode|make money|revenue|client|lead|outreach|affiliate|marketplace|wallet|payment|paid task)\b/.test(text)
  );
  if (!isMoneyOrExternal) return null;

  const risky = [
    ['publish', /\b(publish|post|schedule post|go live)\b/],
    ['outreach', /\b(send|email|dm|message|contact|outreach)\b/],
    ['payment', /\b(spend|pay|purchase|buy|wallet|payment|transfer|charge)\b/],
    ['paid_task', /\b(accept paid|accept job|submit client|deliver client|bid)\b/],
    ['external_account', /\b(change account|connect account|modify account|oauth|api key)\b/],
  ].filter(([, pattern]) => pattern.test(text)).map(([name]) => name);

  if (!risky.length) return null;
  return {
    id: safeId('approval'),
    status: 'required',
    risk_level: 'high',
    required_for: risky,
    reason: 'This request may publish, send, spend, accept paid work, or modify an external account.',
    requested_at: nowIso(),
  };
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
      contract_version: CONTRACT_VERSION,
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

    const approvalRequired = detectApprovalRequirement(input, kind);
    if (approvalRequired) {
      approvals.push(approvalRequired);
      actions.push({
        id: 'approval_gate',
        action: 'approval_gate',
        label: 'Human approval required before execution',
        status: 'waiting_approval',
        proof: { approval_id: approvalRequired.id, required_for: approvalRequired.required_for },
      });
      proof.push({
        type: 'approval_gate',
        label: 'Execution paused for human approval',
        status: 'waiting_approval',
        approval_id: approvalRequired.id,
      });

      const assistantReplyForApproval = formatTeammateReply({
        input,
        rawReply: 'I paused before taking external or money-related action. Approve the action first, then I can continue with execution.',
        source: 'approval_gate',
        proof,
        errors: [],
        degraded: false,
      });
      const turn = {
        ok: true,
        contract_version: CONTRACT_VERSION,
        compatibility_route: options.source || kind,
        turn_id: turnId,
        task_id: queued.taskId,
        taskId: queued.taskId,
        workflow_run: run.run_id,
        user_id: userId,
        tenant_id: tenantId,
        input,
        intent: queued.subsystem || kind,
        status: 'waiting_approval',
        assistant_reply: assistantReplyForApproval,
        reply: assistantReplyForApproval,
        content: assistantReplyForApproval,
        response: assistantReplyForApproval,
        raw_reply: 'Execution paused for approval.',
        actions,
        artifacts,
        attachments: artifacts,
        proof,
        approvals,
        degraded: false,
        errors,
        trace_id: null,
        source: 'approval_gate',
        memory_router: null,
        created_at: nowIso(),
      };

      appendTurnLog(turn);
      broadcast('approval:required', { turn_id: turnId, task_id: queued.taskId, approval: approvalRequired, turn });
      broadcast('proof:ready', turn);
      broadcast('turn:completed', turn);
      broadcast('orchestrator:message', {
        turn_id: turnId,
        taskId: queued.taskId,
        message: assistantReplyForApproval,
        proof,
        artifacts,
        actions,
        approvals,
        degraded: false,
        source: 'approval_gate',
        subsystem: queued.subsystem || 'orchestrator',
        timestamp: nowIso(),
      });
      return turn;
    }

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
            goal: input,
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
            // Real AgentController result drives the agent task's VERIFIED
            // completion — not the scheduler's timer.
            try { deps.orchestrator.completeTask?.(queued.taskId, { ok: true, result: pyPayload }); } catch { /* non-fatal */ }
          } else {
            degraded = true;
            errors.push({ stage: 'agent_controller', message: `Python returned ${pyPayload?._http_status || 'non-ok'}` });
            try { deps.orchestrator.completeTask?.(queued.taskId, { ok: false, error: `python_${pyPayload?._http_status || 'non_ok'}` }); } catch { /* non-fatal */ }
          }
        } catch (error) {
          degraded = true;
          errors.push({ stage: 'agent_controller', message: compactError(error) });
          try { deps.orchestrator.completeTask?.(queued.taskId, { ok: false, error: 'agent_controller_error' }); } catch { /* non-fatal */ }
        }
        broadcast('action:completed', { turn_id: turnId, task_id: queued.taskId, action: 'agent_controller', status: source === 'agent_controller' ? 'completed' : 'failed' });
      }

      // Pipeline-first inversion (C1/R1): `/api/chat` runs process_user_input,
      // whose Phase 0 already executes the real_execution_engine — so for chat
      // the pipeline IS the controlled execution path (with the adversarial
      // filter, STRICT_PIPELINE and telemetry the standalone subprocess skips).
      // Default: call the pipeline first for chat and skip the redundant
      // run_execution.py subprocess. Set TURN_RUNNER_PIPELINE_FIRST=0 to restore
      // the legacy order (execution-engine subprocess → pipeline).
      const pipelineFirst = process.env.TURN_RUNNER_PIPELINE_FIRST !== '0';

      const tryExecutionEngine = async () => {
        if (assistantReply) return;
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
      };

      const tryPipeline = async () => {
        if (assistantReply || !(await deps.isPythonBackendUp())) return;
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
      };

      if (kind === 'chat' && pipelineFirst) {
        // Pipeline is the spine for chat; its Phase 0 covers goal execution.
        await tryPipeline();
      } else {
        // Tasks (after AgentController above), or legacy order when flag=0.
        await tryExecutionEngine();
        await tryPipeline();
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
      contract_version: CONTRACT_VERSION,
      compatibility_route: options.source || kind,
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
