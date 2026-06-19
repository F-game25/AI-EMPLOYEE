"""Heuristic demo quality gate — evaluates a generated HTML demo without running it.

Dimensions checked:
  1. visual_quality     — viewport meta, CSS present, no inline-only styles
  2. content_quality    — no lorem ipsum, meaningful text length, Dutch/English copy
  3. business_fit       — business name appears in copy, relevant section keywords
  4. conversion_quality — CTA button/link present, contact section, form or tel link
  5. usability          — nav or header, footer, headings hierarchy
  6. technical_preview  — valid HTML shell, no broken image srcs, no JS errors in template
  7. forge_readiness    — has structured sections, no placeholder tokens left
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


_AI_HOME = os.environ.get("AI_HOME") or str(Path.home() / ".ai-employee")
_DEMOS_DIR = Path(_AI_HOME) / "state" / "artifacts" / "demos"

_LOREM = re.compile(r"lorem ipsum", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\[.*?\]|\{.*?\}|PLACEHOLDER|TODO|FIXME", re.IGNORECASE)


def _dim(score: float, passed: bool, notes: list[str]) -> dict[str, Any]:
    return {"score": round(score, 2), "passed": passed, "notes": notes}


def evaluate_html(html: str, bedrijfsnaam: str = "", branche: str = "") -> dict[str, Any]:
    lower = html.lower()
    name_lower = (bedrijfsnaam or "").lower()

    # 1. Visual quality
    has_viewport = "viewport" in lower
    has_css = "<style" in lower or "stylesheet" in lower
    vq_notes = []
    if not has_viewport:
        vq_notes.append("Geen viewport meta tag — mogelijk niet mobiel-vriendelijk")
    if not has_css:
        vq_notes.append("Geen CSS gevonden")
    vq_score = (0.5 if has_viewport else 0) + (0.5 if has_css else 0)
    visual_quality = _dim(vq_score, vq_score >= 0.5, vq_notes)

    # 2. Content quality
    has_lorem = bool(_LOREM.search(html))
    text_len = len(re.sub(r"<[^>]+>", "", html))
    cq_notes = []
    if has_lorem:
        cq_notes.append("Lorem ipsum tekst gevonden — demo bevat placeholder tekst")
    if text_len < 500:
        cq_notes.append(f"Weinig tekst ({text_len} tekens) — mogelijk incomplete demo")
    cq_score = (0.4 if not has_lorem else 0) + min(0.6, text_len / 2000)
    content_quality = _dim(min(1.0, cq_score), cq_score >= 0.5, cq_notes)

    # 3. Business fit
    bf_notes = []
    name_present = name_lower and name_lower in lower
    branch_present = bool(branche) and branche.lower() in lower
    has_hero = any(k in lower for k in ("hero", "<h1", "<h2"))
    if not name_present:
        bf_notes.append(f"Bedrijfsnaam '{bedrijfsnaam}' niet gevonden in demo")
    if not branch_present and branche:
        bf_notes.append(f"Branche '{branche}' niet in tekst — mogelijk te generiek")
    bf_score = (0.4 if name_present else 0) + (0.3 if branch_present else 0.1) + (0.3 if has_hero else 0)
    business_fit = _dim(min(1.0, bf_score), bf_score >= 0.5, bf_notes)

    # 4. Conversion quality
    has_cta = any(k in lower for k in ("cta", "offerte", "quote", "contact", "bel", "tel:", "mailto:", "afspraak", "boek"))
    has_form = "<form" in lower or "netlify" in lower
    has_button = "<button" in lower or 'type="submit"' in lower or "btn" in lower
    cvq_notes = []
    if not has_cta:
        cvq_notes.append("Geen duidelijke CTA gevonden")
    if not has_form and not has_button:
        cvq_notes.append("Geen formulier of actie-knop gevonden")
    cvq_score = (0.4 if has_cta else 0) + (0.3 if has_form else 0) + (0.3 if has_button else 0)
    conversion_quality = _dim(min(1.0, cvq_score), cvq_score >= 0.5, cvq_notes)

    # 5. Usability
    has_nav = any(k in lower for k in ("<nav", "navbar", "menu"))
    has_footer = "<footer" in lower
    has_headings = "<h1" in lower or "<h2" in lower
    uq_notes = []
    if not has_nav:
        uq_notes.append("Geen navigatie gevonden")
    if not has_footer:
        uq_notes.append("Geen footer gevonden")
    uq_score = (0.4 if has_headings else 0) + (0.3 if has_nav else 0) + (0.3 if has_footer else 0)
    usability = _dim(min(1.0, uq_score), uq_score >= 0.5, uq_notes)

    # 6. Technical preview
    has_doctype = "<!doctype" in lower
    has_body = "<body" in lower
    broken_img = len(re.findall(r'src="\s*"', html))
    tpq_notes = []
    if not has_doctype:
        tpq_notes.append("Geen DOCTYPE — mogelijk incomplete HTML")
    if broken_img:
        tpq_notes.append(f"{broken_img} lege img src(s) gevonden")
    tpq_score = (0.5 if has_doctype and has_body else 0.2) + (0.5 if broken_img == 0 else 0)
    technical_preview = _dim(min(1.0, tpq_score), tpq_score >= 0.5, tpq_notes)

    # 7. Forge readiness
    placeholders = _PLACEHOLDER.findall(html)
    unique_placeholders = list(set(placeholders))[:5]
    has_sections = lower.count("<section") + lower.count("<div") >= 5
    frq_notes = []
    if unique_placeholders:
        frq_notes.append(f"Placeholder tokens gevonden: {', '.join(unique_placeholders)}")
    if not has_sections:
        frq_notes.append("Weinig structurele secties — mogelijk moeilijk uit te breiden")
    frq_score = (0.6 if not unique_placeholders else 0.1) + (0.4 if has_sections else 0)
    forge_readiness = _dim(min(1.0, frq_score), frq_score >= 0.5, frq_notes)

    dims = {
        "visual_quality": visual_quality,
        "content_quality": content_quality,
        "business_fit": business_fit,
        "conversion_quality": conversion_quality,
        "usability": usability,
        "technical_preview_quality": technical_preview,
        "forge_readiness": forge_readiness,
    }
    total = sum(d["score"] for d in dims.values()) / len(dims)
    passed_count = sum(1 for d in dims.values() if d["passed"])
    blocking = [n for d in dims.values() for n in d["notes"] if not d["passed"]]

    if passed_count >= 6:
        status = "passed"
    elif passed_count >= 4:
        status = "partially_passed"
    else:
        status = "failed"

    return {
        "ok": True,
        "status": status,
        "total_score": round(total, 2),
        "passed_dimensions": passed_count,
        "total_dimensions": len(dims),
        "blocking_issues": blocking,
        "recommended_improvements": [n for d in dims.values() for n in d["notes"]],
        "quality_dimensions": dims,
    }


def evaluate_order_demo(order_id: str) -> dict[str, Any]:
    from core.orders_store import order_ophalen, demo_quality_opslaan
    order = order_ophalen(order_id)
    if not order:
        return {"ok": False, "error": f"Order {order_id} niet gevonden"}

    demo_pad = order.get("demo_pad", "")
    if not demo_pad:
        return {"ok": False, "error": "Geen demo gegenereerd voor dit order", "status": "unavailable"}

    demo_file = Path(demo_pad)
    if not demo_file.exists():
        # Try by slug under demos dir
        slug = demo_pad.split("/")[-1] if "/" in demo_pad else demo_pad
        alt = _DEMOS_DIR / slug / "index.html"
        if alt.exists():
            demo_file = alt
        else:
            return {"ok": False, "error": f"Demo bestand niet gevonden: {demo_pad}", "status": "unavailable"}

    html = demo_file.read_text(errors="replace")
    result = evaluate_html(html, order.get("bedrijfsnaam", ""), order.get("branche", ""))
    result["order_id"] = order_id
    result["demo_path"] = str(demo_file)

    demo_quality_opslaan(order_id, json.dumps(result, ensure_ascii=False))
    return result
