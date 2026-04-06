"""scanner/style_analyzer.py — Design-debt detector.

Analyses a parsed component (output of component_parser.parse_component)
against design_system.json and produces a structured "design debt" report.

Violations detected:
  - non-system spacing values
  - duplicated style logic
  - inconsistent component patterns
  - hardcoded colours outside the token palette
  - missing / inline font-size outside the type scale
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


# ── Configuration ─────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
_DS_PATH = _HERE.parent / "config" / "design_system.json"


def _load_design_system(path: Path | None = None) -> dict:
    p = path or _DS_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

def analyze(
    parsed_component: dict[str, Any],
    design_system: dict | None = None,
) -> dict[str, Any]:
    """Return a structured design-debt report for *parsed_component*.

    Args:
        parsed_component: Output of ``component_parser.parse_component()``.
        design_system:    Loaded design_system.json dict (loaded from disk when
                          ``None``).

    Returns a dict with keys:
        violations  — list of violation dicts (type, detail, line, severity)
        summary     — { total, critical, warning, info }
        debt_score  — float 0–100 (higher = more debt)
    """
    ds = design_system or _load_design_system()
    violations: list[dict[str, Any]] = []

    _check_spacing(parsed_component, ds, violations)
    _check_typography(parsed_component, ds, violations)
    _check_colors(parsed_component, ds, violations)
    _check_duplicates(parsed_component, violations)
    _check_inline_vs_class(parsed_component, violations)

    severity_map = {"critical": 3, "warning": 2, "info": 1}
    summary = {
        "total":    len(violations),
        "critical": sum(1 for v in violations if v["severity"] == "critical"),
        "warning":  sum(1 for v in violations if v["severity"] == "warning"),
        "info":     sum(1 for v in violations if v["severity"] == "info"),
    }
    # Debt score: weighted sum capped at 100
    raw = (summary["critical"] * 10 + summary["warning"] * 4 + summary["info"] * 1)
    debt_score = min(100.0, float(raw))

    return {
        "filename":   parsed_component.get("filename", "<unknown>"),
        "violations": violations,
        "summary":    summary,
        "debt_score": debt_score,
    }


# ── Internal checkers ─────────────────────────────────────────────────────────

def _check_spacing(
    comp: dict[str, Any],
    ds: dict,
    violations: list,
) -> None:
    """Flag inline-style spacing values that are not on the design system scale."""
    scale: list[int] = ds.get("spacing", {}).get("scale", [])
    if not scale:
        return

    px_re = re.compile(r"^(\d+(?:\.\d+)?)px$")

    def _is_off_scale(value: str) -> bool:
        m = px_re.match(value.strip())
        if not m:
            return False
        num = float(m.group(1))
        return num not in scale

    for style_obj in comp.get("inline_styles", []):
        props = style_obj.get("properties", {})
        for css_prop, css_val in props.items():
            if css_prop in (
                "margin", "marginTop", "marginRight", "marginBottom", "marginLeft",
                "padding", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
                "gap", "rowGap", "columnGap",
            ):
                if _is_off_scale(css_val):
                    violations.append({
                        "type":     "non_system_spacing",
                        "detail":   f"{css_prop}: {css_val} — not on spacing scale {scale}",
                        "line":     style_obj.get("line", 0),
                        "severity": "warning",
                    })


def _check_typography(
    comp: dict[str, Any],
    ds: dict,
    violations: list,
) -> None:
    """Flag inline font-size values outside the type scale."""
    font_sizes: dict[str, int] = ds.get("typography", {}).get("fontSizes", {})
    allowed_px = set(font_sizes.values())
    if not allowed_px:
        return

    px_re = re.compile(r"^(\d+(?:\.\d+)?)px$")

    for style_obj in comp.get("inline_styles", []):
        props = style_obj.get("properties", {})
        if "fontSize" in props:
            m = px_re.match(props["fontSize"].strip())
            if m and float(m.group(1)) not in allowed_px:
                violations.append({
                    "type":     "non_system_font_size",
                    "detail":   f"fontSize: {props['fontSize']} — not in type scale {sorted(allowed_px)}",
                    "line":     style_obj.get("line", 0),
                    "severity": "warning",
                })


def _check_colors(
    comp: dict[str, Any],
    ds: dict,
    violations: list,
) -> None:
    """Flag hardcoded hex / rgb colors not found in the design-system palette."""
    palette_colors: set[str] = set()
    for palette in ds.get("colors", {}).values():
        if isinstance(palette, dict):
            for v in palette.values():
                if isinstance(v, str):
                    palette_colors.add(v.lower())
        elif isinstance(palette, str):
            palette_colors.add(palette.lower())

    if not palette_colors:
        return

    color_props = {"color", "backgroundColor", "background", "borderColor", "outlineColor"}
    hex_re = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
    rgb_re = re.compile(r"^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+")

    for style_obj in comp.get("inline_styles", []):
        props = style_obj.get("properties", {})
        for css_prop, css_val in props.items():
            if css_prop not in color_props:
                continue
            val = css_val.strip().lower()
            if (hex_re.match(val) or rgb_re.match(val)) and val not in palette_colors:
                violations.append({
                    "type":     "hardcoded_color",
                    "detail":   f"{css_prop}: {css_val} — use a design-system color token",
                    "line":     style_obj.get("line", 0),
                    "severity": "warning",
                })


def _check_duplicates(
    comp: dict[str, Any],
    violations: list,
) -> None:
    """Flag duplicated className strings across the component."""
    seen: dict[str, int] = {}  # class_string → first line
    for cn in comp.get("class_names", []):
        if cn.get("type") != "static":
            continue
        key = " ".join(sorted(cn.get("classes", [])))
        if not key:
            continue
        if key in seen:
            violations.append({
                "type":     "duplicated_class_pattern",
                "detail":   f'Duplicate className "{cn["raw"]}" (first at line {seen[key]})',
                "line":     cn.get("line", 0),
                "severity": "info",
            })
        else:
            seen[key] = cn.get("line", 0)


def _check_inline_vs_class(
    comp: dict[str, Any],
    violations: list,
) -> None:
    """Flag excessive use of inline styles — prefer utility classes."""
    inline_count = len(comp.get("inline_styles", []))
    if inline_count >= 5:
        violations.append({
            "type":     "excessive_inline_styles",
            "detail":   f"{inline_count} inline style objects found — extract to utility classes or CSS modules",
            "line":     0,
            "severity": "warning",
        })
    elif inline_count >= 3:
        violations.append({
            "type":     "excessive_inline_styles",
            "detail":   f"{inline_count} inline style objects — consider extracting to classes",
            "line":     0,
            "severity": "info",
        })


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import importlib
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    cp = importlib.import_module("component_parser")

    if len(sys.argv) < 2:
        print("Usage: python3 style_analyzer.py <component_file>", file=sys.stderr)
        sys.exit(1)

    parsed = cp.parse_file(sys.argv[1])
    report = analyze(parsed)
    print(json.dumps(report, indent=2))
