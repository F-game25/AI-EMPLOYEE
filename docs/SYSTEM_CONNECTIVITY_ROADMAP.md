# System Connectivity Roadmap

This roadmap turns AETERNUS NEXUS from a collection of working modules into one
cohesive offline-first AI operating system.

## Current Slice Implemented

- Node exposes the live Python memory service through:
  - `GET /api/memory`
  - `GET /api/memory/conversations`
  - `POST /api/memory/interactions`
  - `POST/PATCH/DELETE /api/memory/clients`
- The Memory page now shows live persisted memory, live WebSocket memory writes,
  and explicit mock/offline fallback state.
- Operators can write a memory interaction from the UI. Local agents and
  external API workflows can use the same endpoint.
- `runtime/config/system_orchestration_manifest.json` now defines the shared
  contract for memory layers, model routing, token minimization, page contracts,
  and core agent roles.
- `GET /api/system/manifest` exposes that contract to the dashboard.
- Agents page reads manifest contracts and shows job descriptions, workflows,
  hooks, and model needs in the agent drawer.
- AscendForge page reads its overseer/vibecoding contract and can call:
  - `POST /api/model/route-plan`
  - `POST /api/forge/submit`
  - `POST /api/forge/sandbox`
- `GET /api/memory/search` performs semantic search through the Python vector
  store with JSON-memory fallback.

## Required Architecture

```text
User / Operator
  -> Dashboard pages
  -> Node gateway
  -> Lightweight local orchestrator
  -> Memory fabric + model router + agent workflows
  -> Local models by default
  -> External APIs only when policy allows and context is compacted
```

## Memory Fabric

The memory system must behave as one fabric even if the storage engines differ.

- Working memory: live UI/session context and WebSocket events.
- Episodic memory: interactions, conversations, task events, approvals.
- Semantic memory: clients, facts, documents, embeddings, RAG chunks.
- Graph memory: entities and relationships via local graph/Neo4j-compatible
  layer.

All agents should use memory hooks:

- `before_model_call:retrieve_context`
- `after_chat:record_interaction`
- `after_task:write_summary`
- `after_delivery:record_feedback`

## Agent Contracts

Every agent needs:

- job description
- workflows
- input/output schemas
- hooks
- approval requirements
- model architecture needs
- memory read/write behavior
- allowed tools
- failure and rollback behavior

The manifest starts this with `ascend-forge`, `task-orchestrator`, `memory`, and
`blacklight-security`. The next phase should generate or normalize entries for
all agents in `runtime/config/agent_capabilities.json`.

## AscendForge Target

AscendForge is the system overseer and vibecoding agent.

It must be able to:

- build internal and external projects
- create agents, skills, tools, and workflows
- inspect system health and technical debt
- run sandboxed code changes
- perform security review before changes
- require approval before applying risky patches or delivering externally
- work with local AI by default and external APIs by policy

## Lightweight Token Orchestrator

External API calls must be reduced by default:

1. Classify intent locally.
2. Retrieve only relevant memory.
3. Summarize/compact context locally.
4. Route simple work to SLM/local LLM.
5. Escalate to external LLM/VLM only when policy and quality require it.
6. Cache embeddings, plans, and repeated outputs.
7. Track token cost per agent, workflow, and outcome.

## Next Implementation Phases

1. Normalize all agents into detailed manifest entries.
2. Add installer/offline validation for all model runtimes used by the manifest.
3. Add AscendForge project workspace UI: goal, repo path, plan, sandbox result,
   security scan, approval, apply.
4. Add Operations page task creation and approval workflow against real backend
   task endpoints.
5. Add page-level "live/mock/disabled" labels everywhere data is not yet real.
6. Add token-cost persistence per route-plan and per completed workflow.
7. Add local model availability probes for LLM, SLM, MLM, LAM, VLM, SAM, and LCM.
