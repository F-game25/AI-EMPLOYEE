# 🔄 REVISED ROADMAP — Core Product First, Payment Last

**Previous mistake:** Assumed you wanted to monetize immediately  
**Actual requirement:** Build a powerful, fully-functional system FIRST, then add monetization later  

---

## NEW PRIORITY ORDER

### PHASE 1: DEV FEATURES UNLOCK (Week 1-2, ~80 hours)
**Goal:** You can fully configure and control the system locally

**P1.1: Settings Menu + API Key Management** (20 hours)
- [ ] Settings page UI (nexus-ui components)
  - API keys section (Anthropic, OpenRouter, Ollama endpoints)
  - Encrypted local storage (not in plaintext)
  - "Test Connection" button for each API
  
- [ ] Backend API key management
  - GET `/api/settings/keys` → return configured keys
  - POST `/api/settings/keys` → save new key (encrypted)
  - DELETE `/api/settings/keys/{provider}` → remove key
  - All keys stored locally (not cloud), encrypted with local secret
  
- [ ] Environment variables
  - Read from `~/.ai-employee/.env` on startup
  - Allow override via UI Settings menu
  - Validate API keys before saving

**Success Criterion:**
- ✓ You can paste Anthropic API key in Settings → system uses it
- ✓ Key is encrypted on disk, not visible in plaintext
- ✓ Can switch between Anthropic/OpenRouter/Ollama

---

**P1.2: LLM Mode Selection** (16 hours)
- [ ] Settings panel for LLM choice
  - Default: Anthropic Claude (your preference)
  - Option 1: Local Ollama (download models yourself)
  - Option 2: OpenRouter (fallback, uses your API key)
  - Option 3: Custom endpoint (for self-hosted)

- [ ] Backend routing logic
  - `runtime/core/orchestrator.py` → choose provider based on setting
  - Fallback chain: Anthropic → OpenRouter → Ollama → error
  - Each provider has own error handling + retry logic

- [ ] Model selection UI
  - Available models dropdown (changes per provider)
  - Anthropic: Claude 3.5 Sonnet, Claude 3 Opus, etc.
  - Ollama: auto-detect available models on local instance
  - Save selection to settings

**Success Criterion:**
- ✓ You can switch from Anthropic → Ollama in Settings
- ✓ System uses local Ollama if configured
- ✓ Falls back gracefully if provider unavailable

---

**P1.3: Local LLM Integration (Ollama)** (24 hours)
- [ ] Ollama setup guide
  - Instructions in onboarding (how to install Ollama)
  - Auto-detect Ollama running on localhost:11434
  - Model download helpers (button: "Download Llama 2", "Download Mistral")

- [ ] Backend integration
  - Add Ollama provider to `runtime/engine/api.py`
  - LLM inference via Ollama REST API
  - Same interface as Anthropic client (unified)
  - Error handling for local LLM (timeout, OOM, not running)

- [ ] Frontend feedback
  - Show "Using Local Ollama" badge in UI
  - Display model name + tokens in status
  - Warn if Ollama not running

**Success Criterion:**
- ✓ Download Llama 2 via Ollama
- ✓ Set Ollama as provider in Settings
- ✓ System uses local LLM for tasks (no API costs)

---

**P1.4: Anthropic SDK Setup (Claude Locally)** (20 hours)
- [ ] `@anthropic-ai/sdk` integration (for Anthropic Claude)
  - Initialize in `runtime/engine/api.py`
  - Support all Claude models (Opus, Sonnet, Haiku)
  - Tool use support (for agents calling APIs)
  - Streaming support (real-time output to UI)

- [ ] Environment setup
  - ANTHROPIC_API_KEY read from settings or .env
  - Default model selection (you can override)
  - Token counting for usage tracking

- [ ] Error handling
  - API key validation on startup
  - Rate limiting handling (429 → retry)
  - Timeout handling (> 5 min → graceful failure)

**Success Criterion:**
- ✓ ANTHROPIC_API_KEY in Settings works
- ✓ Can select Sonnet vs Opus vs Haiku
- ✓ Tasks execute using selected model

---

### PHASE 2: FILE I/O & CODEX SYSTEM (Week 3-4, ~100 hours)
**Goal:** Upload files → system modifies → downloads updated files

**P2.1: File Upload System** (24 hours)
- [ ] Upload UI component
  - Drag-drop file area
  - Multi-file upload support
  - File browser (show uploaded files)
  - Preview for code files (syntax highlighting)

- [ ] Backend file handling
  - POST `/api/files/upload` → save to `~/.ai-employee/tenants/{tenant_id}/uploads/`
  - GET `/api/files/{file_id}` → download file
  - GET `/api/files` → list uploaded files with metadata (name, size, type, upload time)
  - DELETE `/api/files/{file_id}` → remove file

- [ ] File storage
  - Store in tenant-specific directory (multi-tenant safe)
  - Metadata in `state/files.json` (name, path, size, mime type)
  - Support: .py, .js, .ts, .jsx, .tsx, .md, .txt, .json, .css, .html, .sql, etc.

**Success Criterion:**
- ✓ Drag file onto interface → file uploads
- ✓ File stored and retrievable
- ✓ Can list, preview, delete files

---

**P2.2: Codex-Like Interface (System Modifies Files)** (40 hours)
- [ ] Instruction panel UI
  - Text input: "What changes do you want?"
  - File selector: "Which file to modify?"
  - Options: refactor, add tests, optimize, fix bugs, add comments
  - Reasoning: show what the AI proposes before applying

- [ ] Backend codex logic
  ```python
  # runtime/codex/file_modifier.py
  async def modify_file(file_path, instruction, llm_provider):
    # 1. Read file content
    # 2. Send to LLM: "File: {content}\n\nRequest: {instruction}"
    # 3. LLM returns modified code
    # 4. Show diff to user (what changed?)
    # 5. User approves → save
    # 6. Return modified file
  ```

- [ ] Diff visualization
  - Show before/after side-by-side
  - Highlight changes (green = added, red = removed)
  - User can approve, reject, or request revisions
  - Keep audit trail (who changed what, when)

- [ ] Supported modifications
  - Refactoring (simplify code, extract functions)
  - Bug fixes (fix logic errors)
  - Testing (generate unit tests)
  - Documentation (add comments, docstrings)
  - Optimization (performance improvements)
  - Formatting (style compliance)

**Success Criterion:**
- ✓ Upload Python file
- ✓ Ask "Add type hints to this file"
- ✓ See diff, approve, file downloads with changes

---

**P2.3: AscendForge Full Implementation** (36 hours)
**Current:** AscendForge UI exists but doesn't do anything  
**Goal:** Full strategic planning + execution

- [ ] Goal Decomposition Engine
  - User inputs goal (text)
  - System breaks into: Strategic Analysis → Resource Planning → Execution Roadmap
  - Each level shows tasks, dependencies, timeline
  - Example: "Build a SaaS for AI agents" → decomposes into 10+ tasks

- [ ] Constraint Reasoning
  - Budget slider (€)
  - Timeline slider (days)
  - Tool authorization checkboxes
  - System shows feasibility (green = possible, red = needs more resources)

- [ ] Multi-Path Strategy Planning
  - Generate 3 different approaches
  - Risk assessment for each path
  - Choose active path (system executes that plan)
  - Real-time progress tracking

- [ ] Execution Bridge (working buttons)
  - SEND TO AGENTS → `POST /api/tasks/run` with decomposed tasks
  - REQUEST MEMORY → `GET /api/brain/insights`
  - MONITOR OPS → navigate to Operations page
  - REPORT STATUS → fetch real status from `/api/agents/status`

- [ ] SVG Thought Map (interactive)
  - Nodes: initial goal, subgoals, constraints, decisions
  - Edges: dependencies
  - Click node → show logic chain (assumption → reasoning → conclusion)
  - Real-time updates as agents work

**Success Criterion:**
- ✓ Input goal: "Build React component for dashboard"
- ✓ System decomposes into 5 tasks with dependencies
- ✓ Click "SEND TO AGENTS" → tasks execute
- ✓ Watch progress in real-time via thought map

---

### PHASE 3: EXECUTION PIPELINE & REAL-TIME REPORTING (Week 5-6, ~80 hours)
**Goal:** System can think → work → execute → report via UI

**P3.1: Real-Time Task Execution UI** (24 hours)
- [ ] Task dashboard
  - Task ID, description, status (running, completed, failed)
  - Real-time progress bar
  - Agent assignments (which agents working on this?)
  - Subtask breakdown (3 of 5 steps complete)

- [ ] WebSocket connection
  - Subscribe to `/ws/tasks/{task_id}`
  - Receive updates every few seconds:
    - Status changes (idle → running → completed)
    - Subtask completion
    - Agent logs
    - Output preview

- [ ] Output display
  - Show task result (text, code, file, etc.)
  - Download button (save result)
  - Copy button (copy to clipboard)
  - Show execution time + cost (if applicable)

**Success Criterion:**
- ✓ Create task: "Write Python function to sort list"
- ✓ Watch progress: 0% → 25% → 50% → 100%
- ✓ Download result: `sorting_function.py`

---

**P3.2: Agent Activity Dashboard** (20 hours)
- [ ] Live agent status
  - Which agents are active?
  - What are they working on?
  - Idle agents available for work
  - Agent logs (last 10 messages from each)

- [ ] Agent communication
  - See agent → agent handoffs
  - Message queue (tasks queued for agents)
  - Retry logic (failed tasks, retries left)

- [ ] Metrics dashboard
  - Tasks per hour (throughput)
  - Avg task duration
  - Success rate (%)
  - Agents utilized (how many active?)

**Success Criterion:**
- ✓ Dashboard shows "3 agents active, 1 idle"
- ✓ See agent logs in real-time
- ✓ Click agent → see what it's working on

---

**P3.3: Unified Task Pipeline** (36 hours)
**Goal:** Complete 10-phase pipeline with UI visibility

- [ ] 10-Phase Pipeline (already in code, just expose to UI)
  1. Input validation
  2. Retrieve relevant nodes
  3. Build context
  4. Classify decision
  5. Call LLM
  6. Validate tasks
  7. Execute tasks
  8. Format response
  9. Update graph
  10. Monitor and improve

- [ ] Pipeline visibility
  - Show which phase task is in (progress bar: phase 5 of 10)
  - Show decision tree (how did system choose agent?)
  - Show context (what information was used?)
  - Show validation checks (what was validated?)

- [ ] Error recovery
  - If task fails → show which phase failed
  - Suggest fix (retry, use different agent, adjust parameters)
  - Automatic retry with exponential backoff
  - Manual override (user can force different approach)

**Success Criterion:**
- ✓ Task shows "Phase 7 of 10: Execute tasks"
- ✓ Can see detailed logs for each phase
- ✓ Failed task shows why it failed + suggests fix

---

### PHASE 4: SETTINGS & CONFIGURATION (Week 6-7, ~40 hours)
**Goal:** Full user control over system behavior

**P4.1: Settings Menu (Complete)** (20 hours)
- [ ] API Keys Section
  - Anthropic API key (encrypted)
  - OpenRouter key (fallback)
  - Ollama endpoint (localhost or remote)
  - Custom LLM endpoint (user-provided)
  - "Test Connection" button for each

- [ ] Model Selection
  - Default model choice (Sonnet, Opus, Haiku for Anthropic)
  - Temperature slider (0.0-1.0, affects creativity)
  - Max tokens slider (256-4096)
  - System prompt editor (customize LLM behavior)

- [ ] Agent Configuration
  - Which agents to enable/disable
  - Agent-specific settings (risk level, tool access)
  - Rate limiting (max tasks per hour)
  - Timeout settings (how long to wait for task)

- [ ] Tenant Settings
  - Tenant name, branding
  - Theme (light/dark)
  - Notification preferences
  - Export settings (backup, migrate)

**Success Criterion:**
- ✓ You can paste API key → system uses it
- ✓ Switch models (Sonnet → Opus)
- ✓ Adjust temperature, test effect
- ✓ All settings persist after restart

---

**P4.2: Settings Persistence** (10 hours)
- [ ] Local storage
  - Save to `~/.ai-employee/tenants/{tenant_id}/config.json`
  - Encrypted secrets (API keys)
  - Plain config (model choice, temperature)
  - Automatic backup (daily snapshots)

- [ ] Settings API
  - GET `/api/settings` → return all settings
  - POST `/api/settings` → save settings
  - PUT `/api/settings/{key}` → update one setting
  - PATCH `/api/settings/keys` → add/update API key

- [ ] Validation
  - API key format validation
  - Model name validation (check against available models)
  - Parameter bounds (temperature 0-1, tokens 256-4096)
  - Connection test before saving

**Success Criterion:**
- ✓ Settings persist after system restart
- ✓ API keys encrypted on disk
- ✓ Invalid settings rejected with clear error

---

**P4.3: Settings UI Completeness** (10 hours)
- [ ] Settings page layout (nexus-ui)
  - Tabs: API Keys, Models, Agents, Tenant, Advanced
  - Each tab has its own form
  - Save button applies all changes
  - Reset button reverts to last saved

- [ ] Notifications
  - "Settings saved successfully"
  - "Connection test failed: {error}"
  - "API key updated"
  - "System restart required for some changes"

- [ ] Help text
  - Tooltip on each setting (what does this do?)
  - Links to docs (how to get API key?)
  - Examples (show example API key format)

**Success Criterion:**
- ✓ All settings visible and editable in UI
- ✓ Changes take effect immediately (or with restart notice)
- ✓ Clear feedback on success/failure

---

### PHASE 5: PAYMENT INTEGRATION (Week 8+, ~40 hours)
**Goal:** Monetize after core product is rock-solid

**Only after Phases 1-4 are complete and working perfectly**

- P5.1: Billing Dashboard
- P5.2: Stripe Checkout
- P5.3: Quota Enforcement
- P5.4: Subscription Management

---

## REVISED TIMELINE

```
Week 1-2: Dev Features Unlock (80 hours)
  └─ Settings menu, API keys, LLM selection, local Ollama, Anthropic SDK

Week 3-4: File I/O & Codex (100 hours)
  └─ File upload/download, code modification with diff, AscendForge completion

Week 5-6: Execution Pipeline (80 hours)
  └─ Real-time task dashboard, agent activity, 10-phase visibility

Week 6-7: Configuration (40 hours)
  └─ Settings menu completeness, persistence, validation

Week 8+: Payment (40 hours) ⭐ ONLY AFTER CORE IS PERFECT
  └─ Stripe checkout, billing, quotas (optional if staying open-source)
```

---

## CRITICAL CHANGES

1. **Payment moved to Week 8+** (after core is rock-solid)
2. **Settings menu is P0** (not P2)
3. **AscendForge fully working** (not stub)
4. **File I/O system** (key differentiator)
5. **Codex-like interface** (Claude editing files)
6. **Real execution pipeline** (not mocked)
7. **Local LLM support** (Ollama, cost-free)
8. **Full control to user** (API keys, model selection, settings)

---

## SUCCESS CRITERIA (Week 7)

- ✅ Can paste own API key in Settings
- ✅ Can choose between Claude, Ollama, custom LLM
- ✅ Upload Python file → ask system to refactor → download modified file
- ✅ AscendForge: input goal → system decomposes + executes tasks
- ✅ Task dashboard shows real-time progress (10 phases visible)
- ✅ Agent activity dashboard shows what's happening
- ✅ All settings persist locally, encrypted
- ✅ System fully functional without any payment

---

## THEN (Week 8+)

**Only if you want to monetize, add:**
- Payment integration (Stripe)
- Billing dashboard
- Quota enforcement
- Subscription tiers

**Or stay open-source forever** (no payment ever needed)

---

## DELIVERABLES (Phases 1-4)

**~300 hours of core product work**
- Dev features (80h)
- File I/O (100h)
- Execution pipeline (80h)
- Settings (40h)

**Result:** 
- Fully functional AI system YOU control
- Works locally with your API keys
- Modifies files like Claude Code
- Real multi-agent orchestration
- No payment required
- Open-source or closed-source (your choice)

---

**This is the correct roadmap. Build the product first, monetize later.**
