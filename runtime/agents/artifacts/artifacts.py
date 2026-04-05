"""Artifacts — Track Agent Outputs as Deployable Artifacts for AI-EMPLOYEE.

Inspired by Paperclip's artifact model, every significant agent output
(code, reports, campaigns, business plans, etc.) is stored as an artifact
that can be reviewed, versioned, and deployed.

State:  ~/.ai-employee/state/artifacts/<artifact_id>.json
Index:  ~/.ai-employee/state/artifacts/index.json

Artifact types:
  code         — generated source code
  report       — research or analysis report
  campaign     — marketing campaign content
  business_plan — business plan document
  config       — configuration file
  image_prompt — generated image prompts
  other        — any other output

API (via problem-solver-ui server.py):
  GET  /api/artifacts                    — list artifacts (filter by type/agent)
  POST /api/artifacts                    — create a new artifact
  GET  /api/artifacts/{id}               — get artifact content
  PATCH /api/artifacts/{id}              — update artifact metadata/status
  DELETE /api/artifacts/{id}             — delete artifact
  POST /api/artifacts/{id}/deploy        — mark artifact as deployed
  GET  /api/artifacts/{id}/versions      — list artifact versions
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("artifacts")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
ARTIFACTS_DIR = AI_HOME / "state" / "artifacts"
INDEX_FILE = ARTIFACTS_DIR / "index.json"

VALID_TYPES = ("code", "report", "campaign", "business_plan", "config", "image_prompt", "other")
VALID_STATUSES = ("draft", "review", "approved", "deployed", "archived")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _artifact_file(artifact_id: str) -> Path:
    return ARTIFACTS_DIR / f"{artifact_id}.json"


def _load_index() -> dict:
    _ensure_dirs()
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {"artifacts": {}}


def _save_index(index: dict) -> None:
    _ensure_dirs()
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def _load_artifact(artifact_id: str) -> dict | None:
    f = _artifact_file(artifact_id)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return None


def _save_artifact(artifact: dict) -> None:
    _ensure_dirs()
    artifact["updated_at"] = _now_iso()
    _artifact_file(artifact["artifact_id"]).write_text(json.dumps(artifact, indent=2))
    # Update index with metadata only (no content)
    index = _load_index()
    index["artifacts"][artifact["artifact_id"]] = {
        "artifact_id": artifact["artifact_id"],
        "title": artifact.get("title"),
        "type": artifact.get("type"),
        "status": artifact.get("status"),
        "agent_id": artifact.get("agent_id"),
        "ticket_id": artifact.get("ticket_id"),
        "task_plan_id": artifact.get("task_plan_id"),
        "created_at": artifact.get("created_at"),
        "updated_at": artifact.get("updated_at"),
        "version": artifact.get("version", 1),
        "content_length": len(str(artifact.get("content", ""))),
    }
    _save_index(index)


# ── Public API ────────────────────────────────────────────────────────────────


def create_artifact(
    title: str,
    content: str,
    artifact_type: str = "other",
    agent_id: str | None = None,
    ticket_id: str | None = None,
    task_plan_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create a new artifact from agent output."""
    if artifact_type not in VALID_TYPES:
        artifact_type = "other"
    artifact_id = str(uuid.uuid4())[:12]
    now = _now_iso()
    artifact: dict = {
        "artifact_id": artifact_id,
        "title": title,
        "type": artifact_type,
        "status": "draft",
        "content": content,
        "agent_id": agent_id,
        "ticket_id": ticket_id,
        "task_plan_id": task_plan_id,
        "metadata": metadata or {},
        "version": 1,
        "versions": [],
        "created_at": now,
        "updated_at": now,
        "deployed_at": None,
    }
    _save_artifact(artifact)
    logger.info("artifacts: created %s '%s' (%s)", artifact_type, title[:50], artifact_id)
    return artifact


def get_artifact(artifact_id: str) -> dict | None:
    return _load_artifact(artifact_id)


def list_artifacts(
    artifact_type: str | None = None,
    agent_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return artifact metadata from the index."""
    index = _load_index()
    items = list(index["artifacts"].values())
    if artifact_type:
        items = [a for a in items if a.get("type") == artifact_type]
    if agent_id:
        items = [a for a in items if a.get("agent_id") == agent_id]
    if status:
        items = [a for a in items if a.get("status") == status]
    items.sort(key=lambda a: a.get("updated_at", ""), reverse=True)
    return items[:limit]


def update_artifact(
    artifact_id: str,
    title: str | None = None,
    content: str | None = None,
    status: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Update an artifact (creates a version snapshot on content change)."""
    artifact = _load_artifact(artifact_id)
    if artifact is None:
        raise ValueError(f"Artifact '{artifact_id}' not found")

    if content is not None and content != artifact.get("content"):
        # Save version snapshot before overwriting
        version_snapshot = {
            "version": artifact.get("version", 1),
            "content": artifact.get("content"),
            "updated_at": artifact.get("updated_at"),
        }
        artifact.setdefault("versions", []).append(version_snapshot)
        artifact["versions"] = artifact["versions"][-10:]  # keep last 10 versions
        artifact["content"] = content
        artifact["version"] = artifact.get("version", 1) + 1

    if title is not None:
        artifact["title"] = title
    if status is not None and status in VALID_STATUSES:
        artifact["status"] = status
    if metadata is not None:
        artifact.setdefault("metadata", {}).update(metadata)

    _save_artifact(artifact)
    return artifact


def deploy_artifact(artifact_id: str, deploy_notes: str = "") -> dict:
    """Mark an artifact as deployed."""
    artifact = _load_artifact(artifact_id)
    if artifact is None:
        raise ValueError(f"Artifact '{artifact_id}' not found")
    artifact["status"] = "deployed"
    artifact["deployed_at"] = _now_iso()
    artifact.setdefault("metadata", {})["deploy_notes"] = deploy_notes
    _save_artifact(artifact)
    return artifact


def delete_artifact(artifact_id: str) -> bool:
    index = _load_index()
    if artifact_id not in index["artifacts"]:
        return False
    del index["artifacts"][artifact_id]
    _save_index(index)
    f = _artifact_file(artifact_id)
    if f.exists():
        f.unlink()
    return True


def get_versions(artifact_id: str) -> list[dict]:
    """Return version history for an artifact."""
    artifact = _load_artifact(artifact_id)
    if artifact is None:
        return []
    versions = artifact.get("versions", [])
    # Include current as last version
    versions = list(versions) + [{
        "version": artifact.get("version", 1),
        "content": artifact.get("content"),
        "updated_at": artifact.get("updated_at"),
        "is_current": True,
    }]
    return versions
