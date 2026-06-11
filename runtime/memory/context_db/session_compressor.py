"""Session compression → durable context nodes (heuristic, no-fabrication).

``compress_session(messages, project_id)`` scans a conversation for durable
material and writes verbatim extracts into the context tree:

- decisions   ("we decided …", "decision: …", "besloten …")
                → ``/project/<id>/decisions/``
- preferences ("i prefer …", "always use …", "voorkeur …")
                → ``/project/<id>/memory/``
- project facts (deadline/budget/stack/launch statements)
                → ``/project/<id>/memory/``
- tool results worth keeping (role == "tool", substantial output)
                → ``/project/<id>/memory/`` (truncated)

No LLM call required: extraction is pure regex/sentence heuristics, and only
sentences that literally appear in the messages are persisted — nothing is
invented. Optional polish behind ``CONTEXT_DB_LLM_COMPRESS=1`` rewrites the
extract via ``engine.api.generate`` (defensive: any failure keeps the
verbatim heuristic text).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Any

from memory.context_db.context_permissions import valid_tenant
from memory.context_db.context_tree import ContextTree

logger = logging.getLogger("context_db.compressor")

_DECISION_RE = re.compile(
    r"\b(we (?:have )?decided|decision:|we agreed|agreed to|"
    r"we(?:'ll| will) (?:go with|use)|let's go with|final decision|"
    r"besloten|we kiezen(?: voor)?)\b", re.IGNORECASE)
_PREFERENCE_RE = re.compile(
    r"\b(i prefer|we prefer|prefer(?:s)? to|please always|always use|"
    r"never use|voorkeur|ik wil graag|liever)\b", re.IGNORECASE)
_FACT_RE = re.compile(
    r"\b(deadline|budget|launch date|the stack is|stack:|we use|runs on|"
    r"the project uses|repository is|repo is)\b", re.IGNORECASE)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOOL_RESULT_MIN_CHARS = 80
_TOOL_RESULT_KEEP_CHARS = 500
_MAX_NODES_PER_SESSION = 30


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(str(text or "")) if s.strip()]


def _classify(sentence: str) -> str | None:
    if _DECISION_RE.search(sentence):
        return "decision"
    if _PREFERENCE_RE.search(sentence):
        return "preference"
    if _FACT_RE.search(sentence):
        return "fact"
    return None


def _polish(text: str) -> str:
    """Optional LLM condensation — strictly opt-in and failure-tolerant."""
    if os.environ.get("CONTEXT_DB_LLM_COMPRESS") != "1":
        return text
    try:
        from engine.api import generate
        out = generate(
            prompt=("Rewrite this extracted note as one concise factual "
                    "sentence. Do not add information.\n\n" + text),
            system="You condense notes. Never invent facts.", timeout=30)
        out = (out or "").strip()
        return out if out else text
    except Exception as exc:  # noqa: BLE001 — keep verbatim extract
        logger.info("LLM polish unavailable, keeping verbatim text: %s", exc)
        return text


def compress_session(messages: list[dict[str, Any]],
                     project_id: str = "default",
                     tree: ContextTree | None = None,
                     tenant: str = "default") -> dict[str, Any]:
    """Extract durable facts/decisions from *messages* into the tree.

    Returns ``{written_nodes: [paths], counts: {...}}``. Empty or
    non-matching input writes nothing.
    """
    if not isinstance(messages, list) or not messages:
        return {"written_nodes": [], "counts": {}}
    pid = project_id if valid_tenant(project_id) else "default"
    tree = tree or ContextTree(tenant=tenant)

    extracts: list[tuple[str, str]] = []  # (kind, text)
    seen: set[str] = set()
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).lower()
        content = str(msg.get("content", "") or "")
        if not content.strip():
            continue
        if role == "tool":
            if len(content.strip()) >= _TOOL_RESULT_MIN_CHARS:
                text = content.strip()[:_TOOL_RESULT_KEEP_CHARS]
                key = hashlib.sha1(text.encode()).hexdigest()
                if key not in seen:
                    seen.add(key)
                    extracts.append(("tool_result", text))
            continue
        for sentence in _sentences(content):
            kind = _classify(sentence)
            if kind is None:
                continue
            key = hashlib.sha1(sentence.lower().encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            extracts.append((kind, sentence))
        if len(extracts) >= _MAX_NODES_PER_SESSION:
            break

    written: list[str] = []
    counts: dict[str, int] = {}
    session_ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    for i, (kind, text) in enumerate(extracts[:_MAX_NODES_PER_SESSION]):
        category = "decisions" if kind == "decision" else "memory"
        digest = hashlib.sha1(text.encode()).hexdigest()[:8]
        path = f"/project/{pid}/{category}/{kind}-{session_ts}-{i}-{digest}"
        try:
            tree.write(path, _polish(text), metadata={
                "source": "session_compressor", "kind": kind,
                "project_id": pid, "verbatim": True,
            })
            written.append(path)
            counts[kind] = counts.get(kind, 0) + 1
        except Exception as exc:  # noqa: BLE001 — partial success is honest
            logger.warning("could not write %s: %s", path, exc)

    return {"written_nodes": written, "counts": counts}
