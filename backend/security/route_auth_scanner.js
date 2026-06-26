'use strict';

/**
 * route_auth_scanner.js — Static Express route-auth coverage scanner.
 *
 * Parses backend/server.js and backend/routes/*.js for route registrations
 * and checks that every sensitive route has auth middleware in its chain.
 * Loads sensitive prefixes and public allowlist from runtime/config/security.yml.
 * Fail-closed: if config is absent or unparseable, every route is treated as
 * sensitive (deny-by-default).
 *
 * Usage:
 *   node backend/security/route_auth_scanner.js
 *   node backend/security/route_auth_scanner.js --json   # emit JSON report
 *
 * Exit codes:
 *   0  all sensitive routes are gated (or explicitly allowlisted)
 *   1  one or more sensitive routes lack auth (or config load failed)
 */

const fs   = require('fs');
const path = require('path');

// ── Constants ─────────────────────────────────────────────────────────────────

const REPO_ROOT = path.resolve(__dirname, '..', '..');

// Auth guard identifiers recognised in middleware chains.
const AUTH_GUARDS = new Set([
  'requireAuth',
  'requireScope',
  'requireRole',
  'localhostOrAuth',
  'withRole',
  'withPermission',
  'injectRole',
]);

// Regex: locate route registrations in the form
//   app.METHOD('/path', ...)  or  app.use('/path', ...)
//   router.METHOD('/path', ...) or router.use('/path', ...)
// Captures: (obj: app|router, method, path)
// The full statement is extracted separately using brace counting for accuracy.
const ROUTE_RE = /\b(app|router)\.(get|post|put|patch|delete|use)\(\s*(['"`])([^'"`]+)\3/g;

// ── Config loading ────────────────────────────────────────────────────────────

/**
 * Load route_auth config from security.yml.
 * Returns { public_allowlist: string[], sensitive_prefixes: string[] }.
 * On any failure (missing file, missing keys, parse error) returns DEFAULTS
 * and sets result.configMissing = true — caller treats all routes as sensitive.
 */
function loadConfig() {
  const DEFAULT_SENSITIVE = [
    'secrets', 'remote-compute', 'compute', 'sandbox', 'forge',
    'evolution', 'deployment', 'orders', 'marketplace', 'memory', 'rag',
  ];
  const fallback = {
    public_allowlist: [],
    sensitive_prefixes: DEFAULT_SENSITIVE,
    configMissing: true,
    configPath: null,
  };

  const ymlPath = path.join(REPO_ROOT, 'runtime', 'config', 'security.yml');
  if (!fs.existsSync(ymlPath)) return { ...fallback, configPath: ymlPath };

  const raw = fs.readFileSync(ymlPath, 'utf8');

  // Minimal YAML extraction — avoid adding a dependency.
  // We only need two list keys under the `route_auth:` block.
  const section = extractYmlSection(raw, 'route_auth');
  if (!section) return { ...fallback, configPath: ymlPath };

  const publicList  = extractYmlList(section, 'public_allowlist');
  const prefixList  = extractYmlList(section, 'sensitive_prefixes');

  if (!publicList && !prefixList) return { ...fallback, configPath: ymlPath };

  return {
    public_allowlist:    publicList  ?? [],
    sensitive_prefixes:  prefixList  ?? DEFAULT_SENSITIVE,
    configMissing: false,
    configPath: ymlPath,
  };
}

/**
 * Extract the indented block under a top-level YAML key.
 * e.g. extractYmlSection(raw, 'route_auth') → text of that block.
 */
function extractYmlSection(raw, key) {
  const start = raw.search(new RegExp(`^${key}:\\s*$`, 'm'));
  if (start === -1) return null;
  const after = raw.slice(start + key.length + 1);
  // Collect lines that are indented (child lines) or blank.
  const lines = after.split('\n');
  const block = [];
  for (const line of lines) {
    if (line === '' || /^\s/.test(line)) {
      block.push(line);
    } else {
      break; // top-level key encountered → end of block
    }
  }
  return block.join('\n');
}

/**
 * Extract a YAML list under a given key within a pre-extracted section block.
 * Supports both flow `[a, b]` and block `- item` styles.
 */
function extractYmlList(block, key) {
  const keyIdx = block.search(new RegExp(`^\\s+${key}:`, 'm'));
  if (keyIdx === -1) return null;

  const afterKey = block.slice(keyIdx);
  // Flow style: key: [item1, item2]
  const flowMatch = afterKey.match(new RegExp(`${key}:\\s*\\[([^\\]]*)]`));
  if (flowMatch) {
    return flowMatch[1].split(',').map((s) => s.replace(/['"]/g, '').trim()).filter(Boolean);
  }

  // Block style: key:\n  - item
  const blockMatch = afterKey.match(new RegExp(`${key}:[\\s\\S]*?(?=\\n\\s+\\w|$)`));
  if (!blockMatch) return null;
  const items = [...blockMatch[0].matchAll(/^\s+-\s+["']?([^"'\n]+)["']?\s*$/gm)];
  return items.map((m) => m[1].trim()).filter(Boolean);
}

// ── Source file collection ────────────────────────────────────────────────────

function collectSourceFiles() {
  const files = [];
  const serverJs = path.join(REPO_ROOT, 'backend', 'server.js');
  if (fs.existsSync(serverJs)) files.push(serverJs);

  const routesDir = path.join(REPO_ROOT, 'backend', 'routes');
  if (fs.existsSync(routesDir)) {
    for (const f of fs.readdirSync(routesDir)) {
      if (f.endsWith('.js')) files.push(path.join(routesDir, f));
    }
  }
  return files;
}

// ── Route extraction ──────────────────────────────────────────────────────────

/**
 * Extract route registrations from a source file.
 * Returns array of { file, line, method, routePath, hasAuth, rawChain }.
 */
function extractRoutes(filePath) {
  const src = fs.readFileSync(filePath, 'utf8');
  const lines = src.split('\n');
  const results = [];

  // Build a line-offset lookup so we can map match position → line number.
  const offsets = buildLineOffsets(lines);

  ROUTE_RE.lastIndex = 0;
  let match;
  while ((match = ROUTE_RE.exec(src)) !== null) {
    const [, , method, , routePath] = match;
    const lineNum = positionToLine(match.index, offsets);

    // Extract the full statement from the match position by counting parentheses.
    // This captures the complete argument list including nested factory calls:
    //   app.use('/api/forge', require('./routes/forge')(requireAuth, ...))
    const stmtText = extractStatement(src, match.index);
    const hasAuth = containsAuthGuard(stmtText);

    results.push({
      file: path.relative(REPO_ROOT, filePath),
      line: lineNum,
      method: method.toUpperCase(),
      routePath,
      hasAuth,
      rawChain: stmtText.slice(0, 120), // truncate for report readability
    });
  }

  return results;
}

/**
 * Extract the full statement text starting at startPos by counting parentheses.
 * Handles nested calls like app.use('/x', require('./r')(requireAuth, opts)).
 * Stops when the outermost `(` is closed.  Returns the raw text slice.
 */
function extractStatement(src, startPos) {
  let depth = 0;
  let started = false;
  for (let i = startPos; i < src.length; i++) {
    const ch = src[i];
    if (ch === '(') { depth++; started = true; }
    else if (ch === ')') {
      depth--;
      if (started && depth === 0) return src.slice(startPos, i + 1);
    }
    // Stop at semicolon at top level (safety valve for malformed source).
    if (started && depth === 0 && ch === ';') return src.slice(startPos, i + 1);
  }
  // Fallback: return up to 300 chars from match position.
  return src.slice(startPos, startPos + 300);
}

/**
 * Check whether an argument string references any known auth guard.
 */
function containsAuthGuard(str) {
  // Identifier-boundary match so a guard name inside another word, a comment, or
  // a string literal can't produce a false "protected" pass in a security gate.
  for (const guard of AUTH_GUARDS) {
    if (new RegExp(`\\b${guard}\\b`).test(str)) return true;
  }
  return false;
}

function buildLineOffsets(lines) {
  const offsets = [0];
  let pos = 0;
  for (const line of lines) {
    pos += line.length + 1; // +1 for '\n'
    offsets.push(pos);
  }
  return offsets;
}

function positionToLine(pos, offsets) {
  let lo = 0, hi = offsets.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (offsets[mid] <= pos) lo = mid; else hi = mid - 1;
  }
  return lo + 1; // 1-indexed
}

// ── Sensitivity classification ────────────────────────────────────────────────

/**
 * Normalise a route path to a segment list for prefix matching.
 * '/api/secrets/rotate' → ['api', 'secrets', 'rotate']
 */
function routeSegments(rp) {
  return rp.replace(/^\/+/, '').split('/').filter(Boolean);
}

/**
 * Returns true if the route path contains any sensitive prefix as a segment
 * sequence.  Supports two forms:
 *   - bare word, e.g. "secrets"  → matches /api/secrets, /api/secrets/list, etc.
 *   - full prefix, e.g. "api/secrets" → matched from the start of the path.
 *
 * For bare-word prefixes (no leading slash, no slash in the word) we scan all
 * sub-sequences of the route so that /api/secrets/list matches prefix "secrets".
 * For multi-segment prefixes we require alignment from the path start.
 */
function isSensitive(routePath, sensitivePrefixes) {
  const segs = routeSegments(routePath);
  for (const prefix of sensitivePrefixes) {
    const pSegs = routeSegments(prefix);
    if (pSegs.length === 1) {
      // bare word: match any segment in the route path
      if (segs.includes(pSegs[0])) return true;
    } else {
      // multi-segment: match from position 0
      if (pSegs.every((p, i) => segs[i] === p)) return true;
    }
  }
  return false;
}

/**
 * Returns true if the route path is explicitly allowed as public.
 * Supports exact matches and prefix/* patterns.
 * Comparison is normalised (leading slash optional).
 */
function isAllowlisted(routePath, publicAllowlist) {
  const norm = (p) => '/' + p.replace(/^\/+/, '');
  const rn = norm(routePath);
  for (const entry of publicAllowlist) {
    const en = norm(entry);
    if (en.endsWith('*')) {
      if (rn.startsWith(en.slice(0, -1))) return true;
    } else {
      if (rn === en) return true;
    }
  }
  return false;
}

// ── Main scanner ──────────────────────────────────────────────────────────────

function run() {
  const emitJson = process.argv.includes('--json');
  const cfg = loadConfig();

  // Warn loudly if config is missing (fail-closed: all routes treated as sensitive).
  const warnings = [];
  if (cfg.configMissing) {
    warnings.push(
      `Config key route_auth not found in ${cfg.configPath || 'security.yml'} — ` +
      'using built-in defaults (fail-closed: all /api/ routes treated as sensitive). ' +
      'Add route_auth.public_allowlist and route_auth.sensitive_prefixes to security.yml.'
    );
  }

  const sourceFiles = collectSourceFiles();
  const allRoutes   = [];
  for (const f of sourceFiles) {
    try {
      allRoutes.push(...extractRoutes(f));
    } catch (err) {
      warnings.push(`Parse error in ${path.relative(REPO_ROOT, f)}: ${err.message}`);
    }
  }

  // Classify each route.
  const flagged   = []; // sensitive + not allowlisted + no auth
  const protected_  = []; // sensitive + has auth
  const allowlisted = []; // sensitive prefix match but explicitly public
  const benign    = []; // not sensitive

  for (const route of allRoutes) {
    const sensitive = isSensitive(route.routePath, cfg.sensitive_prefixes);
    if (!sensitive) { benign.push(route); continue; }

    if (isAllowlisted(route.routePath, cfg.public_allowlist)) {
      allowlisted.push(route);
    } else if (route.hasAuth) {
      protected_.push(route);
    } else {
      flagged.push(route);
    }
  }

  // ── Report ────────────────────────────────────────────────────────────────
  const report = {
    generated_at:       new Date().toISOString(),
    config_path:        cfg.configPath,
    config_missing:     cfg.configMissing,
    sensitive_prefixes: cfg.sensitive_prefixes,
    public_allowlist:   cfg.public_allowlist,
    warnings,
    summary: {
      total_routes:      allRoutes.length,
      sensitive:         protected_.length + allowlisted.length + flagged.length,
      protected:         protected_.length,
      allowlisted_public: allowlisted.length,
      flagged:           flagged.length,
      benign:            benign.length,
    },
    flagged_routes:     flagged,
    allowlisted_routes: allowlisted,
  };

  if (emitJson) {
    process.stdout.write(JSON.stringify(report, null, 2) + '\n');
  } else {
    printHumanReport(report, flagged, protected_, allowlisted, warnings);
  }

  // Non-zero exit if any sensitive routes are ungated.
  if (flagged.length > 0 || cfg.configMissing) {
    process.exit(1);
  }
}

function printHumanReport(report, flagged, protected_, allowlisted, warnings) {
  const hr = '─'.repeat(72);
  console.log('\n' + hr);
  console.log('ROUTE AUTH SCANNER — AI-EMPLOYEE');
  console.log(hr);
  console.log(`Generated : ${report.generated_at}`);
  console.log(`Config    : ${report.config_path || 'NOT FOUND'}`);
  if (report.config_missing) console.log('⚠  Config key "route_auth" missing — fail-closed defaults active');

  console.log('\nSensitive prefixes: ' + report.sensitive_prefixes.join(', '));
  console.log('Public allowlist  : ' + (report.public_allowlist.length ? report.public_allowlist.join(', ') : '(empty)'));

  console.log('\n' + hr);
  console.log('SUMMARY');
  console.log(hr);
  const s = report.summary;
  console.log(`Total routes scanned   : ${s.total_routes}`);
  console.log(`Sensitive routes       : ${s.sensitive}`);
  console.log(`  Protected (has auth) : ${s.protected}`);
  console.log(`  Allowlisted public   : ${s.allowlisted_public}`);
  console.log(`  FLAGGED (no auth)    : ${s.flagged}`);
  console.log(`Non-sensitive routes   : ${s.benign}`);

  if (warnings.length) {
    console.log('\n' + hr);
    console.log('WARNINGS');
    console.log(hr);
    for (const w of warnings) console.log('⚠  ' + w);
  }

  if (flagged.length === 0) {
    console.log('\n✓ No ungated sensitive routes found.\n');
    return;
  }

  console.log('\n' + hr);
  console.log(`FLAGGED ROUTES (${flagged.length}) — SENSITIVE AND LACKING AUTH`);
  console.log(hr);
  for (const r of flagged) {
    console.log(`  ${r.method.padEnd(7)} ${r.routePath}`);
    console.log(`           ${r.file}:${r.line}`);
    if (r.rawChain) console.log(`           chain: ${r.rawChain}`);
  }

  if (allowlisted.length) {
    console.log('\n' + hr);
    console.log(`ALLOWLISTED PUBLIC ROUTES (${allowlisted.length})`);
    console.log(hr);
    for (const r of allowlisted) {
      console.log(`  ${r.method.padEnd(7)} ${r.routePath}  (${r.file}:${r.line})`);
    }
  }

  console.log('\n' + hr);
  console.log(`EXIT: non-zero (${flagged.length} flagged route(s) require attention)`);
  console.log(hr + '\n');
}

run();
