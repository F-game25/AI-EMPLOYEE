# Orders Money Pipeline — Audit & Implementation Plan

**Date:** 2026-06-12  
**Goal:** Turn the Orders page into a real lead→demo→pitch→approval→Forge handoff money pipeline.

---

## 1. What Already Works (Real, Not Stub)

### Orders System
- **`backend/routes/orders.js`** — 167 lines, thin HTTP→Python worker bridge
  - `GET /api/orders` — list with status filter
  - `GET /api/orders/:id` — single order
  - `POST /api/orders` — create order (manual entry)
  - `POST /api/orders/search` — find businesses via bedrijf_finder (Ollama-backed)
  - `POST /api/orders/:id/research` — company research (website, phone, social)
  - `POST /api/orders/:id/research-data` — store research from frontend finder
  - `POST /api/orders/:id/demo` — generate HTML demo (calls demo_generator.py)
  - `POST /api/orders/:id/approve` — ter_review → goedgekeurd (HITL gate)
  - `POST /api/orders/:id/pitch` — generate pitch email (Ollama LLM)
  - `POST /api/orders/:id/akkoord` — gepitcht → akkoord + vervolg_tekst with PayPal link
  - `POST /api/orders/:id/status` — manual status update (gepitcht/betaald/live)
  - `POST /api/orders/:id/deploy` — Netlify deploy (requires NETLIFY_API_TOKEN)
  - `DELETE /api/orders/:id` — delete order

- **`runtime/core/orders_store.py`** — 167 lines, SQLite-backed persistence
  - Table `orders` in `~/.ai-employee/state/audit.db`
  - Status flow: gevonden → demo_klaar → ter_review → goedgekeurd → gepitcht → akkoord → betaald → live

- **`runtime/core/demo_generator.py`** — 748 lines
  - Generates full HTML demo from Ollama (Dutch copy, Unsplash images, Netlify Forms)
  - Artifacts stored in `~/.ai-employee/state/artifacts/demos/{demo_id}/index.html`
  - Served via `GET /api/demos/:slug` (media.js)

- **`runtime/core/pitch.py`** — 272 lines
  - `genereer_pitch()` — Ollama pitch email (no price, with demo link)
  - `markeer_akkoord()` — follow-up with price + PayPal link + swarm pricing
  - `markeer_betaald(order_id, referentie)` — sets betaald status + stores PayPal ref

- **`frontend/src/components/pages/OrdersPage.jsx`** — 579 lines
  - Full pipeline UI: status pipeline visualization, NewOrderForm, BedrijfZoekerPanel, OrderCard
  - PitchBox with copy buttons, akkoord flow, betaald confirmation with referentie input
  - Demo preview, research display, hosting proposal

### Approval Flow
- `POST /api/orders/:id/approve` uses HITL gate (ter_review → goedgekeurd)
- ApprovalInbox.jsx shows pending approvals including orders

---

## 2. What Is Broken / Disconnected

### Critical Bug
- **Missing `POST /api/orders/:id/betaald` route** — frontend (OrdersPage.jsx:218) calls this but the route doesn't exist in orders.js. Python has `markeer_betaald()` ready. **EASY FIX: 5 lines in orders.js + 1 dispatch in python_worker.py**

### Missing Connections
- **No Forge handoff** — nothing connects `akkoord`/`betaald` orders to Ascend Forge
- **No demo quality gate** — demo goes straight to pitch without quality check
- **No build resource plan** — no compute routing before Forge build
- **No forge_project_id stored** — orders table has no column to link to a Forge project
- **Outreach is manual** — no structured tracking beyond status field

---

## 3. What Is Missing (New Features)

| Feature | Priority | Complexity |
|---------|----------|-----------|
| betaald route fix | P0 | trivial |
| Forge handoff (akkoord→betaald → create Forge V5 project) | P0 | medium |
| Demo quality gate (heuristic HTML evaluation) | P1 | small |
| Build resource plan (local/API/remote compute recommendation) | P1 | small |
| OrdersPage: forge link + quality gate display | P1 | medium |
| Outreach tracking (structured status + notes) | P2 | medium |

---

## 4. Architecture

```
OrdersPage.jsx
  └─ api.post('/api/orders/:id/*')
       └─ orders.js (Node route)
            └─ w().call('orders.*', args)
                 └─ python_worker.py (dispatch)
                      ├─ core.orders_store (SQLite CRUD)
                      ├─ core.demo_generator (HTML demo)
                      ├─ core.pitch (LLM pitch)
                      ├─ core.orders_forge_handoff (NEW — Forge V5 project creation)
                      └─ core.compute_router (backend selection)
```

Forge V5 project creation reuses:
- `POST /api/forge/v5/projects/start` (Node→Python)
- `forgeRunStore.upsertV5Goal()` (backlog integration)
- State files in `~/.ai-employee/state/forge/`

---

## 5. Implementation Plan (this session)

### Step 1 — Fix betaald route
- `backend/routes/orders.js`: add `r.post('/:id/betaald', ...)`
- `backend/python_worker.py`: add `orders.betaald` dispatch

### Step 2 — Forge handoff module
- `runtime/core/orders_forge_handoff.py` (NEW):
  - `create_forge_project_from_order(order_id, base_url)` 
  - Builds ForgeV5 project from order context + demo
  - Returns `{ forge_project_id, handoff }`
- `runtime/core/orders_store.py`: add `forge_project_id` column migration
- `backend/python_worker.py`: add `orders.forge_handoff` dispatch
- `backend/routes/orders.js`: add `POST /api/orders/:id/forge-handoff`

### Step 3 — Demo quality gate
- `runtime/core/demo_quality_gate.py` (NEW):
  - Heuristic HTML analysis: sections, CTA, lorem ipsum, mobile viewport
  - Returns 7-dimension quality result
- `backend/python_worker.py`: add `orders.demo_quality` dispatch
- `backend/routes/orders.js`: add `POST /api/orders/:id/demo-quality`

### Step 4 — Resource plan
- Reuses existing `core.compute_router.ComputeRouter`
- `backend/python_worker.py`: add `orders.resource_plan` dispatch
- `backend/routes/orders.js`: add `GET /api/orders/:id/resource-plan`

### Step 5 — UI wiring
- `frontend/src/components/pages/OrdersPage.jsx`:
  - DemoQualityGate panel (shows after demo generated)
  - ForgeHandoff button + status (shows at betaald/akkoord)
  - Resource plan panel (shows before forge handoff)
  - Link to Forge project when `forge_project_id` exists

---

## 6. Validation Scenario

Lead: Example Premium Detailing, Rotterdam, auto-detailing

1. Create order manually ✓
2. Generate demo ✓
3. Run demo quality gate (NEW)
4. Generate pitch ✓
5. Mark gepitcht ✓
6. Mark akkoord ✓
7. Confirm betaald with referentie (FIX)
8. Click "Stuur naar Ascend Forge" (NEW)
9. Forge V5 project created (NEW)
10. Resource plan shown (NEW)
11. Orders UI links to Forge project (NEW)

---

## 7. Files Changed in This Session

| File | Type | Change |
|------|------|--------|
| `backend/routes/orders.js` | Modified | +betaald, +forge-handoff, +demo-quality, +resource-plan routes |
| `backend/python_worker.py` | Modified | +orders.betaald, +orders.forge_handoff, +orders.demo_quality, +orders.resource_plan |
| `runtime/core/orders_store.py` | Modified | +forge_project_id column migration |
| `runtime/core/orders_forge_handoff.py` | New | Forge V5 project creation from order |
| `runtime/core/demo_quality_gate.py` | New | Heuristic HTML quality evaluation |
| `frontend/src/components/pages/OrdersPage.jsx` | Modified | +quality gate UI, +forge handoff UI, +resource plan UI |
