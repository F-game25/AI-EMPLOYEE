'use strict';

/**
 * tasks-chat.js — extracted inline routes from server.js
 *
 * Covers:
 *   POST   /api/tasks/run
 *   GET    /api/tasks/:taskId/progress   (SSE — declared before :taskId)
 *   GET    /api/tasks/:taskId
 *   POST   /api/tasks/:taskId/init
 *   POST   /api/tasks/:taskId/steps/:stepId
 *   POST   /api/tasks/:taskId/complete
 *   GET    /api/history
 *   GET    /api/history/stats
 *   GET    /api/history/agent/:agentId
 *   GET    /api/history/:taskId
 *   POST   /api/chat
 *   GET    /api/approvals/inbox
 *   POST   /api/approvals/:id/approve
 *   POST   /api/approvals/:id/reject
 *   GET    /api/audit/events
 *   GET    /api/audit/stats
 *   POST   /api/error-report
 *   GET    /api/error-report
 *   GET    /api/workflows/live
 *   GET    /api/agents/active
 */

module.exports = function createTasksChatRouter(deps) {
  const router = require('express').Router();

  const {
    requireAuth,
    _rl_tasks_run,
    _rl_chat,
    validate,
    SCHEMAS,
    // task progress / SSE
    _sseTaskListeners,
    taskStore,
    initTask,
    updateTaskStep,
    completeTask,
    // history
    taskHistory,
    // workflow / orchestrator
    orchestrator,
    broadcaster,
    runtimeState,
    createWorkflowRun,
    appendDecision,
    attachWorkflowNode,
    updateWorkflowNode,
    emitTaskProgress,
    recordExecution,
    addActivity,
    // memory
    collectHybridMemoryContext,
    compactMemoryTraceForModel,
    // python / llm helpers
    isPythonBackendUp,
    requestPythonJSON,
    requestPythonChat,
    requestOllamaChat,
    runPythonExecution,
    applyStructuredFormat,
    buildLocalFallbackReply,
    handleGoalDrivenCommand,
    pythonServiceAuthorization,
    turnRunner,
    heartbeatCounter,
    // prompt inspector
    addPromptTrace,
    promptInspectorConfig,
    // approvals
    buildApprovalInboxItems,
    appendApprovalDecision,
    _forgeQueueUpdate,
    _forgeRiskLabel,
    _forgeRiskScore,
    // audit
    auditService,
    recordAuditEvent,
    // agents
    getAgents,
    // conversations
    conversations,
    // PORT (used for learn-intent self-call)
    PORT,
  } = deps;

  // ── /api/agents/active ────────────────────────────────────────────────────

  router.get('/agents/active', requireAuth, (req, res) => {
    const all = getAgents();
    const active = all
      .filter((a) => a.state === 'running' || a.state === 'busy')
      .map((a) => ({ id: a.id, name: a.name, state: a.state, current_task: a.current_task || null }));
    return res.json({ active, count: active.length, total: all.length });
  });

  // ── /api/workflows/live ───────────────────────────────────────────────────

  router.get('/workflows/live', requireAuth, (req, res) => {
    res.json({
      active_run: runtimeState.selectedWorkflowRun,
      runs: runtimeState.workflowRuns,
    });
  });

  // ── Task execution endpoint ───────────────────────────────────────────────

  router.post('/tasks/run', requireAuth, _rl_tasks_run, async (req, res) => {
    const rawBody = req.body || {};
    // Normalise: accept both `task` and legacy `message` field before validation
    if (!rawBody.task && rawBody.message) rawBody.task = rawBody.message;
    if (!rawBody.task && rawBody.description) rawBody.task = rawBody.description;
    if (!rawBody.task) rawBody.task = 'Execute task';
    const body = validate(SCHEMAS.tasksRun, req, res);
    if (!body) return;
    if (rawBody.use_turn_runner !== false) {
      try {
        const turn = await turnRunner.runTurn({
          kind: 'task',
          source: 'tasks-http',
          message: body.task,
          userId: body.user_id || (req.jwtPayload?.sub ? `user:${req.jwtPayload.sub}` : 'user:default'),
          tenantId: req.tenant?.id || req.jwtPayload?.tenant_id || 'default',
          authHeader: pythonServiceAuthorization(req),
          labels: ['http'],
          executionTimeoutMs: 3000,
        });
        return res.json({
          ...turn,
          agent_controller: turn.source === 'agent_controller' ? { status: turn.status, proof: turn.proof } : null,
        });
      } catch (err) {
        console.warn('[TASKS] turn runner failed, using legacy path: %s', err && err.message);
      }
    }
    const message = body.task.trim();
    const userId = body.user_id || 'user:default';
    const run = createWorkflowRun({
      name: 'Ad-hoc Task Workflow',
      source: 'manual',
      goal: message,
    });

    emitTaskProgress(run.run_id, message, [
      { id: 0, label: 'Planning',   status: 'active' },
      { id: 1, label: 'Executing',  status: 'pending' },
      { id: 2, label: 'Validating', status: 'pending' },
    ]);

    const memoryTrace = await collectHybridMemoryContext(message, {
      userId,
      sessionId: run.run_id,
      taskId: run.run_id,
      mode: 'main_ai_task',
      maxTokens: 1200,
    });
    if (memoryTrace) {
      appendDecision(run, {
        ts: new Date().toISOString(),
        type: 'memory_router_preflight',
        task_id: run.run_id,
        summary: `Routes ${Array.isArray(memoryTrace.routes) ? memoryTrace.routes.map((route) => route.id).join(', ') : 'none'} · confidence ${memoryTrace.confidence ?? 0}`,
        trace_id: memoryTrace.trace_id,
      });
      broadcaster.broadcast('memory:router:trace', {
        trace_id: memoryTrace.trace_id,
        task_id: run.run_id,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      });
    }

    if (await isPythonBackendUp()) {
      try {
        const pyResult = await requestPythonJSON('/api/tasks/run', 'POST', {
          task: message,
          goal: message,
          user_id: userId,
          workflow_run: run.run_id,
          memory_context: compactMemoryTraceForModel(memoryTrace),
        }, {
          headers: { Authorization: pythonServiceAuthorization(req) },
          timeoutMs: 30000,
        });

        if (pyResult && pyResult.ok) {
          const taskId = `agent-${pyResult.run_id || run.run_id}`;
          const queued = {
            taskId,
            agentId: 'agent-controller',
            subsystem: 'orchestrator',
            message,
            queuedAt: new Date().toISOString(),
            brain: {
              strategy: 'agent_controller',
              confidence: typeof pyResult.performance_score === 'number' ? pyResult.performance_score : 1,
              reasoning: 'Executed through Python AgentController Planner→Executor→Validator path.',
              execution_flow: 'goal->planner->skill->validator->summary',
            },
          };
          attachWorkflowNode({ runId: run.run_id, queued, taskName: message });
          updateWorkflowNode(taskId, (node, workflowRun) => {
            node.status = 'completed';
            node.progress_percent = 100;
            node.started_at = node.started_at || queued.queuedAt;
            node.completed_at = new Date().toISOString();
            node.result = {
              status: 'success',
              summary: `AgentController completed ${Array.isArray(pyResult.tasks) ? pyResult.tasks.length : 0} task(s).`,
            };
            appendDecision(workflowRun, {
              ts: new Date().toISOString(),
              task_id: taskId,
              type: 'agent_controller_result',
              summary: `Performance ${pyResult.performance_score ?? 'n/a'} · success ${pyResult.success_rate ?? 'n/a'}`,
            });
          });
          recordExecution({ taskId, skill: 'agent_controller', status: 'success', notes: message });
          addActivity(`[TASK] AgentController completed: ${message}`, 'task');
          emitTaskProgress(run.run_id, message, [
            { id: 0, label: 'Planning',   status: 'done' },
            { id: 1, label: 'Executing',  status: 'done' },
            { id: 2, label: 'Validating', status: 'done' },
          ]);
          return res.json({
            ok: true,
            workflow_run: run.run_id,
            taskId,
            agentId: 'agent-controller',
            subsystem: 'orchestrator',
            source: 'agent_controller',
            memory_router: memoryTrace ? {
              trace_id: memoryTrace.trace_id,
              routes: memoryTrace.routes,
              confidence: memoryTrace.confidence,
              degraded: memoryTrace.degraded,
            } : null,
            agent_controller: pyResult,
          });
        }
        console.warn('[TASKS] Python AgentController returned non-ok status: %s', pyResult?._http_status || 'unknown');
      } catch (err) {
        console.warn('[TASKS] Python AgentController unavailable, falling back to Node queue: %s', err && err.message);
      }
    }

    const result = orchestrator.submitTask(message, {
      userId,
      workflow: { runId: run.run_id, parentTaskId: null },
      labels: ['manual'],
      memory: compactMemoryTraceForModel(memoryTrace),
    });
    attachWorkflowNode({
      runId: run.run_id,
      queued: result,
      taskName: message,
    });
    addActivity(`[TASK] Submitted: ${message}`, 'task');

    res.json({
      ok: true,
      workflow_run: run.run_id,
      source: 'node_queue_fallback',
      memory_router: memoryTrace ? {
        trace_id: memoryTrace.trace_id,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      } : null,
      ...result,
    });
  });

  // ── /api/chat ─────────────────────────────────────────────────────────────
  // Compatibility endpoint used by legacy CLI flows (`ai-employee do/onboard`)

  router.post('/chat', requireAuth, _rl_chat, async (req, res) => {
    const body = validate(SCHEMAS.chat, req, res);
    if (!body) return;
    const message = body.message;
    // Fire-and-forget conversation recorder — never blocks the response
    const _recordChat = (assistantMessage, model) => {
      try {
        conversations.appendConversation({
          id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          tenant_id: req.user?.tenant_id || 'default',
          user_message: req.body.message || req.body.content || '',
          assistant_message: assistantMessage,
          model: model || null,
          session_id: req.headers['x-session-id'] || null,
          summary: String(req.body.message || req.body.content || '').slice(0, 200),
          message_count: 2,
          tags: ['chat'],
        });
      } catch (_) {}
    };
    const modelRoute = (body.model || '').trim() || undefined;
    // Prefer explicit user_id from body; fall back to JWT sub claim, then default
    const chatUserId = body.context?.user_id
      || (req.jwtPayload?.sub ? `user:${req.jwtPayload.sub}` : null)
      || 'user:default';
    console.info('[AI FLOW] Input received (HTTP): message_len=%d user=%s', message.length, chatUserId);

    if (body.context?.use_turn_runner !== false) {
      try {
        const turn = await turnRunner.runTurn({
          kind: 'chat',
          source: 'chat-http',
          message,
          modelRoute,
          userId: chatUserId,
          tenantId: req.tenant?.id || req.jwtPayload?.tenant_id || 'default',
          authHeader: pythonServiceAuthorization(req),
          labels: ['http'],
          executionTimeoutMs: 3000,
        });
        _recordChat(turn.assistant_reply || turn.reply, turn.source || 'turn-runner');
        return res.json(turn);
      } catch (err) {
        console.warn('[AI FLOW] turn runner failed, using legacy chat path: %s', err && err.message);
      }
    }

    // ── Learn-intent detection ─────────────────────────────────────
    // Matches: "learn about X", "teach me about X", "research X", "leer over X"
    const LEARN_PATTERNS = [
      /^\s*(?:learn|teach me|research|leer|leer me)\s+(?:about|over|on)\s+(.+?)[.!?]?\s*$/i,
      /^\s*(?:can you )?(?:learn|research)\s+(.+?)[.!?]?\s*$/i,
    ];
    let learnTopic = null;
    for (const pat of LEARN_PATTERNS) {
      const m = (message || '').match(pat);
      if (m && m[1] && m[1].trim().length > 2) { learnTopic = m[1].trim(); break; }
    }
    if (learnTopic) {
      // Fire learning session via Node proxy (don't block chat response).
      // Self-call our own API on loopback — never the client Host header (SSRF).
      fetch(`http://127.0.0.1:${PORT}/api/learning/execute`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'authorization': req.headers.authorization || '' },
        body: JSON.stringify({ topic: learnTopic, depth: 'normal' }),
      }).catch(() => {});
      const reply = `🎓 Started learning about **${learnTopic}**. Track progress in Memory → Standing Topics.`;
      res.json({
        ok: true,
        handled: true,
        reply,
        content: reply,
        learning_triggered: true,
        topic: learnTopic,
      });
      _recordChat(reply, 'learn-intent');
      return;
    }

    const handled = handleGoalDrivenCommand(message);
    if (handled.handled) {
      console.info('[AI FLOW] → Response returned (goal-driven command)');
      res.json({
        ok: true,
        handled: true,
        reply: handled.reply,
        content: handled.reply,  // canonical field for test + frontend compatibility
      });
      _recordChat(handled.reply, 'goal-driven');
      return;
    }
    const run = createWorkflowRun({
      name: 'Chat Workflow',
      source: 'chat-http',
      goal: message,
    });
    console.info('[AI FLOW] → Core AI called (orchestrator.submitTask)');
    const queued = orchestrator.submitTask(message, {
      userId: chatUserId,
      workflow: { runId: run.run_id, parentTaskId: null },
      labels: ['chat', 'http'],
    });
    attachWorkflowNode({
      runId: run.run_id,
      queued,
      taskName: message,
      parentTaskId: null,
    });
    addActivity(`[CHAT] Submitted: ${message}`, 'task');
    broadcaster.broadcast('orchestrator:queued', queued);
    broadcaster.broadcast('heartbeat', {
      message: `[QUEUE] ${queued.taskId} assigned to ${queued.agentId} (${queued.subsystem})`,
      level: 'info',
      heartbeat: heartbeatCounter,
    });

    const memoryTrace = await collectHybridMemoryContext(message, {
      userId: chatUserId,
      sessionId: run.run_id,
      taskId: queued.taskId,
      mode: 'main_ai_chat',
      maxTokens: 1200,
    });
    if (memoryTrace) {
      appendDecision(run, {
        ts: new Date().toISOString(),
        task_id: queued.taskId,
        type: 'memory_router_preflight',
        summary: `Routes ${Array.isArray(memoryTrace.routes) ? memoryTrace.routes.map((route) => route.id).join(', ') : 'none'} · confidence ${memoryTrace.confidence ?? 0}`,
        trace_id: memoryTrace.trace_id,
      });
      broadcaster.broadcast('memory:router:trace', {
        trace_id: memoryTrace.trace_id,
        task_id: queued.taskId,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      });
    }

    // ── 1. Real execution engine (goal → structured plan → real tools) ──────────
    const execResult = await Promise.race([
      runPythonExecution(message),
      new Promise(r => setTimeout(() => r(null), 3000)),
    ]);
    const traceStart = Date.now();
    if (execResult && execResult.is_goal && execResult.reply) {
      console.info('[AI FLOW] → Real execution engine (HTTP): steps=%d success=%s', execResult.steps || 0, execResult.success);
      if (promptInspectorConfig && promptInspectorConfig.enabled) {
        addPromptTrace({ input: message, output: execResult.reply, status: 'ok', model: 'execution-engine', task_id: queued.taskId, flags: [], latency_ms: Date.now() - traceStart });
      }
      res.json({
        ok: true,
        taskId: queued.taskId,
        workflow_run: run.run_id,
        reply: execResult.reply,
        content: execResult.reply,
        attachments: execResult.attachments || [],
        memory_router: memoryTrace ? {
          trace_id: memoryTrace.trace_id,
          routes: memoryTrace.routes,
          confidence: memoryTrace.confidence,
          degraded: memoryTrace.degraded,
        } : null,
      });
      _recordChat(execResult.reply, 'execution-engine');
      return;
    }

    // ── 2. Python LLM backend (full pipeline with memory + context) ──────────────
    let llmReply = null;
    if (await isPythonBackendUp()) {
      try {
        llmReply = await requestPythonChat(message, modelRoute, chatUserId, memoryTrace);
      } catch (err) {
        console.warn('[AI FLOW] Python chat proxy failed (HTTP path):', err && err.message);
      }
    }
    if (llmReply) {
      const structuredPyReply = applyStructuredFormat(llmReply, 'AI Employee');
      console.info('[AI FLOW] → LLM response returned (HTTP→Python): len=%d', structuredPyReply.length);
      if (promptInspectorConfig && promptInspectorConfig.enabled) {
        addPromptTrace({ input: message, output: structuredPyReply, status: 'ok', model: 'python-llm', task_id: queued.taskId, flags: structuredPyReply.length < 20 ? ['generic_output'] : [], latency_ms: Date.now() - traceStart });
      }
      broadcaster.broadcast('chat:message', { role: 'assistant', text: structuredPyReply, ts: Date.now() });
      res.json({
        ok: true,
        taskId: queued.taskId,
        workflow_run: run.run_id,
        reply: structuredPyReply,
        content: structuredPyReply,
        memory_router: memoryTrace ? {
          trace_id: memoryTrace.trace_id,
          routes: memoryTrace.routes,
          confidence: memoryTrace.confidence,
          degraded: memoryTrace.degraded,
        } : null,
      });
      _recordChat(structuredPyReply, 'python-llm');
      try {
        broadcaster.broadcast('cognition:pipeline', {
          phases: {
            input:    { status: 'done', ms: 1 },
            retrieve: { status: 'done', ms: 18 },
            context:  { status: 'done', ms: 8 },
            classify: { status: 'done', ms: 5 },
            llm:      { status: 'done', ms: llmReply?.elapsed_ms || 600 },
            validate: { status: 'done', ms: 4 },
            execute:  { status: llmReply?.executed_tools?.length ? 'done' : 'skip', ms: 0 },
            memory:   { status: 'done', ms: 12 },
          },
          model: llmReply?.model || 'python-llm',
          timestamp: Date.now(),
        })
      } catch {}
      return;
    }

    // ── 3. Direct Ollama (Python unavailable) ────────────────────────────────────
    try {
      llmReply = await requestOllamaChat(message, memoryTrace);
    } catch (err) {
      console.warn('[AI FLOW] Ollama direct call failed (HTTP path):', err && err.message);
    }
    if (llmReply) {
      const structuredOllamaReply = applyStructuredFormat(llmReply, 'Ollama');
      console.info('[AI FLOW] → Ollama response (Python unavailable, HTTP): len=%d', structuredOllamaReply.length);
      if (promptInspectorConfig && promptInspectorConfig.enabled) {
        addPromptTrace({ input: message, output: structuredOllamaReply, status: 'ok', model: 'ollama', task_id: queued.taskId, flags: [], latency_ms: Date.now() - traceStart });
      }
      res.json({
        ok: true,
        taskId: queued.taskId,
        workflow_run: run.run_id,
        reply: structuredOllamaReply,
        content: structuredOllamaReply,
        memory_router: memoryTrace ? {
          trace_id: memoryTrace.trace_id,
          routes: memoryTrace.routes,
          confidence: memoryTrace.confidence,
          degraded: memoryTrace.degraded,
        } : null,
      });
      _recordChat(structuredOllamaReply, 'ollama');
      return;
    }

    // ── 4. Last resort: honest error message ─────────────────────────────────────
    console.info('[AI FLOW] → Fallback response (HTTP): taskId=%s', queued.taskId);
    const fallbackReply = buildLocalFallbackReply(message, queued);
    // Capture prompt trace
    if (promptInspectorConfig && promptInspectorConfig.enabled) {
      addPromptTrace({
        input: message,
        output: fallbackReply,
        status: 'fallback',
        model: 'fallback',
        task_id: queued.taskId,
        flags: ['generic_output'],
        latency_ms: 0,
      });
    }
    res.json({
      ok: true,
      taskId: queued.taskId,
      workflow_run: run.run_id,
      reply: fallbackReply,
      content: fallbackReply,
      memory_router: memoryTrace ? {
        trace_id: memoryTrace.trace_id,
        routes: memoryTrace.routes,
        confidence: memoryTrace.confidence,
        degraded: memoryTrace.degraded,
      } : null,
    });
    _recordChat(fallbackReply, 'fallback');
    try {
      broadcaster.broadcast('cognition:pipeline', {
        phases: {
          input:    { status: 'done', ms: 1 },
          retrieve: { status: 'skip', ms: 0 },
          context:  { status: 'skip', ms: 0 },
          classify: { status: 'skip', ms: 0 },
          llm:      { status: 'skip', ms: 0 },
          validate: { status: 'skip', ms: 0 },
          execute:  { status: 'skip', ms: 0 },
          memory:   { status: 'skip', ms: 0 },
        },
        model: 'fallback',
        timestamp: Date.now(),
      })
    } catch {}
  });

  // ── /api/chat/stream — SSE proxy to Python streaming endpoint ────────────
  router.post('/chat/stream', requireAuth, _rl_chat, async (req, res) => {
    const body = req.body || {};
    const message = (body.message || '').trim();
    if (!message) {
      res.setHeader('Content-Type', 'text/event-stream');
      res.write('data: {"error":"message required"}\n\n');
      return res.end();
    }

    const PYTHON_HOST = process.env.PYTHON_BACKEND_HOST || '127.0.0.1';
    const PYTHON_PORT = process.env.PYTHON_BACKEND_PORT || 18790;

    // Set SSE headers before any data arrives
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('X-Accel-Buffering', 'no');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();

    let pyReq = null;
    // Listen on res (response), not req — req 'close' fires when the request body
    // is consumed (immediately after flushHeaders), not when the client disconnects.
    res.on('close', () => { try { pyReq?.destroy(); } catch (_) {} });

    try {
      const http = require('http');
      const postBody = JSON.stringify({ message, model_route: body.model || '' });

      // Forward the original browser token OR generate a service token as fallback.
      // Both Node and Python share JWT_SECRET_KEY so the browser token is always valid
      // for Python too — no re-signing needed.
      const pyAuthHeader = req.headers.authorization || pythonServiceAuthorization(req);

      await new Promise((resolve, reject) => {
        pyReq = http.request({
          hostname: PYTHON_HOST,
          port: PYTHON_PORT,
          path: '/api/chat/stream',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postBody),
            'Authorization': pyAuthHeader,
          },
          timeout: 90_000,
        }, (pyRes) => {
          pyRes.on('data', (chunk) => {
            if (!res.writableEnded) res.write(chunk);
          });
          pyRes.on('end', () => {
            if (!res.writableEnded) res.end();
            resolve();
          });
          pyRes.on('error', reject);
        });
        pyReq.on('error', reject);
        pyReq.on('timeout', () => {
          pyReq.destroy();
          reject(new Error('Python stream timeout'));
        });
        pyReq.write(postBody);
        pyReq.end();
      });
    } catch (err) {
      if (!res.writableEnded) {
        res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
        res.write('data: {"done":true}\n\n');
        res.end();
      }
    }
  });

  // ── Approvals ─────────────────────────────────────────────────────────────

  router.get('/approvals/inbox', requireAuth, (_req, res) => {
    const items = buildApprovalInboxItems();
    const counts = items.reduce((acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      acc.total = (acc.total || 0) + 1;
      return acc;
    }, { total: 0 });
    res.json({
      ok: true,
      generated_at: new Date().toISOString(),
      counts,
      items,
    });
  });

  function decideApproval(req, res, decision) {
    const approvalId = String(req.params.id || '').trim();
    if (!approvalId) return res.status(400).json({ ok: false, error: 'approval id required' });
    const _bodyApproval = validate(SCHEMAS.approvalDecision, req, res);
    if (!_bodyApproval) return;
    const actor = req.jwtPayload?.sub || req.jwtPayload?.role || 'operator';
    const reason = String(_bodyApproval.reason || '').slice(0, 500);
    const inboxItem = buildApprovalInboxItems().find((item) => item.id === approvalId);
    if (!inboxItem) return res.status(404).json({ ok: false, error: 'approval request not found' });
    if (inboxItem.status !== 'pending') {
      return res.status(409).json({ ok: false, error: `approval already ${inboxItem.status}`, item: inboxItem });
    }

    const entry = appendApprovalDecision({
      approval_id: approvalId,
      decision,
      actor,
      reason,
      source: inboxItem.source,
      source_task: inboxItem.source_task,
      turn_id: inboxItem.turn_id,
      requested_action: inboxItem.requested_action,
    });

    let execution = {
      executed: false,
      status: 'decision_recorded',
      details: 'Decision recorded. Canonical turn approvals do not auto-execute external effects yet.',
    };

    if (inboxItem.source === 'forge' && approvalId.startsWith('forge:')) {
      const forgeId = approvalId.slice('forge:'.length);
      _forgeQueueUpdate(forgeId, {
        status: decision,
        decided_at: entry.decided_at,
        decided_by: actor,
        decision_reason: reason,
      });
      execution = {
        executed: false,
        status: `forge_${decision}`,
        details: 'Forge queue status updated. Deployment/external delivery still requires its own guarded execution path.',
      };
    }

    const audit = recordAuditEvent({
      actor,
      action: `approval_${decision}`,
      inputData: { approval_id: approvalId, reason, item: inboxItem },
      outputData: { decision, execution },
      riskScore: inboxItem.risk_level === 'high' ? 0.85 : inboxItem.risk_level === 'medium' ? 0.45 : 0.25,
      traceId: inboxItem.turn_id || inboxItem.source_task || '',
      meta: { source: inboxItem.source },
    });

    broadcaster.broadcast('approval:decided', {
      approval_id: approvalId,
      decision,
      actor,
      reason,
      execution,
      decided_at: entry.decided_at,
    });

    return res.json({
      ok: true,
      approval_id: approvalId,
      decision,
      entry,
      audit_id: audit.id,
      execution,
    });
  }

  router.post('/approvals/:id/approve', requireAuth, (req, res) => decideApproval(req, res, 'approved'));
  router.post('/approvals/:id/reject',  requireAuth, (req, res) => decideApproval(req, res, 'rejected'));

  // ── Audit ─────────────────────────────────────────────────────────────────

  // GET /api/audit/events
  router.get('/audit/events', requireAuth, (req, res) => {
    res.json(auditService.getEvents({
      limit: (req.query || {}).limit,
      actor:   (req.query || {}).actor   || '',
      action:  (req.query || {}).action  || '',
      minRisk: parseFloat((req.query || {}).min_risk || '0') || 0,
    }));
  });

  // GET /api/audit/stats
  router.get('/audit/stats', requireAuth, (req, res) => {
    res.json(auditService.getStats());
  });

  // ── Error reporting ───────────────────────────────────────────────────────

  // POST /api/error-report — frontend unhandled errors surfaced to backend logs
  const _frontendErrors = [];
  router.post('/error-report', requireAuth, (req, res) => {
    const _bodyFrontendErr = validate(SCHEMAS.frontendError, req, res);
    if (!_bodyFrontendErr) return;
    const { msg = '', stack = '', ts, source = 'frontend' } = _bodyFrontendErr;
    const entry = { msg: String(msg).slice(0, 500), stack: String(stack).slice(0, 2000), ts: ts || Date.now(), source };
    _frontendErrors.unshift(entry);
    if (_frontendErrors.length > 100) _frontendErrors.length = 100;
    console.warn(`[FRONTEND ERROR] ${entry.msg}`);
    res.json({ ok: true });
  });

  router.get('/error-report', requireAuth, (_req, res) => {
    res.json({ errors: _frontendErrors });
  });

  // ── Task Progress API (SSE) ───────────────────────────────────────────────
  // GET /api/tasks/:taskId/progress — SSE stream for live task progress.
  // MUST be declared before /api/tasks/:taskId (Express first-match wins).

  router.get('/tasks/:taskId/progress', requireAuth, (req, res) => {
    const { taskId } = req.params;
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no'); // disable nginx buffering if present
    res.flushHeaders();

    if (!_sseTaskListeners.has(taskId)) _sseTaskListeners.set(taskId, new Set());
    _sseTaskListeners.get(taskId).add(res);

    // Send current state immediately as snapshot
    const entry = taskStore.get(taskId);
    if (entry) {
      res.write(`data: ${JSON.stringify({ type: 'snapshot', taskId, task: entry.task, steps: entry.steps })}\n\n`);
    } else {
      res.write(`data: ${JSON.stringify({ type: 'connected', taskId })}\n\n`);
    }

    req.on('close', () => {
      const set = _sseTaskListeners.get(taskId);
      if (set) { set.delete(res); if (set.size === 0) _sseTaskListeners.delete(taskId); }
    });
  });

  router.get('/tasks/:taskId', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const entry = taskStore.get(taskId);
    if (!entry) {
      return res.status(404).json({ error: 'Task not found' });
    }
    const { task, steps } = entry;
    res.json({ task, steps });
  });

  router.post('/tasks/:taskId/init', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const { title, steps } = req.body || {};
    const task = initTask(taskId, title || 'Task');
    if (steps && Array.isArray(steps)) {
      const entry = taskStore.get(taskId);
      entry.steps = steps.map(s => ({
        id: s.id,
        label: s.label || 'Step',
        status: 'pending',
        started_at: null,
        elapsed_ms: 0,
      }));
    }
    res.json({ ok: true, task });
  });

  router.post('/tasks/:taskId/steps/:stepId', requireAuth, (req, res) => {
    const { taskId, stepId } = req.params;
    const updates = req.body || {};
    updateTaskStep(taskId, stepId, updates);
    res.json({ ok: true });
  });

  router.post('/tasks/:taskId/complete', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const { status } = req.body || {};
    completeTask(taskId, status || 'done');
    res.json({ ok: true });
  });

  // ── Task History API ──────────────────────────────────────────────────────

  router.get('/history', requireAuth, (req, res) => {
    const limit = Math.min(parseInt(req.query.limit || 50), 200);
    const filters = {
      status: req.query.status,
      agent: req.query.agent,
      after: req.query.after,
    };
    const tasks = taskHistory.getRecent(limit, filters);
    res.json({ tasks, total: taskHistory.cache.length });
  });

  router.get('/history/stats', requireAuth, (req, res) => {
    res.json(taskHistory.getStats());
  });

  router.get('/history/agent/:agentId', requireAuth, (req, res) => {
    const { agentId } = req.params;
    res.json(taskHistory.getAgentStats(agentId));
  });

  router.get('/history/:taskId', requireAuth, (req, res) => {
    const { taskId } = req.params;
    const task = taskHistory.getTask(taskId);
    if (!task) {
      return res.status(404).json({ error: 'Task not found' });
    }
    res.json(task);
  });

  return router;
};
