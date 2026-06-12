"""Infer the design language from real CSS: tokens, colors, spacing, fonts.

Honest scanner — returns only what it finds in the given files (bounded
reads); empty collections when nothing is found. No invention.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

from forge.ui_quality.frontend_preflight import _max_read_bytes

_VAR_DEF = re.compile(r"--([\w-]+)\s*:\s*([^;}]+)")
_COLOR_VALUE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")
_SPACING_VALUE = re.compile(r"\b(\d+(?:\.\d+)?)(px|rem|em)\b")
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)


def _top_n() -> int:
    return int(os.environ.get("FORGE_UI_TOKEN_TOP", "10"))


def infer(paths: list) -> dict:
    """-> {tokens: {colors, spacing, fonts, variables}, source: 'scanned', files_scanned}"""
    colors: Counter = Counter()
    spacing: Counter = Counter()
    fonts: Counter = Counter()
    variables: dict[str, str] = {}
    scanned = 0

    for p in paths or []:
        path = Path(p)
        if not path.is_file():
            continue
        try:
            text = path.read_bytes()[:_max_read_bytes()].decode("utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for name, value in _VAR_DEF.findall(text):
            variables[name] = value.strip()
        colors.update(_COLOR_VALUE.findall(text))
        spacing.update(f"{num}{unit}" for num, unit in _SPACING_VALUE.findall(text))
        fonts.update(v.strip() for v in _FONT_FAMILY.findall(text))

    n = _top_n()
    return {
        "tokens": {
            "colors": [{"value": v, "count": c} for v, c in colors.most_common(n)],
            "spacing": [{"value": v, "count": c} for v, c in spacing.most_common(n)],
            "fonts": [{"value": v, "count": c} for v, c in fonts.most_common(n)],
            "variables": variables,
        },
        "source": "scanned",
        "files_scanned": scanned,
    }
