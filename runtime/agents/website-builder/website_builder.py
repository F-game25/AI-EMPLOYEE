"""Website Builder Agent — landing page copy and structure generation.

Generates complete, conversion-optimized landing page copy and renders it
as a real HTML file saved to state/artifacts/. The chat output includes
a /api/preview/<filename> link that opens inline in the output panel.

Commands (via chat):
  site hero     <product>   — hero section: headline, subhead, CTA
  site features <product>   — 3-6 feature/benefit blocks
  site pricing  <tiers>     — pricing table copy
  site faq      <product>   — 8-10 FAQ questions and answers
  site full     <product>   — complete landing page (all sections)
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
ARTIFACTS_DIR = AI_HOME / "state" / "artifacts"

SYSTEM = """You are a world-class conversion copywriter and landing page specialist. Every word earns its place.

Output JSON with this structure:
{
  "page_title": "SEO-optimized page title (60 chars)",
  "meta_description": "Compelling meta description (155 chars)",
  "hero": {
    "headline": "Primary H1 (under 10 words, benefit-driven)",
    "subheadline": "Supporting H2 (one sentence clarifying the headline)",
    "body": "2-3 sentences expanding on the value proposition",
    "cta_primary": "Button text (action verb + benefit)",
    "cta_secondary": "Secondary option (e.g. 'Watch demo')"
  },
  "features": [{"title": "...", "description": "...", "icon_suggestion": "..."}],
  "social_proof": {"testimonial_prompts": ["Ideal testimonial themes"], "stats": ["stat 1", "stat 2"]},
  "pricing": [{"tier": "...", "price": "...", "description": "...", "features": ["..."], "cta": "..."}],
  "faq": [{"question": "...", "answer": "..."}],
  "final_cta": {"headline": "...", "body": "...", "button": "..."},
  "conversion_tips": ["Specific improvement to implement"]
}"""


def _e(text: str) -> str:
    return _html.escape(str(text or ""))


def _render_html(data: dict, product: str) -> str:
    hero = data.get("hero") or {}
    features = data.get("features") or []
    pricing = data.get("pricing") or []
    faq = data.get("faq") or []
    final_cta = data.get("final_cta") or {}
    stats = (data.get("social_proof") or {}).get("stats") or []

    feature_html = "".join(
        f'<div class="feature"><div class="feat-icon">{_e(f.get("icon_suggestion","★"))}</div>'
        f'<h3>{_e(f.get("title",""))}</h3><p>{_e(f.get("description",""))}</p></div>'
        for f in features[:6]
    )

    pricing_html = "".join(
        f'<div class="pricing-card {"pricing-card--featured" if i == 1 else ""}">'
        f'<div class="tier">{_e(p.get("tier",""))}</div>'
        f'<div class="price">{_e(p.get("price",""))}</div>'
        f'<p>{_e(p.get("description",""))}</p>'
        f'<ul>{"".join(f"<li>{_e(feat)}</li>" for feat in (p.get("features") or []))}</ul>'
        f'<button class="cta-btn">{_e(p.get("cta","Get started"))}</button></div>'
        for i, p in enumerate(pricing[:3])
    )

    faq_html = "".join(
        f'<details class="faq-item"><summary>{_e(q.get("question",""))}</summary>'
        f'<p>{_e(q.get("answer",""))}</p></details>'
        for q in faq[:10]
    )

    stats_html = "".join(
        f'<div class="stat">{_e(s)}</div>' for s in stats[:4]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(data.get("page_title", product))}</title>
<meta name="description" content="{_e(data.get("meta_description", ""))}">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a0a0f; --surface: #13131a; --border: rgba(255,255,255,.08);
    --accent: #20d6c7; --gold: #e5c76b; --text: #e8e8f0; --muted: #888;
    --radius: 12px; --font: 'Segoe UI', system-ui, sans-serif;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); line-height: 1.6; }}
  a {{ color: var(--accent); text-decoration: none; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 0 24px; }}
  /* NAV */
  nav {{ padding: 20px 0; border-bottom: 1px solid var(--border); }}
  nav .container {{ display: flex; align-items: center; justify-content: space-between; }}
  .nav-brand {{ font-size: 1.2rem; font-weight: 700; color: var(--accent); }}
  /* HERO */
  .hero {{ padding: 96px 0 80px; text-align: center; background:
    radial-gradient(ellipse 70% 50% at 50% 0%, rgba(32,214,199,.12), transparent); }}
  .hero h1 {{ font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 800; line-height: 1.15;
    background: linear-gradient(135deg, #fff 40%, var(--accent));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 20px; }}
  .hero h2 {{ font-size: 1.25rem; color: var(--muted); font-weight: 400; margin-bottom: 16px; }}
  .hero-body {{ max-width: 620px; margin: 0 auto 40px; color: #b0b0c0; }}
  .cta-group {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }}
  .cta-btn {{ background: var(--accent); color: #000; font-weight: 700;
    padding: 14px 32px; border-radius: 8px; border: none; cursor: pointer;
    font-size: 1rem; transition: opacity .15s; }}
  .cta-btn:hover {{ opacity: .85; }}
  .cta-btn-ghost {{ background: transparent; color: var(--text); border: 1px solid var(--border);
    padding: 14px 32px; border-radius: 8px; cursor: pointer; font-size: 1rem; }}
  /* STATS */
  .stats {{ display: flex; gap: 32px; justify-content: center; flex-wrap: wrap;
    padding: 48px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
  .stat {{ text-align: center; font-size: .95rem; color: var(--muted); }}
  /* FEATURES */
  .section {{ padding: 80px 0; }}
  .section-title {{ text-align: center; font-size: 2rem; font-weight: 700; margin-bottom: 48px; }}
  .features-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; }}
  .feature {{ background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 28px; }}
  .feat-icon {{ font-size: 2rem; margin-bottom: 12px; }}
  .feature h3 {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }}
  .feature p {{ color: var(--muted); font-size: .95rem; }}
  /* PRICING */
  .pricing-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 24px; }}
  .pricing-card {{ background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 32px; display: flex; flex-direction: column; gap: 16px; }}
  .pricing-card--featured {{ border-color: var(--accent); box-shadow: 0 0 32px rgba(32,214,199,.15); }}
  .tier {{ font-size: .8rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .1em; color: var(--accent); }}
  .price {{ font-size: 2rem; font-weight: 800; }}
  .pricing-card p {{ color: var(--muted); font-size: .9rem; }}
  .pricing-card ul {{ list-style: none; display: flex; flex-direction: column; gap: 8px; flex: 1; }}
  .pricing-card li::before {{ content: "✓ "; color: var(--accent); }}
  .pricing-card li {{ font-size: .9rem; color: #c0c0d0; }}
  /* FAQ */
  .faq-list {{ max-width: 720px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }}
  .faq-item {{ background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden; }}
  .faq-item summary {{ padding: 18px 24px; cursor: pointer; font-weight: 600;
    list-style: none; display: flex; justify-content: space-between; align-items: center; }}
  .faq-item summary::after {{ content: "+"; color: var(--accent); font-size: 1.4rem; }}
  .faq-item[open] summary::after {{ content: "−"; }}
  .faq-item p {{ padding: 0 24px 18px; color: var(--muted); }}
  /* FINAL CTA */
  .final-cta {{ background: var(--surface); border: 1px solid var(--border);
    border-radius: 20px; padding: 80px 40px; text-align: center; margin: 0 0 80px; }}
  .final-cta h2 {{ font-size: 2rem; font-weight: 700; margin-bottom: 16px; }}
  .final-cta p {{ color: var(--muted); max-width: 520px; margin: 0 auto 32px; }}
  /* FOOTER */
  footer {{ border-top: 1px solid var(--border); padding: 32px 0; text-align: center;
    color: var(--muted); font-size: .85rem; }}
</style>
</head>
<body>
<nav><div class="container">
  <span class="nav-brand">{_e(product)}</span>
  <button class="cta-btn" style="padding:10px 20px;font-size:.9rem">{_e(hero.get("cta_primary","Get Started"))}</button>
</div></nav>

<section class="hero"><div class="container">
  <h1>{_e(hero.get("headline",""))}</h1>
  <h2>{_e(hero.get("subheadline",""))}</h2>
  <p class="hero-body">{_e(hero.get("body",""))}</p>
  <div class="cta-group">
    <button class="cta-btn">{_e(hero.get("cta_primary","Get Started"))}</button>
    {"" if not hero.get("cta_secondary") else f'<button class="cta-btn-ghost">{_e(hero.get("cta_secondary",""))}</button>'}
  </div>
</div></section>

{"" if not stats_html else f'<div class="container"><div class="stats">{stats_html}</div></div>'}

{"" if not feature_html else f'<section class="section"><div class="container"><h2 class="section-title">Everything you need</h2><div class="features-grid">{feature_html}</div></div></section>'}

{"" if not pricing_html else f'<section class="section" style="background:var(--surface)"><div class="container"><h2 class="section-title">Simple, transparent pricing</h2><div class="pricing-grid">{pricing_html}</div></div></section>'}

{"" if not faq_html else f'<section class="section"><div class="container"><h2 class="section-title">Frequently asked questions</h2><div class="faq-list">{faq_html}</div></div></section>'}

<section class="section"><div class="container">
  <div class="final-cta">
    <h2>{_e(final_cta.get("headline","Ready to get started?"))}</h2>
    <p>{_e(final_cta.get("body",""))}</p>
    <button class="cta-btn">{_e(final_cta.get("button","Get Started"))}</button>
  </div>
</div></section>

<footer><div class="container">© {datetime.now(timezone.utc).year} {_e(product)}. Built with AI Employee.</div></footer>
</body></html>"""


class WebsiteBuilderAgent(BaseAgent):
    agent_id = "website-builder"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        product = payload.get("product") or payload.get("task", "")
        audience = payload.get("audience", "")
        pain_point = payload.get("pain_point", "")
        section = payload.get("section", "full")
        tone = payload.get("tone", "professional and approachable")

        prompt = (
            f"Build landing page copy for:\n"
            f"Product/Service: {product}\n"
            f"Target Audience: {audience}\n"
            f"Main Pain Point Solved: {pain_point}\n"
            f"Tone: {tone}\n"
            f"Section requested: {section}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens

        # Render and save HTML artifact
        try:
            html_content = _render_html(data, product)
            slug = re.sub(r"[^a-z0-9]+", "-", product.lower())[:40].strip("-")
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"site_{slug}_{ts}.html"
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            (ARTIFACTS_DIR / filename).write_text(html_content, encoding="utf-8")
            preview_url = f"/api/preview/{filename}"
            data["preview_url"] = preview_url
            data["artifact_file"] = filename
            data["artifacts"] = [{
                "name": f"Website: {product}",
                "label": f"Preview — {product}",
                "type": "html_preview",
                "path": str(ARTIFACTS_DIR / filename),
                "url": preview_url,
                "preview_url": preview_url,
            }]
        except Exception as exc:
            data["preview_error"] = str(exc)

        return data
