const assert = require('assert');

process.env.STATE_DIR = process.env.STATE_DIR || require('os').tmpdir();
process.env.PYTHON_BACKEND_PORT = process.env.PYTHON_BACKEND_PORT || '9';

const createHealthRouter = require('../backend/routes/health');

// Regression: POST /api/system/halt and /api/system/restart used to reference
// `runtimeState.agents`, a property that is never set anywhere in server.js.
// Any call threw "Cannot read properties of undefined (reading 'map')",
// crashing the request (and, observed live, taking the whole Node process down).
// The real agent lifecycle lives in backend/agents/index.js (stopAllAgents /
// activateAgents) — routes must call those, not a phantom runtimeState.agents.

function findHandler(router, path, method) {
  const layer = router.stack.find((l) => l.route && l.route.path === path && l.route.methods[method]);
  assert(layer, `route ${method.toUpperCase()} ${path} not found`);
  return layer.route.stack[layer.route.stack.length - 1].handle;
}

function mockRes() {
  const res = { statusCode: 200 };
  res.status = (code) => { res.statusCode = code; return res; };
  res.json = (body) => { res.body = body; return res; };
  return res;
}

let haltCalls = 0;
let activateCalls = 0;
let halted = false;
const broadcasts = [];

const router = createHealthRouter({
  requireAuth: (req, res, next) => next(),
  validate: () => true,
  SCHEMAS: { systemHalt: {} },
  broadcaster: { broadcast: (event, data) => broadcasts.push({ event, data }) },
  setSystemHalted: (v) => { halted = v; },
  getSystemHalted: () => halted,
  stopAllAgents: (reason) => { haltCalls += 1; return { cancelledTasks: 0, runningAgents: 0, reason }; },
  activateAgents: () => { activateCalls += 1; return { desiredActiveAgents: 3, runningAgents: 3 }; },
});

const haltHandler = findHandler(router, '/api/system/halt', 'post');
const resHalt = mockRes();
haltHandler({ body: {} }, resHalt);
assert.equal(haltCalls, 1, 'halt must call the real stopAllAgents, not a phantom runtimeState.agents');
assert.equal(halted, true);
assert.equal(resHalt.body.ok, true);
assert.equal(resHalt.body.halted, true);

const restartHandler = findHandler(router, '/api/system/restart', 'post');
const resRestart = mockRes();
restartHandler({ body: {} }, resRestart);
assert.equal(activateCalls, 1, 'restart must call the real activateAgents, not a phantom runtimeState.agents');
assert.equal(halted, false);
assert.equal(resRestart.body.ok, true);
assert.equal(resRestart.body.halted, false);

assert(broadcasts.some((b) => b.event === 'system:halted' && b.data.halted === true));
assert(broadcasts.some((b) => b.event === 'system:halted' && b.data.halted === false));

console.log('[✓] system halt/restart routes call the real agent lifecycle (no phantom runtimeState.agents)');
