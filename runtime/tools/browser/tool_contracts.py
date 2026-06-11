"""Tool contracts for the browser ops — mirrors the capability registry seeds.

``check_registry_drift()`` verifies the contracts and the companion capability
registry agree (presence, risk level, approval flag); the test suite calls it
so the two can never silently diverge.
"""
from __future__ import annotations

TOOL_CONTRACTS: dict[str, dict] = {
    "browser.open": {
        "name": "browser.open",
        "description": "Open a URL in a fresh ephemeral browser session.",
        "args": {"url": "str", "profile": "str?"},
        "returns": {"session_id": "str", "title": "str", "url": "str"},
        "risk_level": "L0",
        "requires_approval": False,
    },
    "browser.snapshot": {
        "name": "browser.snapshot",
        "description": "Accessibility-style snapshot with stable @eN refs.",
        "args": {"session_id": "str"},
        "returns": {"tree": "dict", "refs": "list", "ref_count": "int",
                    "truncated": "bool"},
        "risk_level": "L0",
        "requires_approval": False,
    },
    "browser.extract": {
        "name": "browser.extract",
        "description": "Extract text/html/value/title/url/attr:<name> (≤20KB).",
        "args": {"session_id": "str", "kind": "str", "target": "str?"},
        "returns": {"data": "str", "truncated": "bool"},
        "risk_level": "L0",
        "requires_approval": False,
    },
    "browser.capture": {
        "name": "browser.capture",
        "description": "Screenshot (PNG) or PDF of the page, rotated dir.",
        "args": {"session_id": "str", "kind": "str?"},
        "returns": {"path": "str"},
        "risk_level": "L0",
        "requires_approval": False,
    },
    "browser.close": {
        "name": "browser.close",
        "description": "Close one session, or all when no session_id given.",
        "args": {"session_id": "str?"},
        "returns": {"closed": "bool|int"},
        "risk_level": "L0",
        "requires_approval": False,
    },
    "browser.act": {
        "name": "browser.act",
        "description": "Click/fill/type/press/scroll/select on a live page — "
                       "interacts with an external website.",
        "args": {"session_id": "str", "action": "str", "target": "str?",
                 "value": "any?"},
        "returns": {"ok": "bool", "side_effect_class": "str"},
        "risk_level": "L3",
        "requires_approval": True,
    },
}


def check_registry_drift() -> list[str]:
    """Empty list when contracts ↔ capability registry agree; else problems."""
    from companion.capability_registry import get_capability_registry
    reg = get_capability_registry()
    problems: list[str] = []
    for cap_id, contract in TOOL_CONTRACTS.items():
        cap = reg.get(cap_id)
        if cap is None:
            problems.append(f"{cap_id}: in contracts but missing from registry")
            continue
        if cap.risk_level != contract["risk_level"]:
            problems.append(f"{cap_id}: risk_level drift "
                            f"(contract={contract['risk_level']}, registry={cap.risk_level})")
        if cap.requires_approval != contract["requires_approval"]:
            problems.append(f"{cap_id}: requires_approval drift "
                            f"(contract={contract['requires_approval']}, "
                            f"registry={cap.requires_approval})")
    registry_browser_ids = {c.id for c in reg.by_subsystem("browser")}
    for missing in registry_browser_ids - set(TOOL_CONTRACTS):
        problems.append(f"{missing}: in registry but missing from contracts")
    return problems
