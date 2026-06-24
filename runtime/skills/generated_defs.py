"""Loader for the generated definitions of previously-undefined agent-advertised
skills (produced by scripts/generate_undefined_skill_defs.py). The executable engine
turns each into a validated executable skill. Never raises — returns {} on any error.
"""
from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "config" / "skills_generated.json"


def load_generated_defs() -> dict[str, dict]:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        return {e["id"]: e for e in data.get("skills", []) if isinstance(e, dict) and e.get("id")}
    except Exception:
        return {}
