"""Composer — turns an escaped context into a coherent, unique multi-page site.

A per-job seed deterministically selects a palette (biased to the branche mood),
a font pair, a style theme and a variant for each section. The same job always
renders the same look; different jobs look clearly different. All four pages of
one site share the theme so they feel like one website.
"""
from __future__ import annotations

import hashlib
import json

from . import blocks
from .css import base_css, font_import_link
from .tokens import PALETTES, FONT_PAIRS, STYLE_THEMES, branche_mood

PAGES = [
    ("index.html", "Home"),
    ("diensten.html", "Diensten"),
    ("over.html", "Over ons"),
    ("contact.html", "Contact"),
]


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.md5(f"{salt}:{seed}".encode("utf-8")).hexdigest(), 16)  # nosec B324


def build_theme(seed: str, branche: str) -> dict:
    mood = branche_mood(branche)
    pool = [p for p in PALETTES if p["mood"] == mood] or PALETTES
    palette = pool[_seed_int(seed, "pal") % len(pool)]
    fonts = FONT_PAIRS[_seed_int(seed, "font") % len(FONT_PAIRS)]
    style = STYLE_THEMES[_seed_int(seed, "style") % len(STYLE_THEMES)]
    variants = {name: _seed_int(seed, f"v_{name}") % n for name, n in blocks.VARIANTS.items()}
    return {"palette": palette, "fonts": fonts, "style": style, "variants": variants,
            "key": f'{palette["name"]}/{fonts["name"]}/{style["name"]}'}


def _schema_jsonld(ctx) -> str:
    schema = {"@context": "https://schema.org", "@type": "LocalBusiness",
              "name": ctx["naam_raw"], "description": ctx["branche_raw"],
              "address": {"@type": "PostalAddress", "addressLocality": ctx["plaats_raw"], "addressCountry": "NL"}}
    if ctx.get("telefoon_raw"):
        schema["telephone"] = ctx["telefoon_raw"]
    if ctx.get("website_raw"):
        schema["url"] = ctx["website_raw"]
    return json.dumps(schema, ensure_ascii=False)


def _doc(title: str, meta: str, theme: dict, body: str, ctx: dict) -> str:
    return f"""<!DOCTYPE html>
<html lang="nl"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{meta}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{meta}"><meta property="og:type" content="website">
{font_import_link(theme)}
<script type="application/ld+json">{_schema_jsonld(ctx)}</script>
<style>{base_css(theme)}</style>
</head><body>
{body}
</body></html>"""


def _pagehead(ctx, label: str, sub: str) -> str:
    return f"""<header class="pagehead"><div class="container">
  <div class="crumbs"><a href="index.html">Home</a> · {label}</div>
  <h1>{label}</h1><p>{sub}</p></div></header>"""


def render_site(ctx: dict, theme: dict) -> dict[str, str]:
    """Return {filename: html} for the full multi-page site."""
    vv = theme["variants"]
    naam, plaats = ctx["naam"], ctx["plaats"]
    title_base = f'{naam} — {ctx["branche"]} in {plaats}'
    meta = ctx["meta"]
    out: dict[str, str] = {}

    # Sections render lazily: a block is only built when its data exists. Empty
    # blocks (reviews/gallery/stat_strip) also self-guard. diensten is always
    # present (real or branche-typical fallback).
    has_reviews  = bool(ctx.get("reviews"))
    has_gallery  = bool(ctx.get("gallery"))
    has_stats    = bool(ctx.get("stats"))
    # Stats show via a dedicated strip → avoid the 'over' statband variant.
    ov_variant = 1 if vv["over"] == 2 else vv["over"]

    def nav_footer(active):
        ctx["active"] = active
        return blocks.nav(ctx, vv["nav"]), blocks.footer(ctx, vv["footer"])

    # Home — full, professional even with little data.
    n, f = nav_footer("index.html")
    home = (n + blocks.hero(ctx, vv["hero"])
            + (blocks.stat_strip(ctx) if has_stats else "")
            + blocks.diensten(ctx, vv["diensten"])
            + blocks.werkwijze(ctx)
            + blocks.over(ctx, ov_variant)
            + (blocks.gallery(ctx) if has_gallery else "")
            + (blocks.reviews(ctx, vv["reviews"]) if has_reviews else "")
            + blocks.waarom(ctx)
            + blocks.cta(ctx, vv["cta"]) + f)
    out["index.html"] = _doc(title_base, meta, theme, home, ctx)

    # Diensten
    n, f = nav_footer("diensten.html")
    dn = (n + _pagehead(ctx, "Diensten", f"Wat {naam} voor u kan betekenen in {plaats} en omgeving.")
          + blocks.diensten(ctx, vv["diensten"], head=False)
          + blocks.werkwijze(ctx)
          + (blocks.gallery(ctx) if has_gallery else "")
          + blocks.cta(ctx, vv["cta"]) + f)
    out["diensten.html"] = _doc(f"Diensten — {naam}", meta, theme, dn, ctx)

    # Over ons
    n, f = nav_footer("over.html")
    ov = (n + _pagehead(ctx, "Over ons", f"Het verhaal achter {naam}.")
          + blocks.over(ctx, ov_variant, full=True)
          + (blocks.stat_strip(ctx) if has_stats else "")
          + blocks.waarom(ctx)
          + (blocks.gallery(ctx) if has_gallery else "")
          + (blocks.reviews(ctx, vv["reviews"]) if has_reviews else "")
          + blocks.cta(ctx, vv["cta"]) + f)
    out["over.html"] = _doc(f"Over ons — {naam}", meta, theme, ov, ctx)

    # Contact
    n, f = nav_footer("contact.html")
    cn = (n + _pagehead(ctx, "Contact", f"Vraag vrijblijvend een offerte aan bij {naam}.")
          + blocks.contact(ctx, vv["contact"], head=False) + f)
    out["contact.html"] = _doc(f"Contact — {naam}", meta, theme, cn, ctx)

    return out
