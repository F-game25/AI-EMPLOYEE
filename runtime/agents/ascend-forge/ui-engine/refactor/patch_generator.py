"""refactor/patch_generator.py — Minimal surgical diff with risk annotations.

Generates a unified diff between the original source and the improved source
produced by ui_optimizer.  Each diff is annotated with:
  - risk level  (low / medium / high)
  - impacted elements  (list of JSX tags, props, classNames affected)
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any


# ── Public API ────────────────────────────────────────────────────────────────

def generate_patch(
    original: str,
    improved: str,
    filename: str = "<unknown>",
) -> dict[str, Any]:
    """Compute a unified diff and return an annotated patch dict.

    Args:
        original: Original component source code.
        improved: Improved component source code.
        filename: Source filename (used in diff header).

    Returns a dict with keys:
        diff            — unified-diff string
        hunks           — list of parsed hunk objects
        risk_level      — "low" | "medium" | "high"
        impacted        — list of impacted element descriptors
        lines_added     — count
        lines_removed   — count
        is_empty        — True when original == improved
    """
    original_lines = original.splitlines(keepends=True)
    improved_lines = improved.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            improved_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )

    diff_str     = "\n".join(diff_lines)
    is_empty     = (original == improved)
    hunks        = _parse_hunks(diff_lines)
    lines_added  = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    lines_removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

    risk_level = _assess_risk(original, improved, lines_added, lines_removed)
    impacted   = _find_impacted_elements(original, improved)

    return {
        "filename":      filename,
        "diff":          diff_str,
        "hunks":         hunks,
        "risk_level":    risk_level,
        "impacted":      impacted,
        "lines_added":   lines_added,
        "lines_removed": lines_removed,
        "is_empty":      is_empty,
    }


def patch_to_json(
    original: str,
    improved: str,
    filename: str = "<unknown>",
) -> str:
    """Return the patch dict as a JSON string (diff excluded for brevity)."""
    patch = generate_patch(original, improved, filename)
    serializable = {k: v for k, v in patch.items() if k != "diff"}
    return json.dumps(serializable, indent=2)


# ── Hunk parser ───────────────────────────────────────────────────────────────

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_hunks(diff_lines: list[str]) -> list[dict[str, Any]]:
    """Parse unified-diff lines into structured hunk objects."""
    hunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in diff_lines:
        m = _HUNK_HEADER_RE.match(line)
        if m:
            if current:
                hunks.append(current)
            current = {
                "old_start":  int(m.group(1)),
                "old_count":  int(m.group(2) or 1),
                "new_start":  int(m.group(3)),
                "new_count":  int(m.group(4) or 1),
                "lines":      [],
            }
        elif current is not None:
            current["lines"].append(line)

    if current:
        hunks.append(current)

    return hunks


# ── Risk assessment ───────────────────────────────────────────────────────────

# Patterns that imply high-risk changes
_HIGH_RISK_PATTERNS = [
    re.compile(r"\bimport\b"),           # imports changed
    re.compile(r"\bexport\b"),           # exports changed
    re.compile(r"\bprops\b"),            # prop interface changed
    re.compile(r"\buseEffect\b"),        # effect hooks changed
    re.compile(r"\buseState\b"),         # state hooks changed
    re.compile(r"onClick|onChange|onSubmit"),  # event handlers
]

_MEDIUM_RISK_PATTERNS = [
    re.compile(r"style\s*="),
    re.compile(r"className"),
    re.compile(r"\bif\b|\belse\b|\bswitch\b"),
]


def _assess_risk(
    original: str,
    improved: str,
    lines_added: int,
    lines_removed: int,
) -> str:
    if lines_added == 0 and lines_removed == 0:
        return "low"

    change_ratio = (lines_added + lines_removed) / max(len(original.splitlines()), 1)

    # Only examine the actual changed lines (prefixed with + or -) for risk signals,
    # not the context lines, to avoid false-positive high-risk classifications.
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(),
            improved.splitlines(),
            lineterm="",
        )
    )
    changed_text = "\n".join(
        l[1:] for l in diff_lines
        if (l.startswith("+") and not l.startswith("+++"))
        or (l.startswith("-") and not l.startswith("---"))
    )

    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(changed_text):
            if change_ratio > 0.2:
                return "high"
            return "medium"

    for pattern in _MEDIUM_RISK_PATTERNS:
        if pattern.search(changed_text):
            return "medium"

    if change_ratio > 0.3:
        return "high"
    if change_ratio > 0.1:
        return "medium"
    return "low"


# ── Impacted element finder ───────────────────────────────────────────────────

_JSX_TAG_RE    = re.compile(r"<([A-Z][A-Za-z0-9.]*|[a-z][a-z0-9-]*)")
_CLASS_RE      = re.compile(r'className\s*=\s*["\']([^"\']+)["\']')
_PROP_RE       = re.compile(r"\b(\w+)\s*=\s*\{")


def _find_impacted_elements(original: str, improved: str) -> list[str]:
    """Return a de-duplicated list of element descriptors that changed."""
    def _extract(src: str) -> set[str]:
        items: set[str] = set()
        items.update(f"<{m.group(1)}>" for m in _JSX_TAG_RE.finditer(src))
        items.update(f".{cls}" for m in _CLASS_RE.finditer(src) for cls in m.group(1).split())
        items.update(f"prop:{m.group(1)}" for m in _PROP_RE.finditer(src))
        return items

    orig_elements  = _extract(original)
    impr_elements  = _extract(improved)
    changed        = orig_elements.symmetric_difference(impr_elements)
    return sorted(changed)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 patch_generator.py <original_file> <improved_file>", file=sys.stderr)
        sys.exit(1)

    orig_src = Path(sys.argv[1]).read_text(encoding="utf-8")
    impr_src = Path(sys.argv[2]).read_text(encoding="utf-8")
    patch    = generate_patch(orig_src, impr_src, filename=sys.argv[1])

    print(patch["diff"])
    print("\n--- Patch Metadata ---")
    meta = {k: v for k, v in patch.items() if k not in ("diff", "hunks")}
    print(json.dumps(meta, indent=2))
