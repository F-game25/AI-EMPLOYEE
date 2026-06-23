const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-skills-route-'));
const stateDir = path.join(tmpRoot, 'state');
process.env.STATE_DIR = stateDir;
process.env.AI_EMPLOYEE_STATE_DIR = stateDir;
fs.mkdirSync(path.join(stateDir, 'forge'), { recursive: true });

const createForgeRouter = require('../backend/routes/forge');

function auth(req, _res, next) {
  req.user = { email: 'skills-route-test@example.com' };
  next();
}

function invokeRoute(router, method, target) {
  const parsed = new URL(target, 'http://forge.test');
  const lowerMethod = method.toLowerCase();
  const layer = router.stack.find((item) => (
    item.route &&
    item.route.methods[lowerMethod] &&
    item.match(parsed.pathname)
  ));
  assert(layer, `route not found: ${method} ${target}`);

  const req = {
    method: method.toUpperCase(),
    url: target,
    originalUrl: target,
    path: parsed.pathname,
    params: layer.params || {},
    query: Object.fromEntries(parsed.searchParams.entries()),
    body: {},
    headers: {},
  };

  return new Promise((resolve, reject) => {
    const res = {
      statusCode: 200,
      status(code) { this.statusCode = code; return this; },
      json(payload) { resolve({ status: this.statusCode, body: payload }); return this; },
      send(payload) { resolve({ status: this.statusCode, body: payload }); return this; },
    };
    const handlers = layer.route.stack.map((stackItem) => stackItem.handle);
    let index = 0;
    const next = (err) => {
      if (err) return reject(err);
      const handler = handlers[index++];
      if (!handler) return resolve({ status: res.statusCode, body: undefined });
      try {
        const result = handler(req, res, next);
        if (handler.length < 3) Promise.resolve(result).then(() => {}).catch(reject);
      } catch (handlerErr) {
        reject(handlerErr);
      }
    };
    next();
  });
}

(async () => {
  const router = createForgeRouter(auth);
  const res = await invokeRoute(router, 'GET', '/skills');
  assert.equal(res.status, 200);
  assert.equal(res.body.ok, true);
  assert.equal(res.body.source, 'skills_library');
  assert(res.body.batch1_count >= 40, `expected batch1 skills, got ${res.body.batch1_count}`);
  assert(res.body.batch2_count >= 40, `expected batch2 skills, got ${res.body.batch2_count}`);
  assert(res.body.batch3_count >= 40, `expected batch3 skills, got ${res.body.batch3_count}`);
  assert(res.body.batch4_count >= 40, `expected batch4 skills, got ${res.body.batch4_count}`);
  assert(res.body.batch5_count >= 40, `expected batch5 skills, got ${res.body.batch5_count}`);
  assert(res.body.batch6_count >= 40, `expected batch6 skills, got ${res.body.batch6_count}`);
  assert(res.body.batch7_count >= 40, `expected batch7 skills, got ${res.body.batch7_count}`);
  assert(res.body.production_batch_count >= 280, `expected production batch skills, got ${res.body.production_batch_count}`);
  const batch1Skill = res.body.skills.find((item) => item.id === 'skill_registry_validator');
  assert(batch1Skill, 'skill_registry_validator missing');
  assert.equal(batch1Skill.skill_id, 'skill_registry_validator');
  assert.equal(batch1Skill.ui_metadata.wired, true);
  const batch2Skill = res.body.skills.find((item) => item.id === 'paid_task_evaluator');
  assert(batch2Skill, 'paid_task_evaluator missing');
  assert.equal(batch2Skill.skill_id, 'paid_task_evaluator');
  assert.equal(batch2Skill.ui_metadata.wired, true);
  assert.equal(batch2Skill.ui_metadata.batch, 'batch_2');
  const batch3Skill = res.body.skills.find((item) => item.id === 'seo_opportunity_auditor');
  assert(batch3Skill, 'seo_opportunity_auditor missing');
  assert.equal(batch3Skill.skill_id, 'seo_opportunity_auditor');
  assert.equal(batch3Skill.ui_metadata.wired, true);
  assert.equal(batch3Skill.ui_metadata.batch, 'batch_3');
  const batch4Skill = res.body.skills.find((item) => item.id === 'api_integration_contract_tester');
  assert(batch4Skill, 'api_integration_contract_tester missing');
  assert.equal(batch4Skill.skill_id, 'api_integration_contract_tester');
  assert.equal(batch4Skill.ui_metadata.wired, true);
  assert.equal(batch4Skill.ui_metadata.batch, 'batch_4');
  const batch5Skill = res.body.skills.find((item) => item.id === 'cold_email_draft_reviewer');
  assert(batch5Skill, 'cold_email_draft_reviewer missing');
  assert.equal(batch5Skill.skill_id, 'cold_email_draft_reviewer');
  assert.equal(batch5Skill.ui_metadata.wired, true);
  assert.equal(batch5Skill.ui_metadata.batch, 'batch_5');
  const batch6Skill = res.body.skills.find((item) => item.id === 'workflow_management_auditor');
  assert(batch6Skill, 'workflow_management_auditor missing');
  assert.equal(batch6Skill.skill_id, 'workflow_management_auditor');
  assert.equal(batch6Skill.ui_metadata.wired, true);
  assert.equal(batch6Skill.ui_metadata.batch, 'batch_6');
  const batch7Skill = res.body.skills.find((item) => item.id === 'shell_command_execution_reviewer');
  assert(batch7Skill, 'shell_command_execution_reviewer missing');
  assert.equal(batch7Skill.skill_id, 'shell_command_execution_reviewer');
  assert.equal(batch7Skill.ui_metadata.wired, true);
  assert.equal(batch7Skill.ui_metadata.batch, 'batch_7');
})();
