const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-run-routes-'));
const stateDir = path.join(tmpRoot, 'state');
const forgeDir = path.join(stateDir, 'forge');
const projectRoot = path.join(tmpRoot, 'project');

process.env.STATE_DIR = stateDir;
process.env.AI_EMPLOYEE_STATE_DIR = stateDir;
process.env.PYTHON_BACKEND_PORT = '9';

fs.mkdirSync(forgeDir, { recursive: true });
fs.mkdirSync(path.join(projectRoot, 'src'), { recursive: true });
fs.writeFileSync(path.join(projectRoot, 'package.json'), '{"scripts":{"test":"node --check src/app.js"}}\n');

function git(args) {
  const result = spawnSync('git', ['-C', projectRoot, ...args], { encoding: 'utf8' });
  assert.equal(result.status, 0, `git ${args.join(' ')} failed: ${result.stderr || result.stdout}`);
  return result.stdout.trim();
}

git(['init']);
git(['config', 'user.email', 'forge-route-test@example.com']);
git(['config', 'user.name', 'Forge Route Test']);
git(['add', 'package.json']);
git(['commit', '-m', 'seed project']);

const createForgeRouter = require('../backend/routes/forge');
const Database = require('../backend/node_modules/better-sqlite3');

const project = {
  id: 'project-test',
  name: 'Forge Route Test',
  target_type: 'internal_repo',
  root_path: projectRoot,
  path: projectRoot,
  allowed_write_paths: ['src', 'backend/routes'],
  write_access: true,
  package_type: 'node',
  verification_commands: ['node --check src/app.js'],
  policy_profile: 'test',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function writeJson(name, value) {
  fs.writeFileSync(path.join(forgeDir, name), JSON.stringify(value, null, 2));
}

function readJson(name) {
  return JSON.parse(fs.readFileSync(path.join(forgeDir, name), 'utf8'));
}

writeJson('projects.json', [project]);
writeJson('sessions.json', []);
writeJson('plans.json', []);
writeJson('actions.json', []);
writeJson('runs.json', []);

function makeRun(id, action) {
  const runAction = {
    id: `${id}-action`,
    type: 'write_file',
    label: `Write ${action.file_path}`,
    file_path: action.file_path,
    proposed_content: action.content,
    content: action.content,
    project_id: project.id,
    run_id: id,
    status: 'pending_approval',
    approval_required: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  return {
    id,
    run_id: id,
    project_id: project.id,
    goal: `test ${id}`,
    status: 'awaiting_approval',
    mode: 'supervised',
    provider: 'test',
    context_pack: {
      verification_commands: project.verification_commands,
      constraints: { approval_required_for_writes: true, staged_apply_required: true },
    },
    plan: { id: `${id}-plan`, verification_commands: project.verification_commands },
    actions: [runAction],
    patches: [{
      action_id: runAction.id,
      files: [action.file_path],
      policy: null,
      status: 'pending_approval',
    }],
    approvals: [],
    test_results: [],
    review: { status: 'policy_checked', summary: 'seeded test run' },
    workspace_path: path.join(forgeDir, 'runs', id, 'workspace'),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function saveRuns(runs) {
  writeJson('runs.json', runs);
}

function auth(req, _res, next) {
  req.user = { email: 'route-test@example.com' };
  next();
}

function invokeRoute(router, method, target, body) {
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
    body: body || {},
    headers: {},
  };

  return new Promise((resolve, reject) => {
    const res = {
      statusCode: 200,
      finished: false,
      status(code) {
        this.statusCode = code;
        return this;
      },
      json(payload) {
        this.finished = true;
        resolve({ status: this.statusCode, body: payload });
        return this;
      },
      send(payload) {
        this.finished = true;
        resolve({ status: this.statusCode, body: payload });
        return this;
      },
    };
    const handlers = layer.route.stack.map((stackItem) => stackItem.handle);
    let index = 0;
    const next = (err) => {
      if (err) {
        reject(err);
        return;
      }
      const handler = handlers[index++];
      if (!handler) {
        if (!res.finished) resolve({ status: res.statusCode, body: undefined });
        return;
      }
      try {
        const result = handler(req, res, next);
        if (handler.length < 3) {
          Promise.resolve(result).then(() => {
            if (!res.finished) next();
          }).catch(reject);
        } else if (result && typeof result.then === 'function') {
          result.catch(reject);
        }
      } catch (handlerErr) {
        reject(handlerErr);
      }
    };
    next();
  });
}

function assertPolicyRule(response, rule) {
  const rules = response.body.failures
    .flatMap((failure) => failure.policy?.violations || [])
    .map((violation) => violation.rule);
  assert(rules.includes(rule), `expected policy rule ${rule}, got ${rules.join(', ')}`);
}

(async () => {
  const router = createForgeRouter(auth);
  try {
    const created = await invokeRoute(router, 'POST', '/runs', {
      project_id: project.id,
      goal: 'inspect project and prepare a safe plan',
      provider: 'test',
    });
    assert.equal(created.status, 200);
    assert.equal(created.body.ok, true);
    assert(created.body.run_id.startsWith('run-'));
    assert.equal(created.body.run.project_id, project.id);
    assert.equal(created.body.run.context_pack.constraints.approval_required_for_writes, true);
    const status = await invokeRoute(router, 'GET', '/status');
    assert.equal(status.status, 200);
    assert.equal(status.body.persistence.backend, 'sqlite');
    const listed = await invokeRoute(router, 'GET', '/runs?limit=10');
    assert.equal(listed.status, 200);
    assert.equal(listed.body.persistence.backend, 'sqlite');
    assert(listed.body.runs.some((run) => run.run_id === created.body.run_id));
    const dbPath = path.join(forgeDir, 'forge_runs.db');
    assert.equal(fs.existsSync(dbPath), true);
    const db = new Database(dbPath, { readonly: true, fileMustExist: true });
    assert.equal(
      db.prepare('SELECT COUNT(*) AS count FROM forge_runs WHERE run_id = ?').get(created.body.run_id).count,
      1,
    );
    assert.equal(
      db.prepare("SELECT COUNT(*) AS count FROM sqlite_master WHERE type = 'table' AND name = 'forge_run_actions'").get().count,
      1,
    );
    db.close();

    saveRuns([makeRun('run-needs-approval', {
      file_path: 'src/app.js',
      content: 'module.exports = 1;\n',
    })]);
    const missingApproval = await invokeRoute(router, 'POST', '/runs/run-needs-approval/approve', {});
    assert.equal(missingApproval.status, 403);
    assert.equal(missingApproval.body.approval_required, true);
    assert.equal(fs.existsSync(path.join(projectRoot, 'src', 'app.js')), false);

    saveRuns([makeRun('run-path-escape', {
      file_path: '../outside.js',
      content: 'module.exports = 1;\n',
    })]);
    const escaped = await invokeRoute(router, 'POST', '/runs/run-path-escape/approve', { ownerApproved: true });
    assert.equal(escaped.status, 409);
    assert.equal(escaped.body.ok, false);
    // The current run policy rejects this traversal through write-scope enforcement.
    assertPolicyRule(escaped, 'write_scope');
    assert.equal(fs.existsSync(path.join(tmpRoot, 'outside.js')), false);

    saveRuns([makeRun('run-protected-path', {
      file_path: 'backend/routes/auth.js',
      content: 'module.exports = {};\n',
    })]);
    const protectedPath = await invokeRoute(router, 'POST', '/runs/run-protected-path/approve', { ownerApproved: true });
    assert.equal(protectedPath.status, 409);
    assert.equal(protectedPath.body.ok, false);
    assertPolicyRule(protectedPath, 'protected_path');

    saveRuns([makeRun('run-secret-path', {
      file_path: 'src/.env',
      content: 'TOKEN=secret\n',
    })]);
    const secretPath = await invokeRoute(router, 'POST', '/runs/run-secret-path/approve', { ownerApproved: true });
    assert.equal(secretPath.status, 409);
    assert.equal(secretPath.body.ok, false);
    assertPolicyRule(secretPath, 'secret_path');

    saveRuns([makeRun('run-happy-path', {
      file_path: 'src/app.js',
      content: 'module.exports = 1;\n',
    })]);
    const staged = await invokeRoute(router, 'POST', '/runs/run-happy-path/approve', { ownerApproved: true });
    assert.equal(staged.status, 200);
    assert.equal(staged.body.ok, true);
    assert.equal(staged.body.run.status, 'staged');
    assert.equal(staged.body.staged[0].workspace_meta.workspace_mode, 'git_worktree');
    const stagedFile = path.join(forgeDir, 'runs', 'run-happy-path', 'workspace', 'src', 'app.js');
    assert.equal(fs.readFileSync(stagedFile, 'utf8'), 'module.exports = 1;\n');
    const workspaceMeta = readJson(path.join('runs', 'run-happy-path', 'workspace', '.forge_workspace.json'));
    assert.equal(workspaceMeta.workspace_mode, 'git_worktree');
    assert.equal(Boolean(workspaceMeta.git_head), true);
    assert.equal(fs.existsSync(path.join(projectRoot, 'src', 'app.js')), false);

    const applyBeforeVerify = await invokeRoute(router, 'POST', '/runs/run-happy-path/apply', { ownerApproved: true });
    assert.equal(applyBeforeVerify.status, 409);
    assert.match(applyBeforeVerify.body.error, /verification must pass/i);

    saveRuns([makeRun('run-verify-allowlist', {
      file_path: 'src/app.js',
      content: 'module.exports = 1;\n',
    })]);
    const stagedForAllowlist = await invokeRoute(router, 'POST', '/runs/run-verify-allowlist/approve', { ownerApproved: true });
    assert.equal(stagedForAllowlist.status, 200);
    const blockedVerify = await invokeRoute(router, 'POST', '/runs/run-verify-allowlist/verify', {
      ownerApproved: true,
      commands: ['rm -rf src'],
    });
    assert.equal(blockedVerify.status, 409);
    assert.equal(blockedVerify.body.ok, false);
    assert.equal(blockedVerify.body.test_result.results[0].skipped, true);
    assert.match(blockedVerify.body.test_result.results[0].output, /allowlist/i);

    saveRuns([staged.body.run]);
    const passedVerify = await invokeRoute(router, 'POST', '/runs/run-happy-path/verify', {
      ownerApproved: true,
      commands: ['node --check src/app.js'],
    });
    assert.equal(passedVerify.status, 200);
    assert.equal(passedVerify.body.ok, true);
    assert.equal(passedVerify.body.run.status, 'verified');
    assert.equal(passedVerify.body.test_result.workspace_meta.workspace_mode, 'git_worktree');
    assert.equal(passedVerify.body.test_result.results[0].sandbox_type, 'process');
    assert.equal(passedVerify.body.test_result.results[0].sandbox_profile, 'code');
    assert(passedVerify.body.test_result.results[0].sandbox_audit);

    const applied = await invokeRoute(router, 'POST', '/runs/run-happy-path/apply', { ownerApproved: true });
    assert.equal(applied.status, 200);
    assert.equal(applied.body.ok, true);
    assert.equal(applied.body.run.status, 'applied');
    assert.equal(applied.body.run.final_report.workspace_meta.workspace_mode, 'git_worktree');
    assert.equal(fs.readFileSync(path.join(projectRoot, 'src', 'app.js'), 'utf8'), 'module.exports = 1;\n');

    const runs = readJson('runs.json');
    assert(runs.some((run) => run.id === 'run-happy-path' && run.status === 'applied'));

    saveRuns([makeRun('run-dirty-fallback', {
      file_path: 'src/dirty.js',
      content: 'module.exports = 2;\n',
    })]);
    const dirtyFallback = await invokeRoute(router, 'POST', '/runs/run-dirty-fallback/approve', { ownerApproved: true });
    assert.equal(dirtyFallback.status, 200);
    assert.equal(dirtyFallback.body.staged[0].workspace_meta.workspace_mode, 'directory_copy');
    assert.equal(dirtyFallback.body.staged[0].workspace_meta.fallback_reason, 'dirty_source_tree');
    console.log('[✓] forge run route contract tests passed');
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
})().catch((err) => {
  console.error(err);
  try { fs.rmSync(tmpRoot, { recursive: true, force: true }); } catch {}
  process.exitCode = 1;
});
