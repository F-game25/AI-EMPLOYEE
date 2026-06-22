# Nexus / AscendForge — MCP brain-connector

A small **stdio MCP server** that exposes the running backend to Claude (the "brain")
as MCP tools. It is a thin adapter: every tool calls an existing backend HTTP route,
so there is no business logic here and no new attack surface beyond the routes themselves.

The brain can **read** system state and **propose** work. It cannot execute work
directly — `forge_submit` only queues an item for human approval. After you approve it
in the dashboard, the server-side dispatcher runs it through the agent engine.

## Tools

| Tool | Route | Scope | Effect |
|------|-------|-------|--------|
| `get_status` | `GET /api/status` (+ `/api/forge/engine/status`) | read | system + forge health |
| `get_diagnostics` | `GET /api/forge/diagnostics` | read | forge diagnostics |
| `get_forge_runs` | `GET /api/forge/runs` | read | recent runs |
| `get_forge_run` | `GET /api/forge/runs/:id` | read | one run + report |
| `get_forge_queue` | `GET /api/forge/queue` | read | pending/approved queue |
| `forge_submit` | `POST /api/forge/submit` | task-emit | **queues** work for your approval (does **not** execute) |

## Install

```bash
cd mcp
npm install
node server.js --smoke   # validates load + resolves backend URL, exits 0
```

## Configuration (no hardcoded values)

All settings come from the environment / runtime files:

**Backend URL** (first match wins):
1. `NEXUS_BACKEND_URL` — full override, e.g. `http://127.0.0.1:8787`
2. `~/.ai-employee/run/runtime-lock.json` → `ports.node` (auto, supports free-port selection)
3. `http://127.0.0.1:${NEXUS_BACKEND_PORT:-8787}`

**Auth** (least privilege — a `read` token for reads, a `task-emit` token for `forge_submit`):
1. `NEXUS_SERVICE_TOKEN_READ` and/or `NEXUS_SERVICE_TOKEN_EMIT` — pre-minted scoped tokens
2. `NEXUS_SERVICE_TOKEN` — used for both
3. Otherwise the connector mints both via `POST /api/auth/service-token` using
   `JWT_SECRET_KEY` (env, or read from `~/.ai-employee/.env`). Fails closed if none is found.

Secrets and minted tokens are **never** printed (all logging is on stderr; stdout is reserved
for the MCP protocol).

## Register with Claude Code

Add to your MCP client config (e.g. `~/.claude.json` or the project `.mcp.json`):

```json
{
  "mcpServers": {
    "nexus-ascendforge": {
      "command": "node",
      "args": ["/home/lf/AI-EMPLOYEE/mcp/server.js"],
      "env": {
        "NEXUS_BACKEND_URL": "http://127.0.0.1:8787"
      }
    }
  }
}
```

If `JWT_SECRET_KEY` is in `~/.ai-employee/.env`, no token env is needed — the connector mints
its own scoped tokens on first use. To run fully least-privilege without exposing the secret,
pre-mint tokens and pass them as `NEXUS_SERVICE_TOKEN_READ` / `NEXUS_SERVICE_TOKEN_EMIT`:

```bash
curl -s -XPOST "$NEXUS_BACKEND_URL/api/auth/service-token" \
  -H 'Content-Type: application/json' \
  -d '{"secret":"<JWT_SECRET_KEY>","scope":"read"}'
```

## Security model

- Deny-by-default scoped tokens; the connector never uses an admin token.
- `forge_submit` is a **proposal** — execution requires your approval + the dispatcher.
- Backend errors (incl. `403 insufficient scope`) are surfaced verbatim as tool errors —
  never a fake success.
