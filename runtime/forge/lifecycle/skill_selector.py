"""Select skills from the REAL library: runtime/config/skills_library.json.

Keyword/tag scoring against the existing 200-skill library — no parallel
catalog is invented. Path is env-overridable (SKILLS_LIBRARY_PATH).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_STOP = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "task", "using"}
_W_TAG, _W_NAME, _W_CATEGORY, _W_DESCRIPTION = 3.0, 2.0, 1.5, 1.0


def _library_path() -> Path:
    env = os.environ.get("SKILLS_LIBRARY_PATH", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "config" / "skills_library.json"


def _load_skills() -> list[dict]:
    try:
        data = json.loads(_library_path().read_text(encoding="utf-8"))
        skills = data.get("skills") if isinstance(data, dict) else None
        return [s for s in skills if isinstance(s, dict) and s.get("id")] if isinstance(skills, list) else []
    except Exception:
        return []


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower())
            if len(w) > 2 and w not in _STOP}


def select_skills(task: str, task_type: str, max_skills: int = 5) -> list[dict]:
    """-> top-scored library skills (each with 'match_score'), [] when no match."""
    query = _tokens(f"{task} {task_type}")
    if not query:
        return []
    scored: list[tuple[float, str, dict]] = []
    for s in _load_skills():
        tags = {str(t).lower() for t in s.get("tags") or []}
        name_toks = _tokens(s.get("name", "")) | _tokens(str(s.get("id", "")).replace("_", " "))
        score = (_W_TAG * len(query & tags)
                 + _W_NAME * len(query & name_toks)
                 + _W_CATEGORY * len(query & _tokens(s.get("category", "")))
                 + _W_DESCRIPTION * len(query & _tokens(s.get("description", ""))))
        if score > 0:
            scored.append((score, str(s["id"]), s))
    scored.sort(key=lambda t: (-t[0], t[1]))  # deterministic: score desc, id asc
    return [{**s, "match_score": round(sc, 2)} for sc, _, s in scored[:max(0, int(max_skills))]]
