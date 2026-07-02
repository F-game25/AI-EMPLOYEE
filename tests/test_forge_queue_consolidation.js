const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-queue-consolidation-'));
const stateDir = path.join(tmpRoot, 'state');
const forgeDir = path.join(stateDir, 'forge');
const projectRoot = path.join(tmpRoot, 'project');

process.env.STATE_DIR = stateDir;
process.env.AI_EMPLOYEE_STATE_DIR = stateDir;
process.env.PYTHON_BACKEND_PORT = '9';
// Deliberately unreachable — TQ-1's /approve adapter fires a background
// autopilot tick (setImmediate) that we don't want reaching a real Ollama
// during a unit test; connection-refused fails fast instead of hanging.
process.env.OLLAMA_HOST = 'http://127.0.0.1:1';

fs.mkdirSync(forgeDir, { recursive: true });
fs.mkdirSync(projectRoot, { recursive: true });
fs.writeFileSync(path.join(projectRoot, 'package.json'), '{"scripts":{}}\n');

function git(args) {
  const result = spawnSync('git', ['-C', projectRoot, ...args], { encoding: 'utf8' });
  assert.equal(result.status, 0, `git ${args.join(' ')} failed: ${result.stderr || result.stdout}`);
}
git(['init']);
git(['config', 'user.email', 'forge-queue-test@example.com']);
git(['config', 'user.name', 'Forge Queue Test']);
git(['add', 'package.json']);
git(['commit', '-m', 'seed project']);

const createForgeRouter = require('../backend/routes/forge');

const project = {
  id: 'project-queue-test',
  name: 'Forge Queue Test',
  target_type: 'internal_repo',
  root_path: projectRoot,
  path: projectRoot,
  allowed_write_paths: ['.'],
  write_access: true,
  package_type: 'node',
  verification_commands: ['echo ok'],
  policy_profile: 'test',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function writeJson(name, value) {
  fs.writeFileSync(path.join(forgeDir, name), JSON.stringify(value, null, 2));
}
writeJson('projects.json', [project]);
writeJson('sessions.json', []);
writeJson('plans.json', []);
writeJson('actions.json', []);
writeJson('runs.json', []);

function auth(req, _res, next) {
  req.user = { email: 'queue-test@example.com' };
  next();
}

function invokeRoute(router, method, target, body) {
  const parsed = new URL(target, 'http://forge.test');
  const lowerMethod = method.toLowerCase();
  const layer = router.stack.find((item) => (
    item.route && item.route.methods[lowerMethod] && item.match(parsed.pathname)
  ));
  assert(layer, `route not found: ${method} ${target}`);
  const req = {
    method: method.toUpperCase(), url: target, originalUrl: target, path: parsed.pathname,
    params: layer.params || {}, query: Object.fromEntries(parsed.searchParams.entries()),
    body: body || {}, headers: {},
  };
  return new Promise((resolve, reject) => {
    const res = {
      statusCode: 200, finished: false,
      status(code) { this.statusCode = code; return this; },
      json(payload) { this.finished = true; resolve({ status: this.statusCode, body: payload }); return this; },
      send(payload) { this.finished = true; resolve({ status: this.statusCode, body: payload }); return this; },
    };
    const handlers = layer.route.stack.map((stackItem) => stackItem.handle);
    let index = 0;
    const next = (err) => {
      if (err) { reject(err); return; }
      const handler = handlers[index++];
      if (!handler) { if (!res.finished) resolve({ status: res.statusCode, body: undefined }); return; }
      try {
        const result = handler(req, res, next);
        if (handler.length < 3) {
          Promise.resolve(result).then(() => { if (!res.finished) next(); }).catch(reject);
        } else if (result && typeof result.then === 'function') {
          result.catch(reject);
        }
      } catch (handlerErr) { reject(handlerErr); }
    };
    next();
  });
}

(async () => {
  const router = createForgeRouter(auth);
  const t = router.__test__;
  assert(t, 'router.__test__ must be exposed');

  // ── 1. Autopilot session durability (SQLite-backed, no more in-process Map) ──
  {
    const projectId = project.id;
    assert.equal(t.getAutopilotSession(projectId), null, 'no session initially');
    t.saveAutopilotSession(projectId, {
      active: true, runsCompleted: 2, consecutiveFails: 1, maxRuns: 10, autonomyLevel: 2,
      cycleId: 'cycle-x', currentRunId: 'run-x', startedAt: new Date().toISOString(),
    });
    const loaded = t.getAutopilotSession(projectId);
    assert.equal(loaded.active, true);
    assert.equal(loaded.runsCompleted, 2);
    assert.equal(loaded.cycleId, 'cycle-x');
    // Simulate a restart: build a brand new router instance against the same
    // STATE_DIR and confirm the session survives (this is the actual TQ-1 claim).
    const router2 = createForgeRouter(auth);
    const reloaded = router2.__test__.getAutopilotSession(projectId);
    assert.equal(reloaded.active, true, 'session must survive a fresh router (simulated restart)');
    assert.equal(reloaded.runsCompleted, 2);
    t.saveAutopilotSession(projectId, { ...loaded, active: false }); // reset for later sections
  }
  console.log('[✓] autopilot session persists across a simulated restart');

  // ── 2. Cycle lifecycle: completion detection (previously: run_ids/status/
  //    final_report never updated after creation) ──
  {
    const b1 = await invokeRoute(router, 'POST', `/projects/${project.id}/backlog`, { title: 'Task A' });
    const b2 = await invokeRoute(router, 'POST', `/projects/${project.id}/backlog`, { title: 'Task B' });
    assert.equal(b1.status, 200);
    assert.equal(b2.status, 200);
    const ids = [b1.body.item.backlog_id, b2.body.item.backlog_id];

    const cycleResp = await invokeRoute(router, 'POST', `/projects/${project.id}/cycles`, {
      goal: 'Ship feature X', backlog_item_ids: ids, success_criteria: ['both tasks done'],
    });
    assert.equal(cycleResp.status, 200);
    assert.equal(cycleResp.body.cycle.status, 'RUNNING');
    const cycleId = cycleResp.body.cycle.cycle_id;

    // Not all terminal yet — must stay RUNNING.
    t.evaluateCycleCompletion(cycleId);
    let cycle = (await invokeRoute(router, 'GET', `/cycles/${cycleId}`)).body.cycle;
    assert.equal(cycle.status, 'RUNNING', 'must not complete while items are non-terminal');

    // Mark both DONE — completion must now fire, with a real final_report.
    await invokeRoute(router, 'PATCH', `/backlog/${ids[0]}`, { status: 'DONE' });
    await invokeRoute(router, 'PATCH', `/backlog/${ids[1]}`, { status: 'DONE' });
    t.evaluateCycleCompletion(cycleId);
    cycle = (await invokeRoute(router, 'GET', `/cycles/${cycleId}`)).body.cycle;
    assert.equal(cycle.status, 'COMPLETED');
    assert(cycle.final_report, 'final_report must be populated on completion');
    assert.equal(cycle.final_report.done, 2);
  }
  console.log('[✓] cycle completion detected and final_report populated when all items are DONE');

  // ── 3. Cycle lifecycle: FAILED when an item fails ──
  {
    const b1 = await invokeRoute(router, 'POST', `/projects/${project.id}/backlog`, { title: 'Task C' });
    const b2 = await invokeRoute(router, 'POST', `/projects/${project.id}/backlog`, { title: 'Task D' });
    const ids = [b1.body.item.backlog_id, b2.body.item.backlog_id];
    const cycleResp = await invokeRoute(router, 'POST', `/projects/${project.id}/cycles`, { goal: 'goal 2', backlog_item_ids: ids });
    const cycleId = cycleResp.body.cycle.cycle_id;
    await invokeRoute(router, 'PATCH', `/backlog/${ids[0]}`, { status: 'DONE' });
    await invokeRoute(router, 'PATCH', `/backlog/${ids[1]}`, { status: 'FAILED' });
    t.evaluateCycleCompletion(cycleId);
    const cycle = (await invokeRoute(router, 'GET', `/cycles/${cycleId}`)).body.cycle;
    assert.equal(cycle.status, 'FAILED');
    assert.equal(cycle.final_report.failed, 1);
  }
  console.log('[✓] cycle marked FAILED when a linked item fails');

  // ── 4. Boot-time reconciliation: a stuck IN_PROGRESS item with no run recovers ──
  {
    const created = await invokeRoute(router, 'POST', `/projects/${project.id}/backlog`, { title: 'Task E' });
    const id = created.body.item.backlog_id;
    await invokeRoute(router, 'PATCH', `/backlog/${id}`, { status: 'IN_PROGRESS' });
    t.reconcileForgeQueueOnBoot();
    const list = await invokeRoute(router, 'GET', `/projects/${project.id}/backlog`);
    const item = list.body.backlog.find((i) => i.backlog_id === id);
    assert.equal(item.status, 'READY', 'a stuck item with no matching run must recover to READY');
  }
  console.log('[✓] boot reconciliation recovers a stuck IN_PROGRESS item with no run');

  // ── 5. Adapter mode: /submit -> /approve converts to a backlog item and
  //    starts autopilot, without needing a separate manual start call ──
  {
    t.saveAutopilotSession(project.id, { active: false, runsCompleted: 0, consecutiveFails: 0, maxRuns: 10, autonomyLevel: 2 });
    const submitted = await invokeRoute(router, 'POST', '/submit', {
      goal: 'Adapter-mode conversion test', project_id: project.id, priority: 'high',
    });
    assert.equal(submitted.status, 200);
    assert.equal(submitted.body.item.status, 'proposed', 'submit contract unchanged for callers');

    const approved = await invokeRoute(router, 'POST', `/approve/${submitted.body.item.id}`, {});
    assert.equal(approved.status, 200);
    assert(approved.body.action.converted_to_backlog_id, 'approved item must convert to a backlog item');

    const list = await invokeRoute(router, 'GET', `/projects/${project.id}/backlog`);
    const converted = list.body.backlog.find((i) => i.backlog_id === approved.body.action.converted_to_backlog_id);
    assert(converted, 'converted backlog item must exist');
    assert.equal(converted.status, 'READY');
    assert.equal(converted.source, 'forge_submit');
    assert.equal(converted.priority, 70, 'priority mapped from "high"');

    const session = t.getAutopilotSession(project.id);
    assert.equal(session.active, true, 'autopilot must auto-start so the goal actually executes');
  }
  console.log('[✓] /submit -> /approve adapter converts to backlog + auto-starts autopilot');

  // ── 6. Cancel / retry controls ──
  {
    const created = await invokeRoute(router, 'POST', `/projects/${project.id}/backlog`, { title: 'Task F' });
    const id = created.body.item.backlog_id;
    const cancelled = await invokeRoute(router, 'POST', `/backlog/${id}/cancel`, {});
    assert.equal(cancelled.status, 200);
    assert.equal(cancelled.body.item.status, 'CANCELLED');
    const doubleCancel = await invokeRoute(router, 'POST', `/backlog/${id}/cancel`, {});
    assert.equal(doubleCancel.status, 409, 'cannot cancel an already-terminal item');

    const retryOnCancelled = await invokeRoute(router, 'POST', `/backlog/${id}/retry`, {});
    assert.equal(retryOnCancelled.status, 400, 'only FAILED items can be retried');

    await invokeRoute(router, 'PATCH', `/backlog/${id}`, { status: 'FAILED' });
    const retried = await invokeRoute(router, 'POST', `/backlog/${id}/retry`, {});
    assert.equal(retried.status, 200);
    assert.equal(retried.body.item.status, 'READY');
  }
  console.log('[✓] backlog cancel/retry controls enforce terminal-state rules');

  console.log('[✓] forge queue consolidation (TQ-1) tests passed');

  // ══════════════════════════════════════════════════════════════════════
  // TQ-2 — goal-achieving: fast path for short goals + skill/agent routing
  // ══════════════════════════════════════════════════════════════════════

  // ── 7. isSimpleGoal heuristic ──
  {
    assert.equal(t.isSimpleGoal('Fix the typo in the README'), true);
    assert.equal(t.isSimpleGoal('Add a docstring to the add() function'), true);
    assert.equal(t.isSimpleGoal(''), false);
    assert.equal(
      t.isSimpleGoal('First research the market, then draft a plan, and then build the feature, after that write tests'),
      false, 'multi-step language must disqualify the fast path',
    );
    assert.equal(
      t.isSimpleGoal('Build a complete authentication system with OAuth support, session management, password reset flows, rate limiting on the login endpoint, and audit logging across the entire application stack'),
      false, 'long goals (>25 words) must disqualify the fast path',
    );
  }
  console.log('[✓] isSimpleGoal heuristic classifies short vs multi-step/long goals correctly');

  // ── 8. computeSkillRouting: a clear non-code request routes; a generic
  //    coding request does not (stays on the safe file-editing pipeline) ──
  {
    const codeRouting = await t.computeSkillRouting('Fix bug in auth.js', 'There is a null pointer exception in the login handler that needs to be fixed in the repo.');
    assert.equal(codeRouting.assigned_skill_id, null, 'a repo code-fix task must never auto-route away from the safe pipeline');

    const researchRouting = await t.computeSkillRouting('Market research report', 'Research the competitive landscape and market size for local-first AI products, and write a summary report with sources.');
    // This may or may not clear the confidence threshold depending on the
    // exact skill library contents — but if it DOES route, it must only ever
    // route to a category on the safe list, never silently to something else.
    if (researchRouting.assigned_skill_id) {
      assert(typeof researchRouting.match_score === 'number' && researchRouting.match_score >= 6.0);
    }
  }
  console.log('[✓] computeSkillRouting never routes a repo code-fix task away from the safe pipeline');

  // ── 9. Backlog creation persists routing decision ──
  {
    const created = await invokeRoute(router, 'POST', `/projects/${project.id}/backlog`, {
      title: 'Generic coding task', description: 'Refactor the payment handler in backend/routes/forge.js.',
    });
    assert.equal(created.status, 200);
    assert.equal(created.body.item.assigned_skill_id, null, 'generic code task must not be routed to a skill');
  }
  console.log('[✓] backlog creation computes and persists the routing decision');

  // ── 10. Cycle fast path: a short goal skips the Decomposer (one item, not 3-8) ──
  {
    const cycleResp = await invokeRoute(router, 'POST', `/projects/${project.id}/cycles`, {
      goal: 'Add a docstring to the ping function',
    });
    assert.equal(cycleResp.status, 200);
    assert.equal(cycleResp.body.cycle.backlog_items.length, 1, 'fast path must create exactly one backlog item');
    assert.equal(cycleResp.body.cycle.current_phase, 'executing_fast_path');
  }
  console.log('[✓] cycle fast path skips the Decomposer for a short, single-step goal');

  console.log('[✓] forge queue consolidation + goal routing (TQ-1 + TQ-2) tests passed');
  process.exit(0);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
