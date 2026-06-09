# NexusOS Dashboard Design Principles

**Version:** 1.0  
**Status:** Production Guidelines  
**Last Updated:** 2026-05-13

---

## CORE PHILOSOPHY

Cinematic ≠ Usable.

This dashboard must support 8-hour workdays managing multiple autonomous agents, live incident response, and workflow orchestration. Professional operational interface, not a sci-fi mockup.

---

## 15 CRITICAL DESIGN RULES

### 1. CALM MOTION (Not Constant Animation)

**Idle State:**
- Almost still
- Soft breathing (0.2-0.3 opacity pulse, 3s cycle)
- Slow orbit (12-16s rotation)
- Minimal glow (0.3 intensity)

**Active State:**
- Intense motion ONLY on:
  - Workflow failures
  - High inference load (queue depth >30)
  - Threat escalation (MEDIUM+)
  - Autonomous actions (agent spawn/execute)
- Motion stops = attention signal

**Rule:** Motion = information, not decoration.

---

### 2. ATTENTION HIERARCHY (3-Tier System)

**Tier 1 — Immediate (Always Visible)**
- Threat state + color
- Critical failures (red badges)
- Active workflows (glowing)
- Emergency controls (red button)
- Location: Top bar + core urgency badges

**Tier 2 — Active Context (Default View)**
- Avatar/core state machine
- Current reasoning state
- Infra health summary
- Active agent count
- Location: Center + ring summaries

**Tier 3 — Deep Information (On Demand)**
- Event timelines
- Detailed metrics
- Reasoning chains
- Memory traces
- Location: Collapsible, hover-expand, modal detail pages

**Rule:** Show overview first, expand detail on demand.

---

### 3. PROGRESSIVE DISCLOSURE

**RingPanel Default Display:**
- 4 primary metrics (text only, monospace)
- 1 trend indicator (sparkline)
- 1 health indicator (color dot)

**RingPanel Hover:**
- Additional metrics appear
- Sparklines expand
- Recent events surface

**RingPanel Click:**
- Full detail modal/page opens
- Deep metrics, logs, chains
- Full context available

**Rule:** Keep dashboard clean by default.

---

### 4. LAYOUT ASYMMETRY (N/S/E/W with Breaks)

**AVOID:** Perfect symmetry (feels static, game-HUD-like)

**DO:** Slight asymmetry
- Cognition ring: positioned slightly higher
- Ops ring: positioned closer to center
- Economy ring: positioned slightly lower
- Infra ring: wider/broader base

**Why:** Organic feel instead of template layout.

**Rule:** Asymmetry = more natural, more tactile.

---

### 5. EVENTFEED STAYS RIGHT (Intelligent Stream)

**Location:** Right sidebar, 300px fixed width

**Display Strategy:**
- Group events into clusters (AGENT CLUSTER, TASK GROUP, etc.)
- Show priority levels (INFO, NOTICE, WARNING, CRITICAL)
- Collapse repeated events (47× retries → "47 retries")
- Scrollable independently from main viewport

**Intelligence Layer:**
- Smart grouping (same agent, same timeframe)
- Automatic deduplication
- Escalation detection (NOTICE → WARNING after 3 repeats)

**Rule:** Events are operational context, not noise.

---

### 6. FOCUS MODES (Attention Redirection)

Four modes, same dashboard, different priorities:

**OPERATIONS MODE**
- Emphasize: workflows, infra, task queue
- Dim: economy details, cognition visuals
- Key metric: queue depth, agent health, deployment status

**COGNITION MODE**
- Emphasize: reasoning chains, memory activity, context state
- Dim: economy, operations tasks
- Key metric: thoughts/sec, active chains, context depth

**SECURITY MODE**
- Emphasize: threat overlays, anomalies, suspicious agents
- Dim: non-critical metrics
- Key metric: threat score, blocked actions, policy violations

**ECONOMY MODE**
- Emphasize: monetization, ROI, conversion streams, revenue
- Dim: operational detail
- Key metric: daily revenue, conversion rate, pipeline health

**Implementation:**
- Mode selector in top-right (dropdown or buttons)
- Same components, different glow/emphasis
- CSS variable swapping (`--focus-mode: operations`)
- Persist user preference per session

**Rule:** Users pick what matters right now.

---

### 7. WORKSPACE PERSISTENCE

**Persist Per User:**
- Collapsed panel states
- Active filters (event categories)
- Zoom level
- Focus mode selection
- Panel positions (if draggable)
- Sidebar width

**Storage:** localStorage or server-side preference

**Rule:** Tools remember user intent.

---

### 8. COMMAND PALETTE (Keyboard-First)

**Trigger:** `Ctrl+K` (or `Cmd+K` on Mac)

**Features:**
- Navigate to agents/workflows/tasks
- Execute quick actions (deploy, approve, stop)
- Search events/alerts
- Jump to modal details
- Open settings, documentation
- Keyboard shortcuts guide

**Why Critical:** Professional users want minimal clicking.

**Rule:** Keyboard workflows > mouse workflows.

---

### 9. QUIET BY DEFAULT (90/10 Rule)

**90% of UI:**
- Dark background
- Low contrast
- Minimal motion
- Neutral colors

**10% of UI (Alerts/Status):**
- Bright colors
- High contrast
- Motion/glow
- Immediate attention

**Rule:** Restraint makes warnings mean something.

---

### 10. MULTITASKING TOOLS

**Dockable Panels:** Drag/resize any panel

**Multi-View Tabs:** 
- [ Operations ] [ Cognition ] [ Security ] [ Economy ]
- Tabs don't reload page, switch focus mode

**Split-Screen Mode:**
- Agent detail + event feed side-by-side
- Workflow + reasoning trace side-by-side

**Pinning System:**
- Pin favorite agents/tasks/workflows to side tray
- Quick access without navigation

**Rule:** Power users need multi-context workflows.

---

### 11. MOBILE: Companion, NOT Clone

**Mobile is NOT miniature desktop.**

**Mobile Focus:**
- Alerts + status only
- Quick actions (approve, stop, acknowledge)
- Emergency controls (easy to find)
- Notifications prominent

**Mobile Structure:**
```
[ Core (summary) ]
[ Alerts (priority feed) ]
[ Agents (quick view) ]
[ Tasks (active only) ]
[ Menu ]
```

**Mobile Avoids:**
- Full orbital rings (unreadable)
- Complex event stream (too dense)
- Deep metrics (overwhelming)

**Rule:** Mobile is operations, not deep analysis.

---

### 12. OPERATIONAL RHYTHM (Global Timing)

**Consistent animation timing across all updates:**

| Update Type | Duration | Easing |
|------------|----------|--------|
| Metric value change | 300ms | easeInOutQuad |
| Panel transition | 250ms | easeInOutQuad |
| Alert/warning flash | 600ms | easeInOut |
| Orbit speed change | 400ms | easeInOutCubic |
| Event insertion | 200ms | easeOut |
| Modal open | 300ms | easeOut |
| Modal close | 200ms | easeIn |

**Why:** Coherent timing feels intentional and professional.

**Rule:** Timing is language.

---

### 13. STATUS SEMANTICS (Shape + Motion + Color)

**Health Status:**
- Healthy → slow breathing (0.3 opacity pulse, 3s)
- Busy → faster orbit + increased glow
- Warning → intermittent pulse (600ms on/off)
- Critical → sharp flashes (300ms intervals) + red tint
- Offline → frozen orbit + desaturated color

**Why:** Visual language is faster than labels.

**Rule:** Motion = state, not just decoration.

---

### 14. CONTEXT LOCKING (Linkage Visualization)

**On hover/click of any event:**
- Highlight relevant RingPanel border (glow increase)
- Highlight relevant agents (in infra ring)
- Highlight relevant workflows (in ops ring)
- Highlight memory references (in cognition ring)

**Why:** Event → system context instantly visible.

**Implementation:**
- CSS class: `.context-active`
- Store: `selectedEventId` in systemStore
- Selector in rings: filter by event context

**Rule:** Connection = understanding.

---

### 15. LAYOUT DECISIONS (Final)

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Ring Layout | N/S/E/W asymmetric | Cinematic + operational |
| Event Feed | Right sidebar (300px) | Natural eye scan pattern |
| Scroll Model | Fixed bars + viewport scroll | Always-visible controls |
| Rings Responsive | Shrink first, collapse later | Maintain visual priority |
| Dark Space | Minimalist + subtle grid | Focus on core/glow |
| Mobile | Companion UI (5 tabs) | Operations-focused, not mini-desktop |
| Focus Modes | 4 modes (Op/Cog/Sec/Econ) | Attention redirection |
| Command Palette | Ctrl+K | Keyboard-first workflows |
| Persistence | localStorage per user | Memory of intent |

---

## IMPLEMENTATION CHECKLIST FOR TASK 4

- [ ] Dashboard layout: fixed bars + scrollable viewport
- [ ] N/S/E/W ring positioning with asymmetry
- [ ] EventFeed right sidebar with intelligent grouping
- [ ] Focus mode selector + CSS variable swapping
- [ ] RingPanel progressive disclosure (default/hover/click)
- [ ] Calm motion idle state (slow breathe, minimal glow)
- [ ] Motion intensity linked to queue/load metrics
- [ ] Context locking (event hover highlights related elements)
- [ ] Operational rhythm timing constants (CSS vars)
- [ ] Status semantics (motion language per state)
- [ ] Command palette trigger (Ctrl+K)
- [ ] Workspace persistence (localStorage)
- [ ] Mobile layout (companion 5-tab structure)
- [ ] Attention hierarchy visual testing (Tier 1/2/3 clarity)
- [ ] Multi-view tabs (Operations/Cognition/Security/Economy)

---

## TESTING CHECKLIST

- [ ] 8-hour workday simulation (no fatigue/blindness)
- [ ] Multi-incident scenario (all visible without overload)
- [ ] Mobile usability (5-tab navigation smooth)
- [ ] Keyboard-only workflow (Command+K sufficient)
- [ ] Focus mode switching (smooth, no jarring)
- [ ] Event escalation (motion intensity rises with severity)
- [ ] Context locking (event hover clearly shows linkage)
- [ ] Accessibility (WCAG AA, prefers-reduced-motion respected)
- [ ] Performance (60fps animations, <100ms interactions)

---

## SUCCESS CRITERIA

This dashboard is successful when:

1. **Cinematic BUT usable** — looks stunning, works for 8+ hours without fatigue
2. **Attention clear** — critical info stands out without fighting for space
3. **Keyboard-friendly** — power users can operate with minimal mouse
4. **Mobile-ready** — alerts/actions accessible on phone (not full clone)
5. **Context-aware** — relationships between events/agents/workflows visible
6. **Calm** — motion has meaning, not constant distraction
7. **Professional** — feels like operational control, not game UI

---

**Status:** Ready for implementation
