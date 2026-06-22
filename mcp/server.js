#!/usr/bin/env node
/**
 * Nexus / AscendForge — MCP brain-connector (stdio).
 *
 * A thin tool/adapter layer (no business logic): every tool calls an existing
 * backend HTTP route, which already runs orchestrator → skills → tools. Lets
 * Claude (the brain) read system state and PROPOSE work (queue it for human
 * approval). It cannot execute work directly — that stays gated behind the
 * dashboard approval + the server-side dispatcher.
 *
 * Security:
 *  - Least privilege: a `read` token for read tools, a `task-emit` token for the
 *    single write tool (forge_submit). No admin token is ever used.
 *  - Secrets (JWT_SECRET_KEY, minted tokens) are never written to stdout/stderr.
 *  - All MCP protocol traffic is on stdout; ALL logging goes to stderr.
 *  - Deny-by-default at the server: an under-scoped call returns 403, surfaced
 *    verbatim as a tool error.
 *
 * Connection / auth resolution (no hardcoded values):
 *  - Backend URL:  NEXUS_BACKEND_URL  →  ~/.ai-employee/run/runtime-lock.json (ports.node)
 *                  →  http://127.0.0.1:${NEXUS_BACKEND_PORT||8787}
 *  - Tokens:       NEXUS_SERVICE_TOKEN_READ / _EMIT  →  NEXUS_SERVICE_TOKEN (both)
 *                  →  mint via POST /api/auth/service-token using JWT_SECRET_KEY
 *                     (env or ~/.ai-employee/.env). Fails closed if none available.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { ListToolsRequestSchema, CallToolRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const log = (...a) => console.error('[nexus-mcp]', ...a); // stderr only

// ── Connection resolution ─────────────────────────────────────────────────────
function resolveBaseUrl() {
  if (process.env.NEXUS_BACKEND_URL) return process.env.NEXUS_BACKEND_URL.replace(/\/+$/, '');
  const runDir = process.env.RUN_DIR || path.join(os.homedir(), '.ai-employee', 'run');
  try {
    const lock = JSON.parse(fs.readFileSync(path.join(runDir, 'runtime-lock.json'), 'utf8'));
    const port = Number(lock?.ports?.node);
    if (Number.isFinite(port) && port > 0) return `http://127.0.0.1:${port}`;
  } catch { /* lock not present — fall through to default */ }
  return `http://127.0.0.1:${process.env.NEXUS_BACKEND_PORT || '8787'}`;
}

const BASE_URL = resolveBaseUrl();

// ── Token resolution (lazy + memoized; never logged) ──────────────────────────
function readSecretFromEnvFile() {
  const envFile = process.env.AI_EMPLOYEE_ENV || path.join(os.homedir(), '.ai-employee', '.env');
  try {
    const line = fs.readFileSync(envFile, 'utf8').split(/\r?\n/).find((l) => l.startsWith('JWT_SECRET_KEY='));
    if (!line) return null;
    return line.slice('JWT_SECRET_KEY='.length).trim().replace(/^["']|["']$/g, '') || null;
  } catch { return null; }
}

async function mintToken(secret, scope) {
  const res = await fetch(`${BASE_URL}/api/auth/service-token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ secret, scope }),
  });
  let body = {};
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok || !body.token) {
    throw new Error(`could not mint '${scope}' token (status ${res.status}: ${body.error || 'unknown'})`);
  }
  return body.token;
}

let _tokens = null;
async function getTokens() {
  if (_tokens) return _tokens;
  let read = process.env.NEXUS_SERVICE_TOKEN_READ || process.env.NEXUS_SERVICE_TOKEN || null;
  let emit = process.env.NEXUS_SERVICE_TOKEN_EMIT || process.env.NEXUS_SERVICE_TOKEN || null;
  if (!read || !emit) {
    const secret = process.env.JWT_SECRET_KEY || readSecretFromEnvFile();
    if (!secret) {
      throw new Error(
        'No service token available. Set NEXUS_SERVICE_TOKEN (or _READ/_EMIT), or provide JWT_SECRET_KEY ' +
        '(env or ~/.ai-employee/.env) so the connector can mint a scoped token.',
      );
    }
    if (!read) read = await mintToken(secret, 'read');
    if (!emit) emit = await mintToken(secret, 'task-emit');
  }
  _tokens = { read, emit };
  log('service tokens resolved (read + task-emit)');
  return _tokens;
}

// ── HTTP helper ───────────────────────────────────────────────────────────────
async function api(method, pathname, { scope = 'read', body = null } = {}) {
  const tokens = await getTokens();
  const token = scope === 'task-emit' ? tokens.emit : tokens.read;
  const res = await fetch(`${BASE_URL}${pathname}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = text ? JSON.parse(text) : {}; } catch { json = { raw: text }; }
  return { status: res.status, ok: res.ok, json };
}

function toolResult({ status, ok, json }, label) {
  return {
    content: [{ type: 'text', text: JSON.stringify({ endpoint: label, http_status: status, ...json }, null, 2) }],
    isError: !ok,
  };
}

function toolError(message, label) {
  return { content: [{ type: 'text', text: JSON.stringify({ endpoint: label, error: message }, null, 2) }], isError: true };
}

// ── Tool catalog ──────────────────────────────────────────────────────────────
const EMPTY = { type: 'object', properties: {}, additionalProperties: false };

const TOOLS = [
  {
    name: 'get_status',
    description: 'System + AscendForge health (read-only). Returns overall status and the forge engine status.',
    inputSchema: EMPTY,
    handler: async () => {
      const sys = await api('GET', '/api/status');
      let forge = null;
      try { forge = await api('GET', '/api/forge/engine/status'); } catch { /* optional */ }
      return {
        content: [{ type: 'text', text: JSON.stringify({ system: { http_status: sys.status, ...sys.json }, forge_engine: forge ? { http_status: forge.status, ...forge.json } : null }, null, 2) }],
        isError: !sys.ok,
      };
    },
  },
  {
    name: 'get_diagnostics',
    description: 'AscendForge diagnostics (read-only).',
    inputSchema: EMPTY,
    handler: async () => toolResult(await api('GET', '/api/forge/diagnostics'), '/api/forge/diagnostics'),
  },
  {
    name: 'get_forge_runs',
    description: 'List recent AscendForge runs (read-only).',
    inputSchema: EMPTY,
    handler: async () => toolResult(await api('GET', '/api/forge/runs'), '/api/forge/runs'),
  },
  {
    name: 'get_forge_run',
    description: 'Get a single AscendForge run by id, including its report (read-only).',
    inputSchema: {
      type: 'object',
      properties: { id: { type: 'string', description: 'Run id' } },
      required: ['id'],
      additionalProperties: false,
    },
    handler: async (args) => {
      const id = encodeURIComponent(String(args?.id || '').trim());
      if (!id) return toolError('id is required', '/api/forge/runs/:id');
      return toolResult(await api('GET', `/api/forge/runs/${id}`), `/api/forge/runs/${id}`);
    },
  },
  {
    name: 'get_forge_queue',
    description: 'List the AscendForge approval queue — pending/approved items (read-only).',
    inputSchema: EMPTY,
    handler: async () => toolResult(await api('GET', '/api/forge/queue'), '/api/forge/queue'),
  },
  {
    name: 'forge_submit',
    description:
      'Propose work to AscendForge. This QUEUES a forge_queue_item for human approval — it does NOT execute. ' +
      'After Lars approves it in the dashboard, the server-side dispatcher runs it through the agent engine.',
    inputSchema: {
      type: 'object',
      properties: {
        goal: { type: 'string', description: 'What to do (the task/goal). Required.' },
        title: { type: 'string', description: 'Short label for the queue item (optional).' },
        project_id: { type: 'string', description: 'Target forge project id (optional).' },
        priority: { type: 'string', enum: ['low', 'normal', 'high'], description: 'Queue priority (optional).' },
        risk: { type: 'string', description: 'Risk hint, e.g. "review" (optional).' },
      },
      required: ['goal'],
      additionalProperties: false,
    },
    handler: async (args) => {
      const goal = String(args?.goal || '').trim();
      if (!goal) return toolError('goal is required', '/api/forge/submit');
      const body = { goal };
      if (args?.title) body.title = String(args.title);
      if (args?.project_id) body.project_id = String(args.project_id);
      if (args?.priority) body.priority = String(args.priority);
      if (args?.risk) body.risk = String(args.risk);
      return toolResult(await api('POST', '/api/forge/submit', { scope: 'task-emit', body }), '/api/forge/submit');
    },
  },
  {
    name: 'get_context_pack',
    description:
      'Get a COMPRESSED project context pack (tree + relevant files + constraints) so you can plan ' +
      'without reading the whole repo. Read-only. Use this before orchestrate to plan cheaply.',
    inputSchema: {
      type: 'object',
      properties: {
        project_id: { type: 'string', description: 'Forge project id. Required.' },
        goal: { type: 'string', description: 'The goal you are planning for (focuses relevance). Optional.' },
      },
      required: ['project_id'],
      additionalProperties: false,
    },
    handler: async (args) => {
      const pid = String(args?.project_id || '').trim();
      if (!pid) return toolError('project_id is required', '/api/forge/context-pack');
      const qs = new URLSearchParams({ project_id: pid });
      if (args?.goal) qs.set('goal', String(args.goal));
      return toolResult(await api('GET', `/api/forge/context-pack?${qs.toString()}`), '/api/forge/context-pack');
    },
  },
  {
    name: 'orchestrate',
    description:
      'Emit a DECOMPOSED task graph: one overall goal split into smaller tasks. Each task is QUEUED ' +
      'as a proposal for human approval — nothing executes until Lars approves. This is the planner/' +
      'decomposer role: read context, decompose, emit. Local agents execute after approval.',
    inputSchema: {
      type: 'object',
      properties: {
        project_id: { type: 'string', description: 'Forge project id (optional).' },
        goal: { type: 'string', description: 'The overall goal being decomposed (optional but recommended).' },
        tasks: {
          type: 'array',
          description: 'The decomposed tasks. Each is queued as a separate proposal.',
          items: {
            type: 'object',
            properties: {
              title: { type: 'string', description: 'Short label.' },
              goal: { type: 'string', description: 'What this task should accomplish. Required.' },
              affected_files: { type: 'array', items: { type: 'string' }, description: 'Files this task likely touches (optional).' },
              verification_command: { type: 'string', description: 'How to verify success, e.g. a test command (optional).' },
              risk: { type: 'string', description: 'Risk hint, e.g. "review" (optional).' },
              priority: { type: 'string', enum: ['low', 'normal', 'high'], description: 'Optional.' },
            },
            required: ['goal'],
            additionalProperties: false,
          },
          minItems: 1,
        },
      },
      required: ['tasks'],
      additionalProperties: false,
    },
    handler: async (args) => {
      const tasks = Array.isArray(args?.tasks) ? args.tasks : [];
      if (!tasks.length) return toolError('tasks[] is required (at least one task)', '/api/forge/orchestrate');
      const body = { tasks };
      if (args?.project_id) body.project_id = String(args.project_id);
      if (args?.goal) body.goal = String(args.goal);
      return toolResult(await api('POST', '/api/forge/orchestrate', { scope: 'task-emit', body }), '/api/forge/orchestrate');
    },
  },
  {
    name: 'get_run_failures',
    description:
      'Get COMPRESSED failure context for a run (failed tests + failed/blocked actions, messages only — ' +
      'no full logs) so you can review and propose fixes cheaply. Read-only.',
    inputSchema: {
      type: 'object',
      properties: { run_id: { type: 'string', description: 'Run id.' } },
      required: ['run_id'],
      additionalProperties: false,
    },
    handler: async (args) => {
      const id = encodeURIComponent(String(args?.run_id || '').trim());
      if (!id) return toolError('run_id is required', '/api/forge/runs/:id/failures');
      return toolResult(await api('GET', `/api/forge/runs/${id}/failures`), `/api/forge/runs/${id}/failures`);
    },
  },
];

// ── Server wiring ─────────────────────────────────────────────────────────────
async function main() {
  if (process.argv.includes('--smoke')) {
    // Validate config/load without connecting stdio or requiring the backend.
    log(`smoke ok — base_url=${BASE_URL}, tools=${TOOLS.map((t) => t.name).join(',')}`);
    process.exit(0);
  }

  const server = new Server(
    { name: 'nexus-ascendforge', version: '1.0.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const tool = TOOLS.find((t) => t.name === request.params.name);
    if (!tool) return toolError(`unknown tool: ${request.params.name}`, request.params.name);
    try {
      return await tool.handler(request.params.arguments || {});
    } catch (err) {
      // Surface backend/connection errors verbatim — never a fake success.
      return toolError(err?.message || String(err), tool.name);
    }
  });

  await server.connect(new StdioServerTransport());
  log(`connected — base_url=${BASE_URL}, tools=${TOOLS.length}`);
}

main().catch((err) => { log('fatal:', err?.message || err); process.exit(1); });
