"""Heuristic page audit: hierarchy / consistency / density scores + A-F grade.

Scores derive from preflight violations plus structure signals (semantic tags,
component-kit imports). Deterministic deductions — no taste-by-vibes.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from forge.ui_quality.frontend_preflight import _max_read_bytes, preflight

_SEMANTIC_TAGS = re.compile(r"<(h[1-6]|header|section|main|nav|aside|article)\b")
_KIT_IMPORT = re.compile(r"""from\s+['"][^'"]*(nexus[-_]?ui|components/nexus)""", re.IGNORECASE)
_GRADES = ((90, "A"), (80, "B"), (70, "C"), (60, "D"))

_D_NO_SEMANTIC = 30          # hierarchy: no semantic structure at all
_D_PLACEHOLDER = 20          # hierarchy+consistency: placeholder content
_D_HARDCODED_COLOR = 10      # consistency: per hardcoded color (capped by floor 0)
_D_INLINE_DENSITY = 25       # density: inline-style density violation
_D_MISSING_EMPTY = 15        # density/UX: list without empty state
_D_CONSOLE_LOG = 5           # consistency: per console.log
_B_KIT_IMPORT = 10           # consistency bonus: uses the component kit


def _clamp(v: int) -> int:
    return max(0, min(100, v))


def audit(page_path: str) -> dict:
    """-> {scores: {hierarchy, consistency, density}, findings, grade: 'A'-'F'}"""
    pf = preflight([page_path])
    path = Path(page_path)
    text = ""
    if path.is_file():
        try:
            text = path.read_bytes()[:_max_read_bytes()].decode("utf-8", errors="replace")
        except OSError:
            pass

    by_rule = Counter(v["rule"] for v in pf["violations"])
    findings = list(pf["violations"])

    hierarchy = consistency = density = 100
    if not _SEMANTIC_TAGS.search(text):
        hierarchy -= _D_NO_SEMANTIC
        findings.append({"file": page_path, "rule": "no_semantic_structure",
                         "detail": "no semantic tags (h1-h6/header/section/main/nav) found"})
    hierarchy -= _D_PLACEHOLDER * min(1, by_rule["placeholder_text"])
    consistency -= (_D_PLACEHOLDER * min(1, by_rule["placeholder_text"])
                    + _D_HARDCODED_COLOR * by_rule["hardcoded_color"]
                    + _D_CONSOLE_LOG * by_rule["console_log_leftover"])
    if _KIT_IMPORT.search(text):
        consistency += _B_KIT_IMPORT
        findings.append({"file": page_path, "rule": "kit_usage",
                         "detail": "imports from the nexus-ui component kit (good)"})
    density -= (_D_INLINE_DENSITY * by_rule["inline_style_density"]
                + _D_MISSING_EMPTY * by_rule["missing_empty_state"])

    scores = {"hierarchy": _clamp(hierarchy), "consistency": _clamp(consistency),
              "density": _clamp(density)}
    avg = sum(scores.values()) / len(scores)
    grade = next((g for floor, g in _GRADES if avg >= floor), "F")
    return {"scores": scores, "findings": findings, "grade": grade}
