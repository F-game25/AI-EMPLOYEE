# Ascend Forge — Polyglot / Multi-Language Build Research

*Research + recommendations for making Ascend Forge good at building across many languages
and multi-service (polyglot) projects, not just Python/JS.*

Date: 2026-06-15 · Status: research only (no code changed) · Author: research session

---

## 1. Executive summary — what makes an AI builder good at many languages

The leading 2026 systems are not "better LLMs at writing Rust." They are **harnesses that
compensate for the model's per-language weakness with structure**. Five things separate a
polyglot-capable builder from a Python-only one:

1. **Stack detection up front.** Before planning, detect every language/runtime/build-system
   in the target (lockfiles, manifests, file extensions, IaC). The plan, sandbox image, and
   test command are all chosen *from* that detection — never assumed.
2. **Language-agnostic code understanding** via a hybrid of **tree-sitter** (fast, structural,
   one grammar per language) and **LSP** (semantic, cross-file, type-aware). This replaces
   grep-based exploration that "misses semantic relationships" and burns 60–70% of agent turns
   just navigating code.
3. **Contract-first / schema-first coherence.** A single source of truth (OpenAPI, protobuf,
   SQL DDL, JSON Schema) is authored once, then **codegen** emits typed clients/stubs/DTOs into
   each language. This is how a TS frontend and a Go/Py backend stay in sync without the LLM
   hand-syncing types across languages (a top failure mode).
4. **Per-language sandbox toolchains + a tight compile/type/test feedback loop.** Each language
   has its own ephemeral, containerised runner; the agent self-corrects from *structured*
   compiler/type-checker output, not just stdout text.
5. **Per-language model routing + outcome learning.** Model success rates vary enormously by
   language (e.g. on Multi-SWE-bench, GPT-4o: ~55% Python vs ~3% C). Route each slice to the
   best model for *that* language, and learn per-language success rates over time.

Forge today does #5 partially (a single `CODE` tier), tags languages in fenced blocks, but does
**not** do stack detection, tree-sitter/LSP understanding, contract-first specs, or per-language
sandbox runners. Those are the highest-leverage gaps.

---

## 2. How the leading systems do it (concrete, per-system)

### Devin / Cognition
Autonomous agent (not in-editor). Given a NL task or linked ticket it **plans, then executes
inside a sandboxed cloud environment with shell + browser + editor**, runs subtasks in parallel,
coordinates sub-agents, and opens PRs. Polyglot capability comes from the *full dev environment*
(real shell + real toolchains) rather than language-specific model tricks — the agent runs the
project's actual build/test commands and reads the errors. Team-scale governance is "encoded
rather than implied" (goals defined upfront, work parallelised, progress centralised).
Sources: techtimes (Cognition $26B raise), augmentcode Devin alternatives, builder.io.

### Cursor (Anysphere)
IDE-first: AI embedded in the editor, engineer in the driver's seat. Polyglot understanding
leans on the editor's existing **LSP** integrations and codebase indexing; the model gets
language intelligence (completions, refactors, go-to-def) from the language servers already
running per language. Source: techtimes, builder.io.

### OpenHands (open source)
Autonomous AI software engineer that **modifies code, runs commands, browses the web, calls
APIs** from NL instructions — i.e. it operates the real toolchain in a sandbox, which is the
language-agnostic path. Source: marktechpost 2026 agents roundup.

### Aider
Maintains the **Aider Polyglot benchmark** — exercises across **Python, Go, Rust, C++, JS, Java**
(vs SWE-bench's Python-only). Aider's own design leans on a repo map (tree-sitter-derived) to
give the model a compressed, cross-language view of the codebase. The polyglot score is now a
standard vendor comparison metric.
Sources: agileleadershipdayindia (Aider polyglot leaderboard), arxiv DGM paper (uses Polyglot
to test generalisation across languages).

### Claude Code / Codex / Cline
Terminal/agent harnesses that operate the real shell and run language-native build/test commands;
they use **context engineering** (conversation compaction, selective file loading) to work on
repos larger than the context window. The harness — not the model — supplies polyglot reach by
executing each language's tools and feeding back structured results.
Sources: arxiv 2603.05344 (terminal coding agent scaffolding/harness/context engineering),
Anthropic "effective context engineering", blink.new ranking.

### Tooling layer used across systems
- **tree-sitter-analyzer (MCP)** — cross-language-safe code intelligence for agents: **13
  languages** indexed (symbols + call graph), **family-gated call graph** to prevent
  cross-language mis-wires (claims ~390× fewer mis-wires than a naive graph on its own repo),
  8 facade tools, 100% local. May-2026 patch added Swift/Kotlin/Ruby/PHP/C#.
- **LSPRAG** (arxiv 2510.22210) — LSP-guided RAG for **language-agnostic** real-time unit-test
  generation: language-specific modules do AST parsing (tree-sitter), language-agnostic modules
  use LSP; extend a language by translating its tree-sitter AST nodes.
- **Zed's hybrid model** — tree-sitter for performance-critical paths (highlighting/structure),
  LSP (separate process) for intelligence-critical features (completion/refactor). The
  canonical "tree-sitter + LSP, not either/or" architecture.
- **Sandboxes** (E2B, Modal, Daytona, Bunnyshell) — ephemeral, containerised, multi-language
  runners. MicroVMs (Firecracker) = gold isolation, gVisor = middle, containers = minimum.
  Closed-loop feedback captures stdout/stderr/exceptions for self-correction; sandbox start must
  be fast (<10s) or the agent stalls.
- **Monorepo orchestrators** (Nx/Turborepo/Bazel) — compute a **dependency graph** and rebuild/
  test **only affected packages**; Nx exposes project-graph awareness to agents via an MCP
  server so the agent knows which packages depend on which before making a breaking change.

---

## 3. Key reusable patterns (the implementable core)

| Pattern | What it does | Why it matters for polyglot |
|---|---|---|
| **Stack detector** | Scan manifests/lockfiles/extensions/IaC → `{languages, runtimes, build_tools, test_cmds, services}` | Everything downstream (plan, sandbox, tests, model) is chosen from this, not assumed |
| **tree-sitter repo map** | Per-language grammar → symbols + structure; compressed map of the repo | Replaces grep; gives the model a cross-language mental model cheaply |
| **LSP semantic layer** | Per-language language server → go-to-def, refs, types, diagnostics | Cross-file / type-aware understanding the LLM can't hold in context |
| **Family-gating** | Don't link symbols across language families in the call graph | Prevents the "Python func wired to a TS caller" mis-wire class |
| **Contract-first spec** | One schema (OpenAPI/protobuf/SQL DDL/JSON Schema) → codegen per language | Keeps TS↔Go/Py↔SQL in sync without the LLM hand-syncing types |
| **Per-language toolchain registry** | Map language → {build, typecheck, test, lint, container image} | Picks the right command + ephemeral image per slice |
| **Compile/type/test feedback loop** | Run build → typecheck → test; feed **structured** errors back; iterate | The single biggest quality lever for unfamiliar languages |
| **Per-language model routing** | Route each slice to the best model for that language; learn rates | GPT-4o ~55% Py vs ~3% C — one model is not enough |
| **Dependency-graph awareness** | Know which packages/services a change affects | Multi-service safety; test only affected, prevent breaking changes |
| **Doc-grounding** | Inject language/library docs into context for weak languages | Mitigates hallucinated APIs in Rust/Go/etc. |

**The unfamiliar-language failure modes to design against** (from the survey + practitioner posts):
- Compilers emit "coarse error messages with little insight" — agents struggle to diagnose. Fix:
  parse compiler/type-checker output into structured form before feeding back.
- Reasoning loops: agent re-calls the same tool with identical params on ambiguous feedback.
  Fix: deterministic, unambiguous tool results; cap retries.
- Type-sync drift across languages (e.g. "keeps breaking TypeScript" because it can't hold
  tsconfig + all `.d.ts` + the type web in context). Fix: contract-first + LSP diagnostics gate.
- Hallucinated APIs in low-resource languages. Fix: doc-grounding + compile-loop must pass.

---

## 4. Gaps in current Ascend Forge vs. these patterns

Grounded in the actual files:

1. **No stack detection.** `spec_engine.py` builds a spec from goal text with vagueness
   heuristics only; `planning_engine.py` maps slices to files via hardcoded `_FILE_HINTS`
   (`backend/routes/`, `frontend/src/components/`, `runtime/...`) — i.e. it assumes **this repo's
   Python/JS layout**. There is no detection of language, runtime, build tool, or service
   boundaries for an arbitrary target. → Misses **stack detector**.

2. **No code-graph understanding.** Nothing in `runtime/forge/lifecycle/` uses tree-sitter or
   LSP. File targeting is keyword→path string matching. → Misses **tree-sitter repo map**,
   **LSP semantic layer**, **family-gating**.

3. **Spec is prose-only, not contract-first.** `spec_engine.build_spec` produces
   goal/scope/assumptions/acceptance-criteria — no API/schema artifact. Cross-language coherence
   (TS client ↔ Py/Go server ↔ SQL) is left entirely to the LLM. → Misses **contract-first spec**.

4. **Test runner is Python-only.** `test_engine.run_tests` hardcodes `python -m pytest` with
   `PYTHONPATH`. A Go/Rust/TS slice has no runner. → Misses **per-language toolchain registry**
   and **per-language test runners**.

5. **No real per-language sandbox.** `implementation_engine.py` only drafts a patch *plan* and
   explicitly writes no files; the actual apply path (forge.js `/runs/:id/apply`) writes into the
   repo. There is no ephemeral, containerised, per-language build/run environment, and no
   compile/typecheck step before tests. → Misses **compile/type/test feedback loop** and
   **ephemeral per-language sandbox**.

6. **Model routing is single-laned for code.** `runtime/core/model_lanes.py` has one `CODE`
   tier (qwen2.5-coder family, degrade to smaller coder). It is hardware-dynamic but **not
   language-aware** — a Rust slice and a Python slice resolve to the same model, and there's no
   per-language success-rate learning. → Misses **per-language model routing** + outcome learning.

7. **Language metadata is shallow + lossy.** forge.js `actions` carry a `language` tag from the
   fenced block (extMap covers js/ts/py/rust/go/java/sql/yaml/etc.), but it's used only for the
   `write_file` action label/diff — not to drive a toolchain, a test command, or a model. The
   stack signal is captured then thrown away.

8. **No dependency-graph / multi-service awareness.** Slices have a linear `depends_on: [S(i-1)]`
   chain; there's no notion of which service/package a change affects, so multi-service builds
   have no blast-radius control or affected-only testing.

---

## 5. Concrete upgrade recommendations (prioritized)

Each item: the pattern it implements, the file(s) it touches, and a thin first slice.

### P0 — Stack detector (foundation for everything else)
- **Pattern:** stack detection. **New module:** `runtime/forge/lifecycle/stack_detector.py`.
- Scan the target dir: lockfiles/manifests (`package.json`, `pyproject.toml`/`requirements.txt`,
  `go.mod`, `Cargo.toml`, `pom.xml`/`build.gradle`, `*.csproj`), file extensions, IaC
  (`*.tf`, `*.yaml` k8s, `Dockerfile`), DB (`*.sql`, migrations). Emit
  `{languages:[], build_tools:[], test_cmds:{lang:cmd}, services:[], schema_files:[]}`.
- **Wire into:** `planning_engine.build_plan` (replace hardcoded `_FILE_HINTS` with detector
  output) and `spec_engine` (attach detected stack to the spec). Keep current hints as the
  fallback when detection is empty.
- *First slice:* detect languages + return a `test_cmds` map; planner consumes `languages`.

### P0 — Per-language toolchain registry + per-language test runner
- **Pattern:** per-language toolchain registry, per-language test runners.
- **New config:** `runtime/forge/lifecycle/toolchains.json` (no hardcoded commands in code) —
  `lang → {build, typecheck, test, lint, container_image}`. **Touches:** `test_engine.py` to read
  the registry instead of hardcoding pytest, selecting the runner from the slice's language /
  stack detection. Keep pytest path as the Python entry in the registry (no regression).
- *First slice:* registry with python(pytest)+node(jest/vitest)+go(`go test`); `run_tests(target,
  language)` dispatches.

### P1 — Compile/type/test feedback loop with structured errors
- **Pattern:** compile/type/test feedback loop, structured compiler feedback.
- Add a `verify_engine` step (or extend `test_engine`) that runs **build → typecheck → test** in
  order, parses each tool's output into `{file, line, code, message}`, and returns a structured
  failure the implementation/review loop can act on. Gate apply on typecheck passing.
- **Touches:** `test_engine.py` / new `verify_engine.py`, `review_engine.py`, and the apply gate
  in `backend/routes/forge.js`.

### P1 — Contract-first spec
- **Pattern:** contract-first / schema-first. **Touches:** `spec_engine.py`.
- When the goal spans services (frontend+backend) or names an API/DB, have `build_spec` require/
  produce a contract artifact (OpenAPI for HTTP, protobuf for RPC, SQL DDL / JSON Schema for
  data) as a first-class spec field. Planning then adds a **codegen slice** that emits typed
  clients/stubs/DTOs per detected language (via openapi-generator / protoc), so the LLM writes
  business logic against generated types instead of hand-syncing them.
- *First slice:* if the spec mentions an HTTP API, emit an `acceptance_criterion` "OpenAPI
  contract exists and client+server typecheck against it" and a codegen slice.

### P1 — Per-language model routing + outcome learning
- **Pattern:** per-language model routing. **Touches:** `runtime/core/model_lanes.py` +
  `skill_selector.py` + the learning/distillation loop (`backend/services/forge_learning.js`,
  `forge_training.js`).
- Extend the `CODE` tier into a language-keyed map (e.g. `CODE.rust`, `CODE.go`, `CODE.default`)
  resolved against live hardware as today, with env overrides (`MODEL_TIER_CODE_RUST`, …).
  Record per-language pass/fail from the feedback loop and bias routing toward the model with the
  best **per-language** success rate (mirrors the Multi-SWE-bench finding).
- *First slice:* keyed ladders + record `{language, model, passed}` to the existing learning store.

### P2 — tree-sitter repo map + LSP semantic layer
- **Pattern:** tree-sitter repo map, LSP semantic layer, family-gating.
- **New module:** `runtime/forge/lifecycle/code_graph.py` (or an MCP integration like
  tree-sitter-analyzer). Build a per-language symbol/call-graph map; family-gate cross-language
  edges. Feed a compressed repo map into planning/implementation context (replaces the
  keyword→path heuristic in `planning_engine._FILE_HINTS`). Optionally add an LSP client for
  go-to-def/refs/diagnostics on the active language.
- *First slice:* tree-sitter symbol index for the detected languages, surfaced to the planner as
  `files_hint` candidates ranked by symbol relevance.

### P2 — Dependency-graph / multi-service awareness
- **Pattern:** dependency-graph awareness. **Touches:** `planning_engine.py` (slice
  `depends_on`), `stack_detector.py` (service boundaries).
- Derive service/package boundaries + a coarse dependency graph; set slice `depends_on` from real
  edges (not linear), and scope the feedback loop to **affected** packages/tests only. If a
  monorepo tool (Nx/Turborepo/Bazel) is detected, shell out to its affected-graph query.

**Suggested order:** P0 stack detector → P0 toolchain registry/test runner → P1 verify loop →
P1 contract-first → P1 per-language model routing → P2 code graph → P2 dep graph. P0+P0 alone
make Forge genuinely multi-language; the rest raise quality and scale to multi-service.

---

## 6. Sources

- AI coding agents 2026 roundup — https://www.marktechpost.com/2026/06/10/ai-coding-agents-development-platforms-2026/
- Cognition $26B / agent-first architecture — https://www.techtimes.com/articles/317354/20260529/ai-coding-agents-cognitions-26b-raise-bets-agent-first-architecture-beats-ide-tools.htm
- Devin vs Cursor (autonomy vs IDE, team scale) — https://www.builder.io/blog/devin-vs-cursor
- Best Devin alternatives / agent orchestration — https://www.augmentcode.com/tools/best-devin-alternatives
- Ranked AI coding agents (Claude Code, Cursor, Devin, Cline, Codex) — https://blink.new/blog/best-ai-coding-agents-2026
- Anatomy of AI coding agents — https://blog.apiad.net/p/the-anatomy-of-ai-coding-agents
- Building effective terminal coding agents (scaffolding/harness/context eng.) — https://arxiv.org/pdf/2603.05344
- Anthropic — effective context engineering for AI agents — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Aider Polyglot leaderboard (6-language benchmark) — https://agileleadershipdayindia.org/blogs/ai-coding-benchmarks-decoded/aider-polyglot-benchmark-leaderboard.html
- Darwin Gödel Machine (uses Polyglot for cross-language generalisation) — https://arxiv.org/pdf/2505.22954
- tree-sitter-analyzer (cross-language code intelligence MCP, family-gating) — https://github.com/aimasteracc/tree-sitter-analyzer
- LSPRAG — LSP-guided RAG, language-agnostic test gen — https://arxiv.org/html/2510.22210v1
- Tree-sitter vs LSP — why hybrid wins — https://byteiota.com/tree-sitter-vs-lsp-why-hybrid-ide-architecture-wins/
- Zed language support + tree-sitter — https://deepwiki.com/zed-industries/zed/5.3-language-support-and-tree-sitter
- Contract-first (OpenAPI/protobuf/GraphQL) — https://designgurus.substack.com/p/openapi-protobuf-and-graphql-how
- OpenAPI → protobuf generator — https://github.com/OpenAPITools/openapi-generator/blob/master/docs/generators/protobuf-schema.md
- Managing APIs with Protobuf + OpenAPI — https://dzone.com/articles/the-modern-way-of-managing-apis-using-protobuf-and
- Contract-first with Node.js + OpenAPI — https://medium.com/@dxloop/contract-first-approach-with-node-js-and-openapi-for-rest-services-d2283a7ffd9d
- Coding agent sandbox (threat model, ephemeral, feedback loop) — https://www.bunnyshell.com/guides/coding-agent-sandbox/
- Best code execution sandboxes for coding agents 2026 — https://modal.com/resources/best-code-execution-sandboxes-coding-agents
- Agent sandboxes practical guide (Firecracker/gVisor isolation) — https://www.vietanh.dev/blog/2026-02-02-agent-sandboxes
- Multi-SWE-bench — multilingual issue resolving (8 languages, per-lang rates) — https://arxiv.org/pdf/2504.02605
- SWE-bench Multilingual overview — https://www.emergentmind.com/topics/swe-bench-multilingual
- SWE-smith — scaling data for SE agents — https://arxiv.org/pdf/2504.21798
- AI Agentic Programming survey (challenges incl. compiler feedback) — https://arxiv.org/pdf/2508.11126
- Why AI agents keep breaking TypeScript (type-sync failure) — https://dev.to/naelawadallah/why-your-ai-coding-agent-keeps-breaking-typescript-and-how-to-fix-it-2623
- Debugging AI-generated code — failure patterns — https://www.augmentcode.com/guides/debugging-ai-generated-code-8-failure-patterns-and-fixes
- Monorepo tooling 2026 (Nx/Turborepo/Bazel, affected graph, MCP) — https://daily.dev/blog/monorepo-turborepo-vs-nx-vs-bazel-modern-development-teams/
- Best monorepo build tools (graph layers) — https://sourcegraph.com/blog/monorepo-build-tools
