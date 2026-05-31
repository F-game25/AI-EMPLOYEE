"""Plugin review workflow — pending → approved/rejected with audit trail.

State machine:
    submitted  →  pending_review  →  approved
                                  →  rejected
    approved   →  suspended
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REVIEWS_PATH = Path(os.path.expanduser("~/.ai-employee/state/plugin_reviews.jsonl"))

# Valid state transitions
_TRANSITIONS: dict[str, set[str]] = {
    "pending_review": {"approved", "rejected"},
    "approved":       {"suspended"},
    "rejected":       set(),
    "suspended":      {"approved"},
}

# Risk weights per permission
_RISK_WEIGHTS: dict[str, float] = {
    "write_vault":        0.30,
    "write_tasks":        0.20,
    "call_llm":           0.20,
    "web_search":         0.15,
    "send_notifications": 0.10,
    "read_vault":         0.05,
    "read_tasks":         0.05,
    "read_agents":        0.05,
}


def compute_risk_score(manifest: dict) -> float:
    """Return a risk score in [0.0, 1.0] based on declared permissions.

    Higher = more dangerous.  Score is the sum of per-permission weights,
    capped at 1.0.
    """
    total = sum(
        _RISK_WEIGHTS.get(p, 0.0)
        for p in manifest.get("permissions", [])
    )
    return min(total, 1.0)


@dataclass
class PluginReview:
    plugin_id:    str
    plugin_name:  str
    tenant_id:    str
    submitted_by: str
    submitted_at: str          # ISO-8601
    status:       str          # pending_review | approved | rejected | suspended
    reviewer:     Optional[str]
    reviewed_at:  Optional[str]
    notes:        str
    manifest_hash: str          # SHA-256 of manifest JSON
    risk_score:   float        # 0.0 – 1.0


class ReviewStore:
    """JSONL-backed persistence for plugin reviews.

    Each state change appends a new record — the file is an audit log.
    The current state of a plugin is derived from the LAST record for that
    plugin_id.
    """

    def __init__(self, path: Path = _REVIEWS_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, review: PluginReview) -> None:
        with self._path.open("a") as fh:
            fh.write(json.dumps(asdict(review)) + "\n")

    def _all(self) -> list[PluginReview]:
        """Read every record in order."""
        if not self._path.exists():
            return []
        reviews = []
        with self._path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    reviews.append(PluginReview(**json.loads(line)))
                except Exception:
                    pass  # corrupt line — skip
        return reviews

    def _latest(self) -> dict[str, PluginReview]:
        """Return a map plugin_id → latest PluginReview record."""
        latest: dict[str, PluginReview] = {}
        for r in self._all():
            latest[r.plugin_id] = r
        return latest

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        plugin_id: str,
        plugin_name: str,
        tenant_id: str,
        submitted_by: str,
        manifest: dict,
    ) -> PluginReview:
        """Create a new review in pending_review state.

        If a review already exists for this plugin_id the existing record is
        superseded (new submission resets to pending_review).
        """
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        review = PluginReview(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            tenant_id=tenant_id,
            submitted_by=submitted_by,
            submitted_at=_iso_now(),
            status="pending_review",
            reviewer=None,
            reviewed_at=None,
            notes="",
            manifest_hash=hashlib.sha256(manifest_bytes).hexdigest(),
            risk_score=compute_risk_score(manifest),
        )
        self._append(review)
        logger.info(
            "Plugin review submitted: %s (risk=%.2f)", plugin_id, review.risk_score
        )
        return review

    def _transition(
        self,
        plugin_id: str,
        new_status: str,
        reviewer: str,
        notes: str = "",
    ) -> PluginReview:
        latest = self._latest()
        current = latest.get(plugin_id)
        if current is None:
            raise KeyError(f"No review found for plugin '{plugin_id}'")
        if new_status not in _TRANSITIONS.get(current.status, set()):
            raise ValueError(
                f"Cannot transition '{plugin_id}' from '{current.status}' to '{new_status}'"
            )
        updated = PluginReview(
            **{**asdict(current),
               "status": new_status,
               "reviewer": reviewer,
               "reviewed_at": _iso_now(),
               "notes": notes},
        )
        self._append(updated)
        logger.info("Plugin %s → %s by %s", plugin_id, new_status, reviewer)
        return updated

    def approve(self, plugin_id: str, reviewer: str, notes: str = "") -> PluginReview:
        """Approve a pending_review (or re-approve a suspended) plugin."""
        return self._transition(plugin_id, "approved", reviewer, notes)

    def reject(self, plugin_id: str, reviewer: str, notes: str = "") -> PluginReview:
        """Reject a pending_review plugin."""
        return self._transition(plugin_id, "rejected", reviewer, notes)

    def suspend(self, plugin_id: str, reviewer: str, notes: str = "") -> PluginReview:
        """Suspend an approved plugin."""
        return self._transition(plugin_id, "suspended", reviewer, notes)

    def get(self, plugin_id: str) -> Optional[PluginReview]:
        """Return the current (latest) review for plugin_id, or None."""
        return self._latest().get(plugin_id)

    def list_pending(self) -> list[PluginReview]:
        """Return all reviews currently in pending_review state."""
        return [r for r in self._latest().values() if r.status == "pending_review"]

    def list_all(self, status: str | None = None) -> list[PluginReview]:
        """Return latest review per plugin, optionally filtered by status."""
        reviews = list(self._latest().values())
        if status:
            reviews = [r for r in reviews if r.status == status]
        return sorted(reviews, key=lambda r: r.submitted_at, reverse=True)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: Optional[ReviewStore] = None


def get_review_store() -> ReviewStore:
    global _store
    if _store is None:
        _store = ReviewStore()
    return _store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
