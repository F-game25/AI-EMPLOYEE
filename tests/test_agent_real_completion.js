/**
 * Step 4 (coherence): agent activity is driven by REAL completion, not a timer.
 *  - completeTask() emits a VERIFIED completion carrying the real result.
 *  - completeTask() on an unknown id is a safe no-op.
 *  - the orchestrator learns from verified completions only (never timer ones).
 */
"use strict";

let passed = 0;
let failed = 0;
function assert(cond, msg) {
  if (cond) { console.log(`  ✓ ${msg}`); passed++; }
  else { console.error(`  ✗ ${msg}`); failed++; }
}

const agents = require("../backend/agents");

// completeTask emits a verified completion with the real result.
let evt = null;
agents.on("task:completed", (e) => { evt = e.task; });
agents.activateAgents(1);
const asg = agents.enqueueTask({ message: "real task", subsystem: "general" });
const ok = agents.completeTask(asg.taskId, { ok: true, result: { performance_score: 0.9 } });
assert(ok === true, "completeTask returns true for a known task");
assert(evt && evt.verified === true, "real completion is flagged verified:true");
assert(evt && evt.result && evt.result.performance_score === 0.9, "real result is carried on the event");

// failure path emits a verified task:failed.
let failEvt = null;
agents.on("task:failed", (e) => { failEvt = e.task; });
const asg2 = agents.enqueueTask({ message: "failing task", subsystem: "general" });
const ok2 = agents.completeTask(asg2.taskId, { ok: false, error: "boom" });
assert(ok2 === true, "completeTask returns true on failure path");
assert(failEvt && failEvt.verified === true && failEvt.error === "boom", "failure is verified with the real error");

// unknown id is a safe no-op (never fabricates).
assert(agents.completeTask("does-not-exist", { ok: true }) === false, "unknown id is a no-op");

console.log(`\nAgent real-completion: ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
