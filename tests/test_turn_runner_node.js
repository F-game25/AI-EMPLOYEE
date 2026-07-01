'use strict';

// C1/R1 — the Node turn-runner routes chat through the `/api/chat` pipeline
// FIRST (its Phase 0 already runs the execution engine), skipping the redundant
// run_execution.py subprocess. TURN_RUNNER_PIPELINE_FIRST=0 restores legacy
// order. This test proves both orderings plus the unchanged approval gate.

const assert = require('assert');
const { createTurnRunner } = require('../backend/services/turn-runner');

function makeRunner(spies, overrides = {}) {
  const events = [];
  const decisions = [];
  const nodes = [];
  const activities = [];
  const deps = {
    broadcaster: { broadcast(event, data) { events.push({ event, data }); } },
    orchestrator: {
      submitTask(message) {
        return { taskId: 'task-test', agentId: 'agent-test', subsystem: 'orchestrator', message };
      },
      completeTask() {},
    },
    createWorkflowRun({ goal }) { return { run_id: 'run-test', goal, decisions: [] }; },
    appendDecision(_run, entry) { decisions.push(entry); },
    attachWorkflowNode(node) { nodes.push(node); },
    addActivity(message, kind) { activities.push({ message, kind }); },
    async collectHybridMemoryContext() {
      return {
        trace_id: 'memtrace-test',
        routes: [{ id: 'semantic_rag', hits: 1 }],
        confidence: 0.8,
        degraded: false,
        citations: [{ title: 'Policy doc', source: 'vault' }],
        context: 'known context',
      };
    },
    compactMemoryTraceForModel(trace) { return { trace_id: trace.trace_id, context: trace.context }; },
    async runPythonExecution() {
      spies.execCalled = true;
      return {
        is_goal: true,
        reply: 'Created index.html',
        success: true,
        steps: 1,
        attachments: [{ filename: 'index.html', path: '/tmp/index.html', type: 'html', bytes: 12 }],
        proof: [{ type: 'file', label: 'index.html', path: '/tmp/index.html', status: 'completed' }],
        step_actions: [{ action: 'website_builder', status: 'success' }],
      };
    },
    async isPythonBackendUp() { return true; },
    async requestPythonJSON() { throw new Error('not expected'); },
    async requestPythonChatPayload() {
      spies.pipelineCalled = true;
      return {
        response: 'Landing page plan ready',
        artifacts: [{ name: 'index.html', path: '/tmp/index.html', type: 'html' }],
        proof: [{ type: 'file', label: 'index.html', status: 'completed' }],
        trace_id: 'pl-trace-1',
      };
    },
    async requestOllamaChat() { return null; },
    applyStructuredFormat(text) { return text; },
    buildLocalFallbackReply() { return 'fallback'; },
    ...overrides,
  };
  return { runner: createTurnRunner(deps), events, decisions, nodes, activities };
}

async function testPipelineFirstChat() {
  delete process.env.TURN_RUNNER_PIPELINE_FIRST; // default = pipeline-first
  const spies = {};
  const { runner, events, decisions, nodes, activities } = makeRunner(spies);

  const turn = await runner.runTurn({
    kind: 'chat',
    source: 'test',
    message: 'build a landing page',
    userId: 'user:test',
    tenantId: 'tenant:test',
  });

  // The spine (pipeline) answered; the redundant subprocess was NOT spawned.
  assert.equal(turn.source, 'python-llm', 'chat must go pipeline-first');
  assert.equal(spies.pipelineCalled, true, 'pipeline rung must run');
  assert.ok(!spies.execCalled, 'execution-engine subprocess must be skipped for chat');

  // Contract + envelope unchanged.
  assert.equal(turn.ok, true);
  assert.equal(turn.contract_version, 'turn_result_v1');
  assert.equal(turn.compatibility_route, 'test');
  assert.equal(turn.turn_id.startsWith('turn-'), true);
  assert.equal(turn.task_id, 'task-test');
  assert.equal(turn.status, 'completed');
  assert.ok(turn.reply.includes('I understood: build a landing page'));
  assert.ok(turn.reply.includes('Proof:'));
  assert.ok(turn.artifacts.some((item) => item.name === 'index.html'));
  assert.ok(turn.proof.some((item) => item.label === 'index.html' || item.trace_id === 'pl-trace-1'));
  ['turn:started', 'proof:ready', 'turn:completed', 'orchestrator:message'].forEach((ev) =>
    assert.ok(events.some((item) => item.event === ev), `missing event ${ev}`));
  assert.equal(decisions.length, 1);
  assert.equal(nodes.length, 1);
  assert.equal(activities.length, 1);
}

async function testPipelineFirstFallsBackToExecution() {
  // Codex P1: when chat is pipeline-first but the pipeline yields NO usable reply
  // (backend down, or a goal its Phase 0 did not answer), the execution engine
  // must still run before Ollama/node fallback — real goals must not slip through.
  delete process.env.TURN_RUNNER_PIPELINE_FIRST; // default = pipeline-first
  const spies = {};
  const { runner } = makeRunner(spies, {
    async requestPythonChatPayload() {
      spies.pipelineCalled = true;
      return {}; // pipeline produced nothing usable (no response/reply)
    },
  });

  const turn = await runner.runTurn({
    kind: 'chat',
    source: 'test',
    message: 'build a landing page',
    userId: 'user:test',
    tenantId: 'tenant:test',
  });

  assert.equal(spies.pipelineCalled, true, 'pipeline rung must run first');
  assert.equal(spies.execCalled, true, 'execution engine must run when pipeline yields nothing');
  assert.equal(turn.source, 'execution-engine', 'goal must reach the execution engine, not node fallback');
  assert.equal(turn.status, 'completed');
  assert.ok(turn.artifacts.some((item) => item.name === 'index.html'));
}

async function testLegacyOrderChat() {
  process.env.TURN_RUNNER_PIPELINE_FIRST = '0'; // restore execution-engine-first
  try {
    const spies = {};
    const { runner } = makeRunner(spies);
    const turn = await runner.runTurn({
      kind: 'chat',
      source: 'legacy',
      message: 'build a landing page',
      userId: 'user:test',
      tenantId: 'tenant:test',
    });
    assert.equal(turn.source, 'execution-engine', 'flag=0 must use legacy exec-first order');
    assert.equal(spies.execCalled, true, 'execution-engine must run under legacy order');
    assert.ok(!spies.pipelineCalled, 'pipeline not reached once exec-engine answered');
  } finally {
    delete process.env.TURN_RUNNER_PIPELINE_FIRST;
  }
}

async function testApprovalGate() {
  const spies = {};
  const { runner, events } = makeRunner(spies);
  const approvalTurn = await runner.runTurn({
    kind: 'task',
    source: 'money-mode-test',
    message: 'Money Mode: send outreach emails and accept paid client work',
    userId: 'user:test',
    tenantId: 'tenant:test',
  });
  assert.equal(approvalTurn.contract_version, 'turn_result_v1');
  assert.equal(approvalTurn.status, 'waiting_approval');
  assert.equal(approvalTurn.source, 'approval_gate');
  assert.equal(approvalTurn.approvals.length, 1);
  assert.ok(approvalTurn.approvals[0].required_for.includes('outreach'));
  assert.ok(approvalTurn.approvals[0].required_for.includes('paid_task'));
  assert.ok(approvalTurn.actions.some((action) => action.action === 'approval_gate'));
  assert.ok(events.some((item) => item.event === 'approval:required'));
  // Approval gate fires before any execution rung.
  assert.ok(!spies.execCalled && !spies.pipelineCalled, 'no execution before approval');
}

async function main() {
  await testPipelineFirstChat();
  await testPipelineFirstFallsBackToExecution();
  await testLegacyOrderChat();
  await testApprovalGate();
}

main()
  .then(() => {
    console.log('PASS turn runner C1/R1 pipeline-first + legacy + approval');
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
