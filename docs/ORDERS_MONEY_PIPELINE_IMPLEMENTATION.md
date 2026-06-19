# Orders Money Pipeline — Implementation Report

**Status:** COMPLETE (Phase 1 — Manual Pipeline)  
**Date:** 2026-06-12  
**Goal:** Turn OrdersPage into a real money-making pipeline: lead → demo → pitch → approval → Ascend Forge handoff.

---

## What Was Built

### Backend (Python)

| File | Purpose |
|------|---------|
| `runtime/core/demo_quality_gate.py` | 7-dimension heuristic HTML evaluator (new) |
| `runtime/core/orders_forge_handoff.py` | Forge V5 handoff + compute resource planning (new) |
| `runtime/core/orders_store.py` | Added `forge_project_id`, `demo_quality` columns + helpers |

**Python worker ops added** (`backend/python_worker.py`):
- `orders.betaald` — mark order paid with PayPal reference
- `orders.demo_quality` — evaluate HTML demo against 7 quality dimensions
- `orders.resource_plan` — recommend compute route (local/GPU/remote/external API)
- `orders.forge_handoff` — create Forge V5 project from approved/paid order

### Backend (Node.js)

**New routes** (`backend/routes/orders.js`):
- `POST /:id/betaald` — record payment reference, status → betaald
- `POST /:id/demo-quality` — trigger quality gate evaluation
- `GET /:id/resource-plan` — get compute resource recommendation
- `POST /:id/forge-handoff` — hand order off to Ascend Forge (supports `override_payment`)

**Forge V5 filesystem fallback** (`backend/routes/forge.js`):
- `GET /v5/projects/:id/brief` — reads from disk when project was created via orders handoff
- `GET /v5/projects/:id/research` — returns null gracefully when research not yet run
- `GET /v5/projects/:id/goals` — returns empty array gracefully when goals not yet planned
- `_readV5Json(subdir, id)` helper function for `FORGE_HOME/{subdir}/{id}.json`

### Frontend

**New panel components** (`frontend/src/components/pages/OrdersPage.jsx`):
- `DemoQualityPanel` — triggers quality gate, shows pass/fail badge + blocking issues
- `ResourcePlanPanel` — shows compute route recommendation + approval warnings
- `ForgeHandoffPanel` — triggers Forge handoff, `override_payment` checkbox for akkoord orders

**CSS** (`frontend/src/components/pages/OrdersPage.css`):
- `.op-quality` panel (indigo), `.op-resource` panel (sky), `.op-forge` panel (purple)

---

## Status Flow

```
gevonden → demo_klaar → ter_review → goedgekeurd → gepitcht → akkoord → betaald → live
                                      ↑                         ↑
                               [auto after demo]          [requires referentie]
                                                               ↓
                                                        override_payment=true
                                                               ↓
                                                      Ascend Forge V5 handoff
```

---

## Demo Quality Gate — 7 Dimensions

| Dimension | Checks | Weight |
|-----------|--------|--------|
| visual_quality | viewport meta, CSS present | 0.5 + 0.5 |
| content_quality | no lorem ipsum, text length ≥ 500 | 0.4 + 0.6 |
| business_fit | business name in copy, branche present, hero section | 0.4 + 0.3 + 0.3 |
| conversion_quality | CTA/tel/mailto, form, button | 0.4 + 0.3 + 0.3 |
| usability | nav, footer, headings | 0.4 + 0.3 + 0.3 |
| technical_preview | DOCTYPE + body, no empty img src | 0.5 + 0.5 |
| forge_readiness | no placeholder tokens, ≥5 structural sections | 0.6 + 0.4 |

**Thresholds:** `passed` ≥ 6/7 dimensions, `partially_passed` ≥ 4/7, `failed` < 4/7.

---

## Compute Resource Plan

Priority: local_gpu → external_api → remote_compute → local_cpu  
Approval required: external_api, remote_compute  
Honest unavailability: remote returns false if `REMOTE_COMPUTE_HOST` not set

---

## Forge Handoff

When `POST /:id/forge-handoff` is called:
1. Validates order status (betaald/live, or akkoord with `override_payment=true`)
2. Deduplicates (returns existing project ID if already created)
3. Builds ForgeV5 brief from order context (bedrijfsnaam, branche, plaats, demo_url, prijs)
4. Persists brief to `~/.ai-employee/state/forge/briefs/{project_id}.json`
5. Persists handoff package to `~/.ai-employee/state/forge/handoffs/{project_id}.json`
6. Links `forge_project_id` on the order record in SQLite

---

## Validated Scenario

**Order:** Example Premium Detailing, Rotterdam, auto-detailing, €499

1. `GET /resource-plan` → `local` route, GPU detected, no approval needed ✓
2. `POST /demo-quality` (no demo) → helpful error "geen demo gegenereerd" ✓
3. `POST /forge-handoff` (wrong status) → "status is 'gevonden' — verwacht betaald" ✓
4. `POST /forge-handoff` (`override_payment=true`, akkoord status) → project `orders-order-728e878bcc-145039` created ✓
5. `POST /forge-handoff` (duplicate) → `already_exists: true` ✓
6. `GET /api/forge/v5/projects/{id}/brief` → full brief returned from filesystem ✓
7. `GET /api/forge/v5/projects/{id}/research` → `ok: true, research_pack: null` ✓
8. `GET /api/forge/v5/projects/{id}/goals` → `ok: true, goals: []` ✓
9. `npm run build` → ✓ 1256 modules, no errors ✓

---

## What's Next (Phase 2)

- **Demo generator upgrade**: premium sections (hero, services, benefits, trust, FAQ, contact, footer), no lorem ipsum
- **Lead finder**: auto-search bedrijven by stad+branche → create orders in bulk
- **Pitch tracking**: email sent/opened/replied status
- **Full Forge V5 execution**: research + goals + build cycle triggered from orders UI
- **Payment webhook**: PayPal IPN → auto `betaald` status on confirmed payment
