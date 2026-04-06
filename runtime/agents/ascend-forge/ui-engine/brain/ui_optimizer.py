"""brain/ui_optimizer.py — Synthesizes code analysis + vision feedback.

Produces:
  - improved component code (string)
  - explanation (concise, technical)
  - predicted improvement score (float 0–100)

All outputs MUST conform to design_system.json constraints.

Optimisation modes (from modes.json):
  money_mode    — conversion & CTA focus
  general_mode  — consistency & maintainability
  blacklight_mode — maximum intensity + variant generation
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE       = Path(__file__).parent
_ENGINE_DIR = _HERE.parent
_CONFIG_DIR = _ENGINE_DIR / "config"
_ROUTER_DIR = _ENGINE_DIR.parent.parent / "ai-router"

_DS_PATH    = _CONFIG_DIR / "design_system.json"
_MODES_PATH = _CONFIG_DIR / "modes.json"


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Scoring ───────────────────────────────────────────────────────────────────

def compute_score(
    vision_score: float,
    debt_score: float,
    hierarchy_quality: float,
    conversion_heuristics: float,
    mode: str = "general_mode",
) -> float:
    """Compute weighted optimisation score (0–100).

    *debt_score* is inverted (higher debt → lower structural score).
    """
    modes = _load_json(_MODES_PATH)
    weights = modes.get(mode, modes.get("general_mode", {})).get(
        "scoring_weights",
        {
            "vision_score":          0.30,
            "structural_consistency": 0.35,
            "hierarchy_quality":     0.25,
            "conversion_heuristics": 0.10,
        },
    )

    structural_score = max(0.0, 100.0 - debt_score)

    score = (
        vision_score           * weights.get("vision_score",          0.30)
        + structural_score     * weights.get("structural_consistency", 0.35)
        + hierarchy_quality    * weights.get("hierarchy_quality",      0.25)
        + conversion_heuristics * weights.get("conversion_heuristics", 0.10)
    )
    return round(min(100.0, max(0.0, score)), 2)


# ── Public API ────────────────────────────────────────────────────────────────

def optimize(
    parsed_component: dict[str, Any],
    style_report: dict[str, Any],
    vision_report: dict[str, Any],
    mode: str = "general_mode",
) -> dict[str, Any]:
    """Synthesize all analysis layers and produce an optimised component.

    Returns a dict with keys:
        improved_code        — patched source string (or original if no changes)
        explanation          — concise technical description of changes
        predicted_score      — estimated score after applying improvements
        current_score        — score of the original component
        mode                 — active mode
        design_system_checks — list of compliance checks run
    """
    ds    = _load_json(_DS_PATH)
    modes = _load_json(_MODES_PATH)

    vision_score           = float(vision_report.get("ux_score", 50))
    debt_score             = float(style_report.get("debt_score", 0))
    hierarchy_quality      = _estimate_hierarchy_quality(parsed_component)
    conversion_heuristics  = _estimate_conversion_score(parsed_component, modes.get(mode, {}))

    current_score = compute_score(
        vision_score, debt_score, hierarchy_quality, conversion_heuristics, mode
    )

    # Build optimisation context for the LLM
    context = _build_context(parsed_component, style_report, vision_report, ds, modes.get(mode, {}))

    improved_code, explanation = _run_llm_optimization(
        parsed_component.get("raw_source", ""), context
    )

    # If LLM unavailable, apply rule-based fixes
    if improved_code is None:
        improved_code, explanation = _rule_based_fix(
            parsed_component.get("raw_source", ""), style_report, ds
        )

    # Optimistically predict a +10 improvement (bounded at 100)
    predicted_score = min(100.0, current_score + 10.0)

    return {
        "improved_code":        improved_code,
        "explanation":          explanation,
        "predicted_score":      predicted_score,
        "current_score":        current_score,
        "mode":                 mode,
        "design_system_checks": _compliance_checks(parsed_component, ds),
    }


def generate_variants(
    parsed_component: dict[str, Any],
    style_report: dict[str, Any],
    vision_report: dict[str, Any],
    count: int = 3,
) -> list[dict[str, Any]]:
    """Generate multiple alternative optimisations (blacklight_mode).

    Returns a list of dicts (each has the same shape as :func:`optimize` output),
    sorted descending by predicted_score.
    """
    variants = []
    for i in range(count):
        variant = optimize(
            parsed_component, style_report, vision_report, mode="blacklight_mode"
        )
        variant["variant_index"] = i
        variants.append(variant)

    variants.sort(key=lambda v: v["predicted_score"], reverse=True)
    return variants


# ── Helpers ───────────────────────────────────────────────────────────────────

def _estimate_hierarchy_quality(comp: dict[str, Any]) -> float:
    """Rough hierarchy quality score based on element count and nesting."""
    hierarchy = comp.get("hierarchy", [])
    if not hierarchy:
        return 50.0
    # Penalise extremely flat or extremely deep structures
    tag_set = {el["tag"] for el in hierarchy}
    semantic_tags = {"header", "main", "footer", "nav", "section", "article", "aside"}
    semantic_ratio = len(semantic_tags & tag_set) / max(len(tag_set), 1)
    return round(50.0 + semantic_ratio * 50.0, 2)


def _estimate_conversion_score(comp: dict[str, Any], mode_cfg: dict) -> float:
    """Estimate conversion potential based on CTA presence and checks."""
    score = 50.0
    hierarchy = comp.get("hierarchy", [])
    tags = {el["tag"].lower() for el in hierarchy}

    # Button / anchor presence
    if "button" in tags or "a" in tags:
        score += 20.0

    # Form presence
    if "form" in tags:
        score += 10.0

    checks = mode_cfg.get("checks", {})
    if checks.get("single_primary_cta"):
        btn_count = sum(1 for el in hierarchy if el["tag"].lower() in ("button", "a"))
        if btn_count == 1:
            score += 10.0
        elif btn_count > 3:
            score -= 10.0

    return round(min(100.0, max(0.0, score)), 2)


def _build_context(
    comp: dict,
    style_report: dict,
    vision_report: dict,
    ds: dict,
    mode_cfg: dict,
) -> str:
    violations = style_report.get("violations", [])
    issues     = vision_report.get("issues", [])
    priorities = mode_cfg.get("priorities", [])

    lines = [
        f"Component: {comp.get('filename', '<unknown>')}",
        f"Type: {comp.get('type', 'unknown')}",
        f"Priorities: {', '.join(priorities)}",
        "",
        "Design-debt violations:",
    ]
    for v in violations[:5]:
        lines.append(f"  [{v['severity']}] {v['detail']} (line {v.get('line', '?')})")
    lines.append("")
    lines.append("UX issues:")
    for iss in issues[:5]:
        lines.append(f"  [{iss['severity']}] {iss['element']}: {iss['description']}")
    return "\n".join(lines)


def _run_llm_optimization(
    source: str,
    context: str,
) -> tuple[str | None, str]:
    """Ask the AI router to produce improved component code."""
    if str(_ROUTER_DIR) not in sys.path:
        sys.path.insert(0, str(_ROUTER_DIR))

    try:
        ai_router = importlib.import_module("ai_router")
    except ImportError:
        return None, "LLM unavailable — rule-based fixes applied."

    query_fn = getattr(ai_router, "query_ai_for_agent", None)
    if not callable(query_fn):
        return None, "LLM unavailable — rule-based fixes applied."

    prompt = (
        "You are a UI engineer. Improve the following component to fix the issues below.\n"
        "Return ONLY the improved code, no explanation.\n\n"
        f"Context:\n{context}\n\n"
        f"Source:\n```\n{source}\n```"
    )

    try:
        result = query_fn("ui-optimizer", prompt, timeout=45)
        if result:
            # Strip markdown code fences if present
            lines  = result.strip().splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines), "LLM-generated improvements applied."
    except Exception:
        pass

    return None, "LLM unavailable — rule-based fixes applied."


def _rule_based_fix(
    source: str,
    style_report: dict,
    ds: dict,
) -> tuple[str, str]:
    """Minimal rule-based improvements when LLM is unavailable."""
    changes: list[str] = []
    result = source

    # Replace obvious non-system spacing (px values not on scale)
    import re
    scale = ds.get("spacing", {}).get("scale", [])
    if scale:
        def _snap(m: re.Match) -> str:
            val = float(m.group(1))
            closest = min(scale, key=lambda s: abs(s - val))
            if closest != val:
                changes.append(f"Snapped {val}px → {closest}px")
                return f"{closest}px"
            return m.group(0)

        result = re.sub(r"\b(\d+(?:\.\d+)?)px\b", _snap, result)

    explanation = (
        "Rule-based fixes: " + "; ".join(changes)
        if changes
        else "No automatic rule-based fixes applied."
    )
    return result, explanation


def _compliance_checks(comp: dict, ds: dict) -> list[dict[str, Any]]:
    """Run a quick compliance check against the design system."""
    checks: list[dict[str, Any]] = []
    inline_styles = comp.get("inline_styles", [])

    checks.append({
        "check":  "inline_styles_count",
        "value":  len(inline_styles),
        "pass":   len(inline_styles) < 5,
        "note":   "Keep inline styles below 5 per component.",
    })
    checks.append({
        "check":  "hierarchy_present",
        "value":  len(comp.get("hierarchy", [])),
        "pass":   len(comp.get("hierarchy", [])) > 0,
        "note":   "Component must have at least one JSX/template element.",
    })
    return checks


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import importlib, sys

    _scanner_dir = _ENGINE_DIR / "scanner"
    _vision_dir  = _ENGINE_DIR / "vision"
    sys.path.insert(0, str(_scanner_dir))
    sys.path.insert(0, str(_vision_dir))

    if len(sys.argv) < 2:
        print("Usage: python3 ui_optimizer.py <component_file> [mode]", file=sys.stderr)
        sys.exit(1)

    cp = importlib.import_module("component_parser")
    sa = importlib.import_module("style_analyzer")

    component_file = Path(sys.argv[1])
    active_mode    = sys.argv[2] if len(sys.argv) > 2 else "general_mode"

    parsed_comp  = cp.parse_file(component_file)
    style_rpt    = sa.analyze(parsed_comp)
    vision_rpt   = {"ux_score": 60, "issues": [], "directives": []}  # placeholder

    result = optimize(parsed_comp, style_rpt, vision_rpt, mode=active_mode)
    print(json.dumps({k: v for k, v in result.items() if k != "improved_code"}, indent=2))
    print("\n--- Improved Code ---")
    print(result["improved_code"])
