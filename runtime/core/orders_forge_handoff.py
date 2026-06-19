"""Orders → Ascend Forge V5 handoff.

Creates a real Forge V5 project from an approved/paid order so Ascend Forge
can build the full production website from the approved demo.

Requires order status: betaald (or akkoord with override_payment=True).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from core.file_lock import FileLock

_AI_HOME = os.environ.get("AI_HOME") or str(Path.home() / ".ai-employee")
_FORGE_STATE = Path(_AI_HOME) / "state" / "forge"
logger = logging.getLogger(__name__)


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_token(value: str, label: str) -> str:
    token = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", token) or ".." in token:
        raise ValueError(f"invalid_{label}")
    return token


def _tenant_id() -> str:
    try:
        from core.tenancy import get_current_tenant
        return _safe_token(get_current_tenant().tenant_id, "tenant_id")
    except Exception:
        return "default"


def _handoff_lock(order_id: str) -> FileLock:
    lock_dir = _FORGE_STATE / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return FileLock(lock_dir / f"handoff-{_tenant_id()}-{_safe_token(order_id, 'order_id')}.json", timeout=10)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _audit_handoff(handoff: dict[str, Any]) -> None:
    try:
        _FORGE_STATE.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(_FORGE_STATE / "audit.db")) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, event_type TEXT, source TEXT, entity_id TEXT, details TEXT, created_at TEXT)"
            )
            conn.execute(
                "INSERT INTO audit (id, event_type, source, entity_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    f"audit-{uuid.uuid4().hex[:12]}",
                    "forge_project_created",
                    "orders",
                    str(handoff.get("order_id") or ""),
                    json.dumps(handoff, ensure_ascii=False),
                    _ts(),
                ),
            )
    except Exception as exc:
        logger.warning("orders_forge_handoff audit failed: %s", type(exc).__name__)
    logger.info(
        "orders_forge_handoff created order_id=%s project_id=%s override_payment=%s",
        handoff.get("order_id"),
        handoff.get("forge_project_id"),
        handoff.get("override_payment_used"),
    )


def build_resource_plan(order_id: str) -> dict[str, Any]:
    """Return a compute/model resource recommendation for the Forge full build."""
    from core.orders_store import order_ophalen
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}

    try:
        from core.compute_router import get_compute_router
        backends = get_compute_router().health()
    except Exception as exc:
        backends = {
            "local_cpu": {"available": True, "reason": "always available"},
            "local_gpu": {"available": False, "reason": str(exc)},
            "remote_compute": {"available": False, "reason": "compute_router unavailable"},
            "external_api": {"available": False, "reason": "compute_router unavailable"},
        }

    local_gpu = backends.get("local_gpu", {}).get("available", False)
    remote = backends.get("remote_compute", {}).get("available", False)
    external = backends.get("external_api", {}).get("available", False)

    if local_gpu:
        recommended_route = "local"
        recommended_compute = "local_gpu"
        reasoning = "Lokale GPU beschikbaar — volledige website build lokaal mogelijk."
        approval_required = False
    elif external:
        recommended_route = "external_api"
        recommended_compute = "external_api"
        reasoning = "Geen lokale GPU. Externe API (Anthropic/OpenAI) beschikbaar voor hogere kwaliteit."
        approval_required = True
    elif remote:
        recommended_route = "remote_compute"
        recommended_compute = "remote_compute"
        reasoning = "Remote compute geconfigureerd — gebruik voor zware builds."
        approval_required = True
    else:
        recommended_route = "local"
        recommended_compute = "local_cpu"
        reasoning = "Alleen lokale CPU beschikbaar. Build werkt maar kan langzamer zijn."
        approval_required = False

    branche = order.get("branche", "")
    complexity = "medium"
    if any(k in branche.lower() for k in ("webshop", "ecommerce", "platform")):
        complexity = "high"
    elif any(k in branche.lower() for k in ("visitekaart", "one-page", "landing")):
        complexity = "low"

    return {
        "ok": True,
        "resource_plan_id": f"rp-{uuid.uuid4().hex[:10]}",
        "order_id": order_id,
        "quality_target": "premium",
        "estimated_complexity": complexity,
        "backends": backends,
        "recommended_route": recommended_route,
        "recommended_compute_backend": recommended_compute,
        "reasoning": reasoning,
        "estimated_cost": None,
        "approval_required": approval_required,
        "risks": (["Externe API-kosten — controleer budget voor build start"] if approval_required else []),
        "fallback": "local_cpu als voorkeur-backend niet beschikbaar is",
        "created_at": _ts(),
    }


def create_forge_project_from_order(
    order_id: str,
    base_url: str = "",
    override_payment: bool = False,
) -> dict[str, Any]:
    with _handoff_lock(order_id):
        return _create_forge_project_from_order_locked(order_id, base_url, override_payment)


def _create_forge_project_from_order_locked(
    order_id: str,
    base_url: str = "",
    override_payment: bool = False,
) -> dict[str, Any]:
    """Create a Forge V5 project from an approved/paid order.

    Args:
        order_id: The order to hand off.
        base_url: Public URL for demo links.
        override_payment: If True, allow akkoord status without betaald.
    """
    from core.orders_store import order_ophalen, forge_project_opslaan

    order_id = _safe_token(order_id, "order_id")
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}

    allowed_statuses = {"betaald", "live"}
    if override_payment:
        allowed_statuses.add("akkoord")

    if order["status"] not in allowed_statuses:
        needed = "betaald/akkoord (met override)" if override_payment else "betaald"
        return {
            "ok": False,
            "error": (
                f"Order status is '{order['status']}' — verwacht {needed}. "
                f"{'Gebruik override_payment=true om door te sturen zonder betaling.' if not override_payment else ''}"
            ),
        }

    if order.get("forge_project_id"):
        return {
            "ok": True,
            "already_exists": True,
            "forge_project_id": order["forge_project_id"],
            "message": f"Forge project bestaat al: {order['forge_project_id']}",
        }

    # Build demo URL
    demo_pad = order.get("demo_pad", "")
    slug = demo_pad.split("/")[-1] if "/" in demo_pad else demo_pad
    demo_url = f"{base_url}/api/demos/{slug}" if slug and base_url else (f"/api/demos/{slug}" if slug else "")

    # Build raw input for the Forge V5 brief
    raw_input = (
        f"Bouw een volledige productie-website voor {order['bedrijfsnaam']} uit {order['plaats']} "
        f"({order['branche']}). "
        f"Gebruik de goedgekeurde demo als basis en maak een professionele, conversiegerichte website. "
        f"Demo: {demo_url or 'zie demo_pad'}. "
        f"Prijs vastgesteld op €{order.get('prijs', 0):.0f}."
    )

    # Persist the handoff package as the Forge project context
    project_id = f"orders-{order_id}-{uuid.uuid4().hex[:6]}"

    # Build brief directly (same shape as ForgeV5Runtime.start_project_brief)
    brief = {
        "project_id": project_id,
        "raw_input": raw_input,
        "title": f"Volledige website: {order['bedrijfsnaam']}",
        "summary": f"Productie-website voor {order['bedrijfsnaam']}, {order['branche']}, {order['plaats']}",
        "user_intent": raw_input,
        "desired_outcome": f"Professionele productie-website live voor {order['bedrijfsnaam']}",
        "scope": [
            f"Homepage met hero, diensten, voordelen, contact",
            f"Business: {order['bedrijfsnaam']} ({order['branche']}, {order['plaats']})",
            f"Goedgekeurde demo als stijl- en inhoudsreferentie",
            "Responsive design, klantgerichte CTA, SEO-basis",
        ],
        "constraints": ["Geen lorem ipsum", "Mobiel-responsive", "Conversiegericht"],
        "unknowns": [],
        "success_definition": "Website is live, volledig functioneel, en voldoet aan demo kwaliteitsstandaard.",
        "required_research": ["demo", "branche", "concurrenten"],
        "autonomy_level": "prepare_only",
        "project": {
            "source": "orders",
            "order_id": order_id,
            "bedrijfsnaam": order["bedrijfsnaam"],
            "branche": order["branche"],
            "plaats": order["plaats"],
            "demo_url": demo_url,
            "demo_pad": demo_pad,
            "prijs": order.get("prijs", 0),
        },
        "created_at": _ts(),
    }

    # Persist brief to Forge state
    _write_json(_FORGE_STATE / "briefs" / f"{_safe_token(project_id, 'project_id')}.json", brief)

    # Build handoff package
    handoff = {
        "handoff_id": f"ho-{uuid.uuid4().hex[:10]}",
        "source": "orders",
        "order_id": order_id,
        "forge_project_id": project_id,
        "status": "forge_project_created",
        "client_context": {
            "bedrijfsnaam": order["bedrijfsnaam"],
            "branche": order["branche"],
            "plaats": order["plaats"],
            "contact": order.get("contact", ""),
            "prijs": order.get("prijs", 0),
        },
        "demo_url": demo_url,
        "demo_pad": demo_pad,
        "approved_demo": {"url": demo_url, "path": demo_pad},
        "override_payment_used": override_payment,
        "created_at": _ts(),
    }

    # Persist handoff
    _write_json(_FORGE_STATE / "handoffs" / f"{_safe_token(project_id, 'project_id')}.json", handoff)
    _audit_handoff(handoff)

    # Store forge_project_id on the order
    forge_project_opslaan(order_id, project_id)

    return {
        "ok": True,
        "forge_project_id": project_id,
        "handoff": handoff,
        "brief": brief,
        "message": (
            f"Ascend Forge project aangemaakt voor {order['bedrijfsnaam']}. "
            f"Open de Ascend Forge pagina om de volledige website build te starten."
        ),
    }
