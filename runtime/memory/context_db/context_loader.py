"""Tiered context loading (OpenViking L0/L1/L2 pattern, rebuilt natively).

Tiers
-----
- ``L0`` — summary only (~200 chars, generated on write): cheapest view.
- ``L1`` — summary + key metadata + first ~1500 chars of content.
- ``L2`` — full content.

``load`` enforces a character budget (``max_chars``, default 12000): once
adding the next node would exceed it, loading stops and the result carries
``truncated: True``. A single over-budget node is trimmed rather than
silently dropped.
"""
from __future__ import annotations

from typing import Any

from memory.context_db.context_tree import ContextTree

LEVELS = ("L0", "L1", "L2")
L1_PREVIEW_CHARS = 1500
DEFAULT_BUDGET = 12000


def _resolve(tree: ContextTree, item: Any) -> dict[str, Any] | None:
    """Accept a node path or a stable node id."""
    item = str(item or "").strip()
    if not item:
        return None
    if "/" in item:
        return tree.read(item)
    return tree.read_by_id(item) or tree.read(item)


def build_view(node: dict[str, Any], level: str) -> dict[str, Any]:
    """One node → one tiered view dict (no budget logic here)."""
    view: dict[str, Any] = {
        "id": node.get("id"),
        "path": node.get("path"),
        "summary": node.get("summary", ""),
        "level": level,
    }
    if level in ("L1", "L2"):
        view["metadata"] = node.get("metadata", {})
        view["updated_at"] = node.get("updated_at")
        view["content_preview"] = str(node.get("content", ""))[:L1_PREVIEW_CHARS]
    if level == "L2":
        view["content"] = str(node.get("content", ""))
    return view


def _view_cost(view: dict[str, Any]) -> int:
    return (len(view.get("summary", ""))
            + len(view.get("content_preview", "") or "")
            + len(view.get("content", "") or ""))


def load(items: list[Any], level: str = "L0", max_chars: int = DEFAULT_BUDGET,
         tree: ContextTree | None = None,
         tenant: str = "default") -> dict[str, Any]:
    """Load tiered views for node ids/paths under a hard character budget.

    Returns ``{level, views, chars_used, truncated, missing}``.
    """
    if level not in LEVELS:
        level = "L0"
    tree = tree or ContextTree(tenant=tenant)
    max_chars = max(1, int(max_chars or DEFAULT_BUDGET))

    views: list[dict[str, Any]] = []
    missing: list[str] = []
    used = 0
    truncated = False

    for item in items or []:
        node = _resolve(tree, item)
        if node is None:
            missing.append(str(item))
            continue
        view = build_view(node, level)
        cost = _view_cost(view)
        if used + cost > max_chars:
            if not views:
                # First node alone busts the budget — trim instead of dropping.
                room = max_chars - len(view.get("summary", ""))
                if "content_preview" in view:
                    view["content_preview"] = view["content_preview"][:max(0, room)]
                    room -= len(view["content_preview"])
                if "content" in view:
                    view["content"] = view["content"][:max(0, room)]
                views.append(view)
                used += _view_cost(view)
            truncated = True
            break
        views.append(view)
        used += cost

    return {"level": level, "views": views, "chars_used": used,
            "truncated": truncated, "missing": missing}
