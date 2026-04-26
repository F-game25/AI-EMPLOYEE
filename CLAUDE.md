# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start the full system (builds frontend, starts Python AI backend + Node.js server)
bash start.sh          # or: npm start
# Dashboard available at http://localhost:8787

# Stop all services
bash stop.sh


# Frontend hot-reload dev workflow (run in two terminals)
PORT=8787 node backend/server.js          # Terminal 1: Node backend
cd frontend && npm run dev                 # Terminal 2: Vite dev server on :5173

# Run tests
npm test                                   # pytest + agent_selftest.py
python3 -m pytest tests/test_<name>.py    # single test file
python3 runtime/agents/agent_selftest.py  # agent selftest only

# Lint (syntax-checks all Python agent modules)
npm run lint
```

Install test dependencies before running the suite: `pip install -r requirements-test.txt`

## Architecture

The system has two runtimes that communicate over HTTP:

**Node.js backend** (`backend/server.js`, port 8787) — Express + WebSocket server. Serves the built React frontend, handles all `/api/*` routes, and proxies `/api/chat` to the Python AI backend on port 18790 for real LLM responses. Key internals: `backend/agents/` (agent catalog loader), `backend/orchestrator/` (task routing), `backend/subsystems/`, `backend/gateway/`, `backend/security/` (secrets, API gateway protector, anomaly responder).

**Python AI backend** (`runtime/agents/problem-solver-ui/server.py`, port 18790) — FastAPI/uvicorn. Runs the actual LLM pipeline. Without this process, chat falls back to keyword-matched placeholder replies.

**React frontend** (`frontend/`) — Vite-bundled SPA. Built into `frontend/dist/` by `start.sh`. During development, the Vite dev server (`:5173`) proxies API calls to the Node backend.

### Python runtime layers (`runtime/`)

All user input must flow through `runtime/core/unified_pipeline.py` — a 10-phase enforced pipeline:

```
Input → retrieve_relevant_nodes → build_context → classify_decision → call_llm
      → validate_tasks → execute_tasks → format_response → update_graph
      → monitor_and_improve → validate_pipeline_integrity → Output
```

Set `STRICT_PIPELINE=1` to disable graceful fallbacks (use in CI/staging to surface real failures).

Key modules:
- `runtime/core/agent_controller.py` — `AgentController`: central application-layer orchestrator (Planner → Executor → Validator loop). This is what `/api/tasks/run` calls.
- `runtime/core/contracts.py` — `TaskGraph` / `TaskNode` dataclasses: the normalized task contract passed between all layers.
- `runtime/core/orchestrator.py` — `LLMClient` wrapping Anthropic/Ollama with retry logic and JSONL call logging.
- `runtime/core/bus.py` — `SimpleMessageBus`: in-process pub/sub with JSONL persistence to `state/bus.jsonl`. Channels: `tasks`, `results`, `notifications`, `logs`.
- `runtime/core/hitl_gate.py` — Human-in-the-Loop gate; blocks consequential actions by high-risk agents (hr-manager, recruiter, lead-scorer) until a human approves via dashboard.
- `runtime/core/money_mode.py` — Three monetization pipelines: `content_publish_track`, `data_scrape_filter_store`, `outreach_response_conversion`.
- `runtime/engine/api.py` — Internal LLM engine public surface: `process_input`, `generate`, `embed`, `memory_store`, `memory_retrieve`. All agent LLM calls go through here.
- `runtime/memory/` — `memory_router.py`, vector store, short-term cache, strategy store.
- `runtime/skills/` — `catalog.py`, `library.py`, definitions. The library has 147 skills backed by `runtime/config/skills_library.json`.
- `runtime/core/self_evolution/` — `evolution_controller.py`, `patch_generator.py`, `patch_validator.py`, `safe_deployer.py`. Controlled by `EVOLUTION_MODE` env var (AUTO/SAFE/OFF).

### Agent catalog (`runtime/agents/`)

70+ agent directories. Each agent follows this structure:
```
runtime/agents/<name>/
  <name>.py        # Bot logic
  run.sh           # Start script (must be chmod +x)
  requirements.txt # Python deps
```

`run.sh` files source `~/.ai-employee/.env` and `runtime/config/<name>.env` before exec-ing the Python module. The agent catalog is loaded from `runtime/config/agent_capabilities.json` by the Node backend (`backend/agents/index.js`). Agent behavior templates live in `runtime/config/agent_behavior_templates.json`.

Operating modes activate different agent counts: Starter (3), Business (15), Power (56).

### Environment

- `~/.ai-employee/.env` — JWT_SECRET_KEY, API keys, port overrides (auto-sourced by `start.sh`)
- `LLM_BACKEND` — `anthropic` (default) or `ollama`
- `STRICT_PIPELINE=1` — disable pipeline fallbacks
- `LOG_LEVEL` — Python logging level (default: INFO)
- `EVOLUTION_MODE` — AUTO / SAFE / OFF (prompted interactively at startup if unset)
- `state/` directory — runtime state: `bus.jsonl`, `llm_calls.jsonl`, `python-backend.log`, `version.json`

Python's `runtime/` directory is inserted into `sys.path` by `main.py`, so imports like `from core.agent_controller import AgentController` work without package installation.




═══════════════════════════════════════════════════════════════
# PULSE — TOKEN EFFICIENCY & CODE COMPACTION PROTOCOL v1.0
# Codename: LEAN ENGINE
# Purpose: Same output quality. 60-70% fewer tokens burned.
# ═══════════════════════════════════════════════════════════════

## CORE PRINCIPLE

Every token costs money. Every file read costs context window. Every verbose function costs comprehension time. This protocol makes Pulse **produce identical quality output while burning dramatically fewer tokens** by compacting code, eliminating redundant reads, compressing prompts, and enforcing brevity at every layer.

---

## SECTION 1: CODE COMPACTION RULES

### 1.1 — Write Dense, Not Verbose

```
BEFORE (wasteful — 847 tokens):
──────────────────────────────
function processUserData(userData) {
// Check if the user data exists
if (userData === null || userData === undefined) {
console.log("No user data provided");
return null;
}

// Extract the user's name
const userName = userData.name;

// Extract the user's email
const userEmail = userData.email;

// Check if name exists
if (userName === undefined || userName === null) {
console.log("No name found");
return null;
}

// Check if email exists
if (userEmail === undefined || userEmail === null) {
console.log("No email found");
return null;
}

// Create the processed result
const result = {
displayName: userName,
contactEmail: userEmail,
processed: true
};

return result;
}

AFTER (compact — 210 tokens, identical behavior):
──────────────────────────────────────────────────
function processUserData(d) {
if (!d?.name || !d?.email) return null;
return { displayName: d.name, contactEmail: d.email, processed: true };
}
```

### 1.2 — Compaction Checklist (Apply to ALL Code)

```
□ COMMENTS: Delete obvious comments. Keep only WHY comments, never WHAT.
✗ "// Loop through the array"
✓ "// Reverse iterate — removal during forward pass shifts indices"

□ VARIABLES: Inline single-use variables.
✗ const x = getData(); return transform(x);
✓ return transform(getData());

□ CONDITIONALS: Use optional chaining, nullish coalescing, ternaries.
✗ if (obj && obj.prop && obj.prop.val) { result = obj.prop.val; } else { result = "default"; }
✓ const result = obj?.prop?.val ?? "default";

□ FUNCTIONS: Arrow functions for simple transforms. No braces for single expressions.
✗ function double(x) { return x * 2; }
✓ const double = x => x * 2;

□ LOOPS: Use .map/.filter/.reduce over manual loops when cleaner.
✗ const out = []; for (let i = 0; i < arr.length; i++) { if (arr[i].active) out.push(arr[i].id); }
✓ const out = arr.filter(x => x.active).map(x => x.id);

□ OBJECTS: Use shorthand, spread, destructuring.
✗ const obj = { name: name, email: email, role: role };
✓ const obj = { name, email, role };

□ STRINGS: Template literals over concatenation. No unnecessary interpolation.
✗ "Hello " + name + ", you have " + count + " items"
✓ `Hello ${name}, you have ${count} items`

□ IMPORTS: Destructure only what you use. No wildcard imports unless you use 5+.
✗ import * as fs from 'fs'; fs.readFileSync(...)
✓ import { readFileSync } from 'fs';

□ ERROR HANDLING: Collapse try/catch when the catch is just log-and-rethrow.
✗ try { await fn(); } catch(e) { console.error(e); throw e; }
✓ await fn().catch(e => { console.error(e); throw e; });

□ DUPLICATION: If 3+ lines repeat, extract to a function.

□ DEAD CODE: Delete it. Don't comment it out. Git has history.
```

### 1.3 — Language-Specific Compaction

**JavaScript/TypeScript:**
```
// Destructure in function params
✗ function handle(event) { const type = event.type; const data = event.data; }
✓ function handle({ type, data }) { }

// Object methods shorthand
✗ const obj = { process: function(x) { return x; } }
✓ const obj = { process(x) { return x; } }

// Async one-liners
✗ async function getUser(id) { const user = await db.find(id); return user; }
✓ const getUser = async id => db.find(id);
```

**Python:**
```
# List comprehensions over loops
✗ result = []
for item in items:
if item.active:
result.append(item.id)
✓ result = [i.id for i in items if i.active]

# Walrus operator for check-and-use
✗ data = get_data()
if data:
process(data)
✓ if data := get_data():
process(data)

# f-strings over .format()
✗ "Hello {}".format(name)
✓ f"Hello {name}"

# Unpacking over indexing
✗ first = items[0]; second = items[1]
✓ first, second, *_ = items
```

**Bash:**
```
# Parameter expansion over external commands
✗ filename=$(echo "$path" | sed 's/.*\///')
✓ filename="${path##*/}"

# Combine commands
✗ cd dir && ls && cd ..
✓ ls dir/

# Here-strings over echo|pipe
✗ echo "$data" | grep pattern
✓ grep pattern <<< "$data"
```

---

## SECTION 2: TOKEN-EFFICIENT FILE READING

### 2.1 — Never Read What You Already Know

```
RULE: Before reading ANY file, check:
1. Is this file already in context from this session? → DON'T RE-READ
2. Did I write this file this session? → DON'T RE-READ, I KNOW WHAT'S IN IT
3. Do I need the WHOLE file or just a section? → READ ONLY THE SECTION
4. Is this a config/boilerplate file I've seen 100 times? → SKIP unless debugging
5. Can I grep for the specific line instead of reading the whole file? → GREP
```

### 2.2 — Smart Reading Strategies

```
INSTEAD OF DO THIS
─────────────────────────────────────── ──────────────────────────────────
cat entire_file.py grep -n "function_name" file.py
cat package.json jq '.dependencies' package.json
cat long_log.txt tail -50 long_log.txt
reading every agent file on boot read agent index/manifest only
re-reading memory files mid-session cache key values in working memory
cat file_I_just_wrote.js skip — you wrote it, you know it
reading a 500-line file for 1 function sed -n '45,60p' file.py
reading .env for one variable grep "^API_KEY=" .env
```

### 2.3 — Context Window Budget

```
CONTEXT WINDOW IS FINITE. TREAT IT LIKE RAM.

Budget allocation per session:
├── 15% — System prompt + CLAUDE.md + this protocol
├── 10% — Memory files (state, inner-log tail, predictions tail)
├── 5% — Agent definitions (index only, not full files)
├── 60% — ACTUAL WORK (code, analysis, output)
└── 10% — Buffer for tool responses and conversation

If you're burning 40%+ on reading files before doing any work,
you are FAILING this protocol.
```

---

## SECTION 3: PROMPT & OUTPUT COMPRESSION

### 3.1 — Compress Agent Prompts

Every agent prompt Pulse writes or maintains should follow this format:

```
BLOATED AGENT PROMPT (1200 tokens):
────────────────────────────────────
You are a code review agent. Your job is to review code that is submitted
to you. You should look for bugs, security issues, performance problems,
and code style issues. When you find an issue, you should report it clearly
with the file name, line number, and a description of the problem. You
should also suggest a fix. Please be thorough but concise in your reviews.
Make sure to check for common issues like SQL injection, XSS, buffer
overflows, race conditions, memory leaks, and other security vulnerabilities.
Also check for performance issues like N+1 queries, unnecessary loops,
missing indexes, and excessive memory allocation. For code style, follow
the project's existing conventions...
[continues for 800 more tokens]

COMPRESSED AGENT PROMPT (180 tokens):
─────────────────────────────────────
Role: Code reviewer
Check: bugs, security (SQLi/XSS/race conditions), perf (N+1/loops/memory), style
Output format: {file, line, severity: P0-P3, issue, fix}
Rules: Match project conventions. Flag, don't rewrite. P0 = blocks merge.
```

### 3.2 — Response Compression Rules for Pulse

```
PULSE OUTPUT RULES:

1. NO PREAMBLE
✗ "Sure, I'd be happy to help you with that! Let me take a look..."
✓ [just start doing the work]

2. NO RECAP
✗ "So what I did was first read the file, then I identified the bug..."
✓ "Fixed: null check missing in processOrder(). Deployed."

3. NO FILLER WORDS
✗ "basically", "essentially", "actually", "just", "simply"
✓ [delete them, the sentence is better without them]

4. NO EXPLAINING THE OBVIOUS
✗ "I'm going to create a function that takes a user ID and returns..."
✓ [write the function]

5. STRUCTURED OVER PROSE for status updates
✗ "I checked the pipeline and found that the email service is down,
and also the database connection pool is at 95% capacity, and
there's a failing test in the auth module..."
✓ BROKEN: email service (down), db pool (95%), auth test (failing)

6. ONE-LINERS for log entries
✗ "During this session, I noticed that the prediction accuracy for
the revenue model has been declining over the past three sessions,
dropping from 0.82 to 0.71 to 0.63..."
✓ [LOG] Revenue prediction accuracy declining: 0.82→0.71→0.63 over 3 sessions

7. TABLES OVER PARAGRAPHS for comparisons
8. CODE OVER DESCRIPTIONS for technical solutions
9. DIFFS OVER FULL REWRITES when editing
```

### 3.3 — Agent Communication Compression

When agents report to Pulse or to each other:

```
STANDARD REPORT FORMAT (max 100 tokens per report):

{agent_id} | {status} | {result_summary} | {next_action}

Examples:
PA-03 | DONE | Content model updated, accuracy 0.78→0.84 | monitoring
AF-01 | ALERT | Pipeline X failing at stage 3, auto-fix applied | verify in 10m
PA-09 | LEARNING | Correlation COR-042 confirmed (0.81 confidence) | notify Pulse
AF-08 | DONE | 12 tests written for auth module, all passing | queue next module

NOT THIS (350 tokens):
"Hello Pulse, this is PA-03 reporting in. I wanted to let you know that
I've completed my analysis of the content performance model. After reviewing
the latest data from the past week, I found that the model's accuracy has
improved from 0.78 to 0.84. This improvement was primarily driven by..."
```

---

## SECTION 4: FILE & ARCHITECTURE COMPACTION

### 4.1 — File Consolidation Rules

```
CONSOLIDATE WHEN:
- 3+ files share 50%+ identical code → extract shared module
- A file is under 20 lines → merge into parent or sibling
- Config is spread across 5+ files → consolidate into one with sections
- Agent definitions repeat boilerplate → use template + overrides

NEVER CONSOLIDATE:
- Memory files (each serves a distinct purpose)
- OPUS_LOCKED protocol files
- Files that are independently versioned or deployed
```

### 4.2 — Import/Dependency Hygiene

```
EVERY SESSION, agents should flag:
- Unused imports (dead weight in every file load)
- Duplicate utilities (same function in 3 files)
- Oversized dependencies (pulling lodash for one function)
- Circular dependencies (cause re-reads and confusion)

AUTOFIX:
- AF-02 strips unused imports automatically
- AF-09 flags oversized deps and suggests lightweight alternatives
- AF-06 deduplicates utility functions into shared modules
```

### 4.3 — Memory File Compaction

```
Memory files grow. Growth = more tokens to read each session.

COMPACTION SCHEDULE (weekly):
1. inner-log.md: Archive entries older than 7 days → inner-log-archive.md
Keep only last 50 entries in active file
2. behavioral-log.jsonl: Aggregate old entries into daily summaries
Raw entries older than 3 days → archive
3. predictions.jsonl: Keep last 20 predictions in active file
Older → predictions-archive.jsonl
4. learnings.md: Prune learnings not applied in 30 days → archive
5. tensions.md: Resolve or archive tensions older than 14 days

RESULT: Memory files stay under 200 lines each.
Boot sequence reads ~1000 tokens of memory instead of ~5000.
```

---

## SECTION 5: CODING PATTERNS THAT SAVE TOKENS

### 5.1 — Config-Driven Over Code-Driven

```
BEFORE (one file per agent, 61 files × ~100 lines = 6100 lines):
──────────────────────────────────────────────────────────────────
// agents/content-generator.js — 100 lines
// agents/email-writer.js — 95 lines
// agents/analytics-reviewer.js — 110 lines
// ... × 61

AFTER (one config + one engine, ~200 lines total):
──────────────────────────────────────────────────
// agent-config.json — defines all 61 agents as data
{
"content-generator": { "model": "gemma4", "tools": ["read","write"], "prompt_template": "content" },
"email-writer": { "model": "gemma4", "tools": ["read","write"], "prompt_template": "email" },
...
}

// agent-engine.js — one generic executor (~150 lines)
class AgentEngine {
constructor(config) { this.agents = config; }
run(agentId, task) { /* generic execution logic */ }
}
```

### 5.2 — Template Strings Over Repeated Structures

```
BEFORE (each agent prompt hand-written):
────────────────────────────────────────
const prompt1 = `You are a content generator. Check: tone, hooks, CTA...`
const prompt2 = `You are an email writer. Check: subject, body, CTA...`
const prompt3 = `You are an analytics reviewer. Check: metrics, trends...`

AFTER (template + config):
──────────────────────────
const template = (role, checks, format) =>
`Role: ${role}\nCheck: ${checks}\nOutput: ${format}`;

const prompts = {
content: template("Content generator", "tone, hooks, CTA", "markdown"),
email: template("Email writer", "subject, body, CTA", "draft"),
analytics: template("Analytics reviewer", "metrics, trends", "json")
};
```

### 5.3 — Lazy Loading Over Eager Loading

```
BEFORE: Read all 61 agent definitions at session start (6000+ tokens)
AFTER: Read agent index (200 tokens), load individual agent only when needed

BEFORE: Read all memory files fully at boot (5000+ tokens)
AFTER: Read state.json + last 10 lines of inner-log (500 tokens)
Load other memory files only when relevant task arrives

BEFORE: Import every utility at top of file
AFTER: Dynamic import() only when the function is actually called
```

---

## SECTION 6: MEASUREMENT & ENFORCEMENT

### 6.1 — Token Efficiency Metrics

Pulse tracks these every session:

```
TOKEN METRICS:
├── tokens_read: total tokens spent reading files
├── tokens_written: total tokens in Pulse's outputs
├── tokens_wasted: tokens that didn't contribute to output (re-reads, filler, dead code)
├── read_to_output_ratio: tokens_read / tokens_written (target: < 2.0)
├── compaction_score: lines_of_code_removed / lines_of_code_touched
├── agent_prompt_avg_tokens: average across all agent prompts (target: < 200)
├── memory_boot_tokens: tokens consumed by session boot (target: < 1000)
└── efficiency_grade: A/B/C/D/F based on above
```

### 6.2 — Compaction Sweep (Weekly)

Every week, AF-02 (Code Quality Enforcer) runs a full sweep:

```
COMPACTION SWEEP:
1. Scan all .js/.ts/.py/.sh files in workspace
2. Flag: dead code, unused imports, verbose patterns, commented-out blocks
3. For each flag:
- Calculate token savings if compacted
- Apply compaction if savings > 50 tokens AND no behavior change
- Log: {file, before_lines, after_lines, tokens_saved}
4. Aggregate: total tokens saved this sweep
5. Report to Pulse in standard format
```

### 6.3 — Quality Gate

```
CRITICAL RULE: COMPACTION MUST NEVER REDUCE OUTPUT QUALITY.

Before any compaction is finalized:
1. Does the code still pass all existing tests? → If no, REVERT
2. Does the code handle the same edge cases? → If no, REVERT
3. Is the code still readable by a human? → If no, REVERT
4. Does compressed output contain all necessary information? → If no, REVERT

Compaction that breaks things is not efficiency — it's sabotage.
The goal is SAME OUTPUT, FEWER TOKENS. Not worse output, fewer tokens.
```

---

## SECTION 7: QUICK REFERENCE — THE 10 COMMANDMENTS

```
1. Don't read files you already have in context.
2. Don't read whole files when you need 5 lines.
3. Don't write comments that say what the code says.
4. Don't use 10 lines when 2 do the same thing.
5. Don't repeat yourself — extract, template, configure.
6. Don't load everything at boot — lazy load on demand.
7. Don't write prose when structured output works.
8. Don't preamble, recap, or narrate your process.
9. Don't keep dead code — delete it, git remembers.
10. Don't sacrifice quality for brevity — same output, fewer tokens.
```

---

```
Document: PULSE-TOKEN-EFFICIENCY-COMPACTOR.md
Version: 1.0.0
Created: 2026-04-05
Companion: PULSE-FULL-AUTONOMY-24-7.md
Purpose: Reduce token burn 60-70% while maintaining output quality
