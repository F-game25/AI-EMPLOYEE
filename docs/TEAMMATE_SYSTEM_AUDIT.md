# Teammate (Companion) System — Gap Audit

**Date:** 2026-06-24 · **Scope:** `runtime/companion/*` (the conversational AI teammate)
**North Star (CLAUDE.md):** behave like an autonomous operations team — *convert intent →
structured workflow → real-world outcome*. Orchestrator → Skills → Tools.

## TL;DR
The teammate has a **strong architecture** (intent classification, context/session memory,
critique, safety gates, HITL approvals, local-first model routing, voice, avatar, 32
capabilities incl. a `skills.run` bridge to the 868 executable skills). **But its
conversation→execution routing cannot actually reach that capability**, so for most real
"do this work" requests it **talks instead of working**. Fixing the routing is the single
highest-leverage change in the whole system.

---

## What's solid ✅
- **Pipeline shape:** `ConversationRuntime.handle` → resolve → classify → critique →
  model-select → act-by-mode → response-policy → session-persist. Clean and observable.
- **Memory/context:** `session_state` (option-selection follow-ups: "option 2", "do that"),
  `context_resolver`, `memory.search/write` capabilities.
- **Safety/autonomy:** `safety_gate` per capability, HITL `approvals_required`, Computer-Use
  hard-gated + refuses to drive a browser with a weak model, security action scoring.
- **Model routing:** local-first (free), paid only on explicit opt-in and even then returns
  requiring approval.
- **The bridge exists:** `skills.run` → `SkillCatalog.dispatch_for_goal` (the same catalog the
  AgentController uses; now backed by ~859 executable skills).

---

## Critical gaps 🔴

### G1 — The 868 skills are effectively UNREACHABLE from conversation
Capability matching (`find_for_intent`) is naive **token-overlap against the ~32 capability
names only** — it never looks at the 868 skill names/tags. So `skills.run` loses the match to
coincidental token hits. Measured:

| Request | Top capability matched | Should reach |
|---|---|---|
| "write a blog post…" | `memory.write_structured` ("write") | skills.run → blog_writing |
| "find me 50 B2B leads" | `browser.open` | skills.run → lead-gen |
| "score these leads vs ICP" | `security.score_action` ("score") | skills.run → lead-scoring |
| "create a promo video" | `teammate.briefing.create_task` ("create") | skills.run → product-video |
| "build a landing page" | `browser.act` | skills.run → landing_page_copy |

There is **no `task_type → skills.run` shortcut** in `_EXACT_TASK_CAPS` (only 4 briefing/routine
caps), so business intents fall to the broken token match. **Impact: the system's biggest asset
(859 validated skills) is essentially dead weight in conversation.**

### G2 — Intent classification misses real "do" requests
Heuristic-first classifier routes many execution requests to `conversation`/`analysis` (chat
only), at low confidence:

| Request | Classified | Should be |
|---|---|---|
| find me 50 B2B leads | conversation (0.4) | execution |
| score these leads vs ICP | conversation (0.4) | execution |
| analyze Q3 revenue | analysis (chat-only) | execution → data/finance skill |

**Impact: the teammate produces a chat answer instead of executing the skill.**

### G3 — No skill-aware selection
Even when `skills.run` is reached, nothing selects *which* of the 859 skills + passes the right
inputs. The teammate has no "match request → best skill (by name/tag/description) → dispatch
with structured inputs" step. `skills.run` just forwards the goal text.

---

## Major gaps 🟠

### G4 — No multi-step decomposition (it's one-shot)
The broker matches up to 4 capabilities by token overlap and runs the cleared ones in a single
turn. There is **no planner loop** for compound goals ("find leads → score → draft outreach").
The `AgentController` (Planner→Executor→Validator) exists but the companion doesn't use it for
multi-step execution.

### G5 — Thin task-type vocabulary
Classifier emits only `chat | analysis | code | browser`. There are no `content | sales |
marketing | data | finance | research` task-types to route to the right skill family — so the
gate/routing can't distinguish a blog post from a financial model.

### G6 — Outcome/proof surfacing
`skills.run` now returns validated output + an artifact, but it's unverified whether the chat
reply surfaces the artifact + quality result as *proof* (the forge path does; the companion
summary path likely doesn't). "Real-world outcome with proof" is a North-Star requirement.

---

## Minor gaps 🟡
- **Proactivity** is limited to morning briefings + routines; no "I noticed X → propose Y".
- **No learning loop** from skill outcomes back into routing (which skill worked for which intent).

---

## Recommended fix (highest leverage first)
1. **Make routing skill-aware (fixes G1+G3).** When intent is an execution/business "do",
   match the request against the **skill catalog** (skill name/tags/description — reuse the
   catalog's own matcher) and dispatch via `skills.run` with the selected `skill_id` + extracted
   inputs. Add a `task_type → skills.run` default so business intents always have a home.
2. **Broaden intent classification (fixes G2+G5).** Add execution detection for content/sales/
   data/research verbs and the `content|sales|data|finance|research` task-types; lean on the LLM
   escalation when the heuristic is low-confidence on an imperative.
3. **Use AgentController for compound goals (fixes G4).** Route multi-step goals to the
   Planner→Executor→Validator loop instead of one-shot capability matching.
4. **Surface proof (fixes G6).** Include the skill's artifact + quality gate result in the chat
   reply/actions.

**#1 alone unlocks 859 skills in conversation — by far the biggest single improvement available.**
