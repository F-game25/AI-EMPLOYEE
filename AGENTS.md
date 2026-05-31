# AGENTS.md — Full System Context Protocol

## Mission

You are working on Lars Fluks' AI system. Before improving, fixing, or changing anything, first understand the system architecture.

The job is not to randomly rewrite files. The job is to inspect the system, build context, identify weak points, and improve the project safely.

Read this file together with `CLAUDE.md`. `CLAUDE.md` contains the current command reference, architecture notes, runtime layout, security model, tenancy model, observability notes, and token-efficiency guidance.

## Mandatory First Step: System Recon

Before making code changes, read and map the project.

Inspect at minimum:

- README files
- `package.json`, `pyproject.toml`, and `requirements.txt` files
- frontend app structure
- backend app structure
- API routes
- database models and schemas
- auth and permissions
- agent orchestration
- event bus and message bus
- task queue
- memory system
- Money Mode
- dashboard UI
- config files
- environment examples
- tests
- existing docs
- `CLAUDE.md` if present
- previous architecture documents if present

Create a short internal map of:

- what the system is supposed to do
- what services exist
- how frontend talks to backend
- how agents, tools, and skills are connected
- what is real versus placeholder
- what is broken
- what is duplicated
- what is unsafe
- what should be improved first

## Working Rules

- Do not edit before understanding.
- Do not replace working systems.
- Do not create a new architecture unless absolutely necessary.
- Improve the existing architecture.
- Keep changes small, targeted, and production-quality.
- Never remove features without explaining why.
- Never fake working integrations.
- Never hardcode secrets.
- Never disable security, permissions, auth, validation, sandboxing, or logging.
- Never make destructive shell commands without approval.
- Prefer real fixes over cosmetic changes.
- Keep work structured so the system does not become messy.

## Output Format Before Any Major Change

Before editing for any major change, respond with:

1. System map
2. Main problems found
3. Risk areas
4. Files that likely need changes
5. Implementation plan

Only then start patching.

## Dashboard/UI Direction

The dashboard must become a premium futuristic AI command center.

Core requirements:

- central avatar, core, or eye is the main anchor
- important system status orbits around the core
- bottom toolbar stays usable
- no clutter
- no cheap sci-fi mess
- readable typography
- black, gold, and bronze premium feel
- smooth but lightweight animations
- every panel must show real system data or clearly marked mock data
- actions must connect to real backend functionality

## Money Mode Direction

Money Mode is not a separate app.

It is a layer on top of the existing system that connects:

- task discovery
- agent evaluation
- content generation
- marketplace and client work
- pricing
- approval flow
- execution
- delivery
- feedback
- earnings tracking

Money Mode may suggest and prepare actions, but must require approval before:

- publishing content
- sending client work
- spending money
- accepting paid tasks
- using wallets or payments
- modifying external accounts

## Verification

After every change, run the most relevant available command:

- `npm run build`
- `npm run lint`
- `npm test`
- `pnpm test`
- `pytest`
- `typecheck`
- backend health check

If verification cannot run, explain exactly why.

For documentation-only changes, verify the file exists, inspect the changed content, and review the diff.

## Final Response After Work

Always summarize:

- what was inspected
- what changed
- which files changed
- what was verified
- what still needs work
