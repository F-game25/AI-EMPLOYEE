"""Static anti-slop preflight over real frontend files. Bounded reads.

Rules: placeholder text, inline-style density, missing empty-state next to
``.map(``, hardcoded hex colors (JS/JSX — should be var(--token)), and
console.log leftovers. passed=True only with zero violations.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_PLACEHOLDER = re.compile(r"\b(TODO|FIXME|PLACEHOLDER|lorem ipsum|lorem|coming soon)\b", re.IGNORECASE)
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_CONSOLE_LOG = re.compile(r"\bconsole\.log\s*\(")
_EMPTY_HANDLING = re.compile(r"EmptyState|empty", re.IGNORECASE)
_JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}


def _max_read_bytes() -> int:
    return int(os.environ.get("FORGE_UI_MAX_READ_KB", "200")) * 1024


def _inline_style_threshold() -> int:
    return int(os.environ.get("FORGE_UI_MAX_INLINE_STYLES", "5"))


def preflight(paths: list) -> dict:
    """-> {violations: [{file, line?, rule, detail}], passed: bool}"""
    violations: list[dict] = []
    for p in paths or []:
        path = Path(p)
        if not path.is_file():
            violations.append({"file": str(p), "rule": "missing_file", "detail": "file not found"})
            continue
        try:
            text = path.read_bytes()[:_max_read_bytes()].decode("utf-8", errors="replace")
        except OSError as exc:
            violations.append({"file": str(p), "rule": "read_error", "detail": str(exc)})
            continue

        is_js = path.suffix.lower() in _JS_EXTENSIONS
        inline_styles = 0
        for lineno, line in enumerate(text.splitlines(), 1):
            m = _PLACEHOLDER.search(line)
            if m:
                violations.append({"file": str(p), "line": lineno, "rule": "placeholder_text",
                                   "detail": f"placeholder marker '{m.group(0)}'"})
            inline_styles += line.count("style={{")
            if is_js:
                if _CONSOLE_LOG.search(line):
                    violations.append({"file": str(p), "line": lineno, "rule": "console_log_leftover",
                                       "detail": "console.log left in frontend code"})
                for hexval in _HEX_COLOR.findall(line):
                    violations.append({"file": str(p), "line": lineno, "rule": "hardcoded_color",
                                       "detail": f"hardcoded {hexval} — use var(--token) instead"})

        if inline_styles > _inline_style_threshold():
            violations.append({"file": str(p), "rule": "inline_style_density",
                               "detail": f"{inline_styles} inline style={{{{}}}} blocks "
                                         f"(threshold {_inline_style_threshold()})"})
        if ".map(" in text and not _EMPTY_HANDLING.search(text):
            violations.append({"file": str(p), "rule": "missing_empty_state",
                               "detail": "renders a list via .map( but has no empty-state handling"})

    return {"violations": violations, "passed": not violations}
