# C2 — One Agent/Skill/Tool Chain: status reconciliation + remaining-work plan

**Date:** 2026-06-30 · **Author:** Pulse (for Lars) · **Status:** DRAFT — doc-first, awaiting Lars's go before any code.
**Parent:** `docs/SYSTEM_COHERENCE_PLAN.md` §5 Phase C2 (P0: B1,B2,B3). Ground truth from the live code (the parent's `file:line` map is point-in-time).

> **Headline:** C2's *infrastructure* exists and B3 is done, but the **payload is missing**: the tool-composing dispatch path (`SkillCatalog.dispatch_for_goal → execute_skill → ToolRegistry`) is built and 19 real tools are registered — yet **0 of 577 skills declare `tools[]`**, so every skill collapses to the LLM-guided fallback. No skill runs a deterministic tool chain today. And `BaseAgent.execute` still calls the LLM directly (B1 open). C2 = give skills a real executable tool contract + dispatch agents through it.

---

## 1. The C2 goal (unchanged)

Make the architecture spec's spine real: **Orchestrator → Skills → Tools.** A skill is a reusable workflow that *composes tools* to a real outcome — not "ask the LLM as role X." Agents dispatch through the skill chain; skills run declared tool steps; the LLM is one tool among many, not the whole execution.

---

## 2. What is ALREADY DONE (evidence-cited — verify before building on it)

| C2 item | Status | Evidence |
|---|---|---|
| **B3 — no fabricated agent activity** | **DONE** | `ff5ba02d`. `backend/agents/index.js:_tick` now emits timer `task:completed` with `verified:false` and a comment: "the Node scheduler does NOT run the agent… the brain never learns success from a timer." Real verified completion comes from `completeTask()` on the AgentController result (`index.js:403-418`). |
| **Two-shape skill chain** | **DONE (infra)** | `SkillCatalog.dispatch_for_goal` (`catalog.py:237`) gives the Executor (dispatch by name) and goal-shaped callers (companion broker, agents) **one chain**: try a tool-composing executable skill → fall back to the library LLM path. |
| **Real ToolRegistry** | **DONE** | 19 tools registered: `web_search, web_fetch, browser_fetch, call_api, code_exec, shell_exec, read_file, write_file, create_file, list_dir, llm_infer, embed_text, get_memory, media_generate, send_email, update_db, system_*`. |
| **Library skills carry guidance** | **PARTIAL** | The "production skill" batches (`843b7857`, `9ba2c7f1`, `c451d7f9`, `8c95ca2f`, `8542b127`) gave all **570** library skills a `system_prompt` + prose `execution_steps`. Better than generic role-prompting — but still LLM-only (see B2). |
| **Honest dispatch (no fake success)** | **DONE** | `agent_controller._emit_action` (`agent_controller.py:609`) supplies a real LLM executor; executor raising → bus error → task fails (no silent fake-success). |

---

## 3. What REMAINS for C2 (ranked, evidence-cited)

### B2 — skills don't run tool chains (P0, the core)
- **Fact:** `skills_library.json` — 570 skills, **`tools` field = 0** (all `null`); catalog loads 577, **0 with `tools[]`**. So `dispatch_for_goal` step 1 (tool-composing) almost never fires for library skills; everything lands in step 2 `_run_library_skill` → `engine.api.generate(system_prompt, prompt=goal)`. `execution_steps` are passed as *prose context to the LLM*, never executed as tool calls.
- **What's missing:** (a) a per-skill **executable contract** — `tools[]` + structured steps (`{tool, inputs, output_var}`) for the high-value skills; (b) an **interpreter** that, when a skill has that contract, runs the steps through `ToolRegistry` (chaining outputs) instead of falling to LLM-only; (c) keep the LLM as a *step tool* (`llm_infer`) for synthesis, not as the whole skill.
- **Proposed change (smallest safe, reuses existing infra):**
  - Add an optional structured `steps[]` to a skill's JSON: each step = `{tool: <registered tool>, inputs: {...templated from goal/prior outputs...}, save_as: <var>}`. Leave prose `execution_steps` as the human/LLM-readable description (unchanged).
  - Add `SkillCatalog._run_tool_chain(skill, goal, ctx)` — validates each step's tool is registered, runs it via `ToolRegistry.execute` with permissioned envelopes, threads outputs, returns `{status, via:"skill_tool_chain", steps:[...real results...], output}`. **Untrusted-input rules:** tool args are built from a strict template (no raw LLM text → shell/file/SQL); `shell_exec`/`code_exec`/`send_email`/`update_db` stay HITL/approval-gated (B4) and are *not* auto-runnable from a skill step without the gate.
  - Slot it into `dispatch_for_goal` as the new step 1.5: if the matched skill has `steps[]`, run the tool chain; else current behavior. Fully backward-compatible (skills without `steps[]` behave exactly as today).
  - **Convert the top N revenue/lead/content/research skills first** (133 candidates identified; start with ~10–15: `market_research, competitor_analysis, lead scraping, email_copywriting, content_calendar, blog_writing, sentiment_analysis, …`). Each gets a `steps[]` of real tools (e.g. `market_research` → `web_search → web_fetch → llm_infer(summarize) → write_file(report)`).
- **Risk:** medium — new execution path. Mitigated: additive (skills without `steps[]` unchanged), each converted skill gets a test asserting its declared tools actually run (mock ToolRegistry, assert call sequence), STRICT_PIPELINE surfaces failures, dangerous tools stay gated.
- **Acceptance:** a converted skill returns `via:"skill_tool_chain"` with real per-tool results (not a single LLM blob); count of tool-executing skills ≫ 5; no dangerous tool auto-runs without the gate (test).

### B1 — agents bypass the skill chain (P0)
- **Fact:** `BaseAgent.execute` (`agents/base.py:64`) uses `self.client` (LLMClient) directly — no `SkillCatalog`/`ToolRegistry`. Agents are LLM-role wrappers, not tool-composers.
- **Proposed change:** route `BaseAgent.execute` (and `agent_controller._emit_action`) through `dispatch_for_goal` so an agent's work resolves to a skill→tool chain, falling back to its current LLM call only when no executable skill matches. Migrate **incrementally** — start with the revenue + lead agents (the ones whose skills get converted in B2). Don't rewrite all ~125 at once.
- **Risk:** medium per agent. Mitigated: per-agent migration behind the same fallback; the LLM path remains the floor; one integration test per migrated agent.
- **Acceptance:** a migrated agent's run shows a real tool chain in its trace (not just an LLM call); dashboard agent activity maps 1:1 to real tool runs.

### B4 — stub tools block some chains (P2)
- `update_db`, `send_email` are HITL-blocked stubs. Skills needing them can't *complete* unattended — by design (deny-by-default). Keep gated; for B2 conversions prefer read/compute/write-file tools; route any `send_email`/`update_db` step through the approval gate. No change this phase beyond documenting which converted skills need a gated step.

### B5 — orphan agents / non-BaseAgent files (P3) — out of scope for C2; cleanup later.

---

## 4. Proposed C2 execution order (gated, incremental)

1. **B2 interpreter** — `_run_tool_chain` + `dispatch_for_goal` step 1.5 + schema for `steps[]`. No skill data changed yet → pure additive infra + tests (chain runs, dangerous tools gated, backward-compat).
2. **B2 convert batch 1** — ~10–15 revenue/lead/content/research skills get real `steps[]`; one test each.
3. **B1 migrate batch 1 agents** — revenue + lead agents dispatch through the chain; integration tests.
4. Measure: executable-skill count, agent-activity↔real-run 1:1, then iterate batches behind the same gate.

Each step ships with proof; one PR per step. Size: **L** overall, but **S per increment** — we ship value continuously, not in a big-bang.

---

## 5. Security impact

- **Strictly tightens** the model→action boundary: today a "skill" is a raw LLM call; after B2, skill steps are **schema-validated tool calls** with permissioned envelopes. Raw LLM text never reaches shell/file/SQL — args are templated, validated, and `shell_exec`/`code_exec`/`send_email`/`update_db` stay approval-gated (deny-by-default).
- Every tool call is already logged via the registry envelope; the chain adds per-step audit.
- Reversible/incremental: additive interpreter + per-skill/-agent opt-in; nothing removed.
- Fail-closed: a step whose tool is unregistered or whose gate denies → chain stops with an explicit error (no silent skip), STRICT_PIPELINE re-raises.

## 6. What I will NOT do without your explicit go

- Convert all 570 skills at once (open decision below).
- Wire `send_email`/`update_db`/`shell_exec` to auto-run from a skill step (stay gated).
- Rewrite all ~125 agents — incremental, revenue/lead first.
- Touch C3's payment/public-URL pieces (separate; need your infra/billing decisions).

## 7. Open decisions for you

1. **C2 scope (parent open-decision #5):** convert **all 570** skills to executable, or **top-N revenue/lead/content/research first** (recommended — start ~10–15, prove the pattern, then batch)?
2. **First agents to migrate:** revenue + lead agents first (recommended), or a different set?
3. **D5 bridge:** make the **website_sales** orders loop the first real composed Skill as part of C2 (it's C3's coherence piece and a perfect first tool-chain), or keep C2 to internal skills and do D5 under C3?

---

*Grounded against the live tree 2026-06-30: `skills/catalog.py:225-330`, `skills_library.json` (570 skills, 0 tools, 570 execution_steps), `tools/registry.py` (19 tools), `agents/base.py:64`, `agent_controller.py:609`, `backend/agents/index.js:224-275,403-418`. Re-verify before each edit.*
