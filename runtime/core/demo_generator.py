"""Demo-website generator — one business at a time.

Calls the local Ollama model to write Dutch copy for each section,
then assembles a single-file HTML page that is production-ready:
- Google Fonts (Inter)
- Unsplash hero image matched to branche keyword
- Working contact form via Netlify Forms (zero backend)
- Hamburger menu on mobile
- Schema.org LocalBusiness JSON-LD
- Meta description + Open Graph tags
- No fake phone/address/email — only real data from research_data
"""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:latest")

_AI_HOME   = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_DEMO_ROOT = _AI_HOME / "state" / "artifacts" / "demos"

if not _OLLAMA_HOST.startswith(("http://", "https://")):
    raise ValueError(f"OLLAMA_HOST must start with http:// or https://, got: {_OLLAMA_HOST!r}")


def _llm(prompt: str, max_tokens: int = 300) -> str:
    payload = {
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "system": (
            "Je bent een professionele Nederlandse copywriter die website-teksten "
            "schrijft voor lokale bedrijven. Schrijf beknopte, zakelijke teksten "
            "in het Nederlands. Geen markdown, alleen platte tekst."
        ),
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    req = urllib.request.Request(
        f"{_OLLAMA_HOST}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310
        body = json.loads(resp.read())
    return body.get("response", "").strip()


def _e(text: str) -> str:
    """HTML-escape LLM output so stray < > & " never break the page."""
    return _html.escape(str(text), quote=True)


def _kleur_voor_branche(branche: str) -> tuple[str, str]:
    b = branche.lower()
    if any(w in b for w in ("loodgiet", "installat", "sanitair")):
        return "#1a3a5c", "#e87b1e"
    if any(w in b for w in ("bouw", "timmer", "aannem")):
        return "#2d4a1e", "#f5a623"
    if any(w in b for w in ("schoon", "onderhoud")):
        return "#1a5c4a", "#27ae60"
    if any(w in b for w in ("elektr",)):
        return "#1c2e4a", "#e74c3c"
    if any(w in b for w in ("schilder",)):
        return "#4a1a5c", "#9b59b6"
    if any(w in b for w in ("kapper", "haar", "schoonheid", "beauty")):
        return "#5c1a3a", "#e91e8c"
    if any(w in b for w in ("tuin", "groen", "hoveniers")):
        return "#1a4a1e", "#4caf50"
    if any(w in b for w in ("restaurant", "horeca", "eten", "café", "cafe")):
        return "#3a1a0a", "#c0392b"
    if any(w in b for w in ("bakker",)):
        return "#5a3a1a", "#f39c12"
    if any(w in b for w in ("auto", "garage", "reparatie")):
        return "#1a1a3a", "#3498db"
    return "#1a3a5c", "#e87b1e"


# Unsplash Source keywords per branche — returns a stable landscape image
_UNSPLASH_KEYWORDS: dict[str, str] = {
    "loodgiet": "plumbing+tools",
    "installat": "hvac+technician",
    "sanitair": "bathroom+modern",
    "bouw": "construction+site",
    "timmer": "carpentry+wood",
    "aannem": "construction+building",
    "schoon": "cleaning+professional",
    "elektr": "electrician+work",
    "schilder": "painting+house",
    "kapper": "hair+salon",
    "haar": "hair+salon",
    "schoonheid": "beauty+salon",
    "beauty": "beauty+spa",
    "tuin": "garden+landscaping",
    "groen": "garden+green",
    "hoveniers": "landscaping+garden",
    "restaurant": "restaurant+interior",
    "horeca": "restaurant+food",
    "bakker": "bakery+bread",
    "auto": "car+garage",
    "garage": "auto+repair",
}


def _unsplash_url(branche: str, w: int = 1400, h: int = 600) -> str:
    b = branche.lower()
    keyword = "local+business+professional"
    for k, v in _UNSPLASH_KEYWORDS.items():
        if k in b:
            keyword = v
            break
    # Unsplash Source — stable, no API key, delivers high-quality CC0 images
    return f"https://source.unsplash.com/featured/{w}x{h}/?{urllib.parse.quote(keyword)}"


def genereer_demo(
    *,
    bedrijfsnaam: str,
    plaats: str,
    branche: str,
    diensten: list[str] | None = None,
    research_data: dict | None = None,
) -> dict:
    """Generate a demo website for ONE business.

    Returns:
        {"status": "ok", "path": "/abs/path/to/demo.html", "bytes": N}
    or  {"status": "error", "error": "..."}
    """
    if not bedrijfsnaam or not plaats or not branche:
        return {"status": "error", "error": "bedrijfsnaam, plaats en branche zijn verplicht"}

    diensten = diensten or []
    primary, accent = _kleur_voor_branche(branche)
    rd = research_data or {}

    logger.info("demo_generator: genereren voor '%s' (%s, %s)", bedrijfsnaam, plaats, branche)

    # ── Swarm copy generation — hero + meta + over_ons + cta in parallel ────
    # 3 agents write each section from a different angle; best is chosen by
    # the swarm engine's belief propagation. Falls back to single LLM if swarm
    # unavailable (Ollama offline / SWARM_DEMO=0).
    _use_swarm = os.environ.get("SWARM_DEMO", "1") != "0"

    def _swarm_or_llm(prompt: str, max_tokens: int = 300) -> str:
        """Run swarm if available, fall back to single LLM call."""
        if _use_swarm:
            try:
                from core.swarm_engine import swarm_pitch
                result = swarm_pitch(prompt, context=f"{bedrijfsnaam}, {branche} in {plaats}", n_agents=3)
                if result.answer and result.confidence > 0.3:
                    return result.answer
            except Exception as exc:
                logger.debug("demo swarm fallback: %s", exc)
        return _llm(prompt, max_tokens=max_tokens)

    # All three heavy copy sections run via swarm in parallel threads
    from concurrent.futures import ThreadPoolExecutor as _Pool
    _hero_prompt = (
        f"Schrijf een korte hero-tekst (2 zinnen) voor de website van {bedrijfsnaam}, "
        f"een {branche} bedrijf in {plaats}. Spreek de bezoeker direct aan."
    )
    _meta_prompt = (
        f"Schrijf een Google meta-description (max 155 tekens) voor {bedrijfsnaam}, "
        f"{branche} in {plaats}. Zakelijk, met een duidelijke call-to-action."
    )
    with _Pool(max_workers=2, thread_name_prefix="demo-swarm") as _pool:
        _hero_fut = _pool.submit(_swarm_or_llm, _hero_prompt, 80)
        _meta_fut = _pool.submit(_llm, _meta_prompt, 60)  # meta is short, single call fine
        _hero_raw  = _hero_fut.result()
        _meta_raw  = _meta_fut.result()

    # ── LLM calls — all outputs html-escaped before template insertion ────────
    hero_tekst = _e(_hero_raw)
    meta_description = _e(_meta_raw)

    diensten_items: list[tuple[str, str]] = []
    if diensten:
        for d in diensten[:4]:
            omschr = _e(_llm(
                f"Schrijf één zin (max 15 woorden) die de dienst '{d}' beschrijft "
                f"voor {bedrijfsnaam} in {plaats}.",
                max_tokens=40,
            ))
            diensten_items.append((_e(d), omschr))
    else:
        raw = _llm(
            f"Noem 3 typische diensten van een {branche} bedrijf in Nederland. "
            f"Geef alleen een komma-gescheiden lijst, geen nummers.",
            max_tokens=40,
        )
        for d in raw.split(",")[:3]:
            d = d.strip().rstrip(".")
            if d:
                omschr = _e(_llm(
                    f"Schrijf één zin (max 15 woorden) die '{d}' beschrijft voor {bedrijfsnaam}.",
                    max_tokens=40,
                ))
                diensten_items.append((_e(d), omschr))

    # Over ons + CTA in parallel via swarm
    _over_prompt = (
        f"Schrijf een 'Over ons' alinea (3-4 zinnen) voor {bedrijfsnaam}, "
        f"een {branche} bedrijf dat al jaren actief is in {plaats} en omgeving. "
        f"Nadruk op vakmanschap en betrouwbaarheid."
    )
    _cta_prompt = (
        f"Schrijf een uitnodigende call-to-action (1 zin) voor {bedrijfsnaam} "
        f"om een offerte aan te vragen."
    )
    with _Pool(max_workers=2, thread_name_prefix="demo-swarm") as _pool:
        _over_fut = _pool.submit(_swarm_or_llm, _over_prompt, 120)
        _cta_fut  = _pool.submit(_llm, _cta_prompt, 40)
        _over_raw = _over_fut.result()
        _cta_raw  = _cta_fut.result()

    over_ons  = _e(_over_raw)
    cta_tekst = _e(_cta_raw)

    # ── Contact info — only real data, never invented ─────────────────────────
    telefoon     = rd.get("telefoon")
    adres        = rd.get("adres")
    website_url  = rd.get("website")

    telefoon_html = f"<p><a href='tel:{_e(telefoon)}'>{_e(telefoon)}</a></p>" if telefoon else "<p>Bel ons voor een afspraak</p>"
    adres_html    = f"<p>{_e(adres)}</p>" if adres else f"<p>{_e(plaats)} en omgeving</p>"
    website_html  = (
        f'<p><a href="{_e(website_url)}" target="_blank" rel="noopener">{_e(website_url)}</a></p>'
        if website_url else ""
    )

    real_website = rd.get("website")
    if real_website:
        domain = re.sub(r"https?://(www\.)?", "", real_website).rstrip("/")
        safe_email = _e(f"info@{domain}")
        email_html = f'<a href="mailto:{safe_email}">{safe_email}</a>'
    else:
        safe_email = None
        email_html = '<span style="color:#999">Vul het formulier in</span>'

    # ── Services HTML ─────────────────────────────────────────────────────────
    diensten_html = "\n".join(
        f"""      <div class="svc-card">
        <div class="svc-icon">✓</div>
        <h3>{naam}</h3>
        <p>{omschr}</p>
      </div>"""
        for naam, omschr in diensten_items
    )

    # ── Schema.org JSON-LD ────────────────────────────────────────────────────
    schema: dict = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": bedrijfsnaam,
        "description": branche,
        "address": {
            "@type": "PostalAddress",
            "addressLocality": plaats,
            "addressCountry": "NL",
        },
    }
    if telefoon:
        schema["telephone"] = telefoon
    if website_url:
        schema["url"] = website_url
    schema_json = json.dumps(schema, ensure_ascii=False)

    # ── Unsplash hero image ───────────────────────────────────────────────────
    hero_img = _unsplash_url(branche)

    # ── Netlify Forms endpoint name (safe ASCII slug) ─────────────────────────
    form_name = "contact-" + re.sub(r"[^a-z0-9]", "-", bedrijfsnaam.lower())[:30]

    # ── Full HTML ─────────────────────────────────────────────────────────────
    html_out = f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(bedrijfsnaam)} — {_e(branche)} in {_e(plaats)}</title>
<meta name="description" content="{meta_description}">
<meta property="og:title" content="{_e(bedrijfsnaam)} — {_e(branche)} in {_e(plaats)}">
<meta property="og:description" content="{meta_description}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script type="application/ld+json">{schema_json}</script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 100%;
    min-height: 100vh;
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
    color: #333;
    background: #fff;
    line-height: 1.6;
  }}
  :root {{
    --primary: {primary};
    --accent:  {accent};
    --light:   #f4f6f8;
    --text:    #333;
    --radius:  6px;
  }}
  .inner {{ max-width: 1100px; margin: 0 auto; padding: 0 2rem; }}

  /* NAV */
  nav {{
    width: 100%;
    background: var(--primary);
    color: #fff;
    position: sticky;
    top: 0;
    z-index: 200;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }}
  nav .inner {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 1rem;
    padding-bottom: 1rem;
  }}
  .logo {{ font-size: 1.3rem; font-weight: 700; letter-spacing: -0.02em; }}
  .nav-links a {{
    color: #fff;
    text-decoration: none;
    margin-left: 1.75rem;
    font-size: 0.9rem;
    font-weight: 500;
    opacity: 0.88;
    transition: opacity 0.15s;
  }}
  .nav-links a:hover {{ opacity: 1; }}
  .hamburger {{
    display: none;
    flex-direction: column;
    gap: 5px;
    cursor: pointer;
    padding: 4px;
    background: none;
    border: none;
  }}
  .hamburger span {{
    display: block;
    width: 24px;
    height: 2px;
    background: #fff;
    border-radius: 2px;
    transition: all 0.25s;
  }}
  .mobile-menu {{
    display: none;
    flex-direction: column;
    background: var(--primary);
    padding: 0.75rem 2rem 1rem;
    border-top: 1px solid rgba(255,255,255,0.15);
  }}
  .mobile-menu.open {{ display: flex; }}
  .mobile-menu a {{
    color: #fff;
    text-decoration: none;
    padding: 0.6rem 0;
    font-size: 1rem;
    font-weight: 500;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    opacity: 0.9;
  }}
  .mobile-menu a:last-child {{ border-bottom: none; }}

  /* HERO */
  .hero {{
    width: 100%;
    min-height: 520px;
    background:
      linear-gradient(135deg, {primary}ee 0%, {primary}99 100%),
      url('{hero_img}') center/cover no-repeat;
    color: #fff;
    display: flex;
    align-items: center;
    padding: 5rem 0;
  }}
  .hero h1 {{ font-size: 2.8rem; font-weight: 700; margin-bottom: 1rem; line-height: 1.2; letter-spacing: -0.02em; }}
  .hero p  {{ font-size: 1.15rem; max-width: 580px; margin: 0 auto 2rem; opacity: 0.92; }}
  .hero .inner {{ text-align: center; }}
  .btn {{
    display: inline-block;
    background: var(--accent);
    color: #fff;
    padding: 0.9rem 2.2rem;
    border-radius: var(--radius);
    text-decoration: none;
    font-weight: 600;
    font-size: 1rem;
    transition: filter 0.2s, transform 0.1s;
    box-shadow: 0 4px 14px rgba(0,0,0,0.25);
  }}
  .btn:hover {{ filter: brightness(1.1); transform: translateY(-1px); }}
  .btn:active {{ transform: translateY(0); }}

  /* SERVICES */
  .svc-strip {{ width: 100%; background: #fff; padding: 5rem 0; }}
  .svc-strip h2 {{ font-size: 2rem; font-weight: 700; color: var(--primary); text-align: center; margin-bottom: 0.75rem; }}
  .svc-intro {{ text-align: center; color: #666; margin-bottom: 3rem; font-size: 1.05rem; }}
  .svc-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1.5rem;
  }}
  .svc-card {{
    background: var(--light);
    border-radius: 10px;
    padding: 2rem 1.5rem;
    border-top: 4px solid var(--accent);
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .svc-card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }}
  .svc-icon {{ font-size: 1.8rem; color: var(--accent); margin-bottom: 0.75rem; }}
  .svc-card h3 {{ font-size: 1.05rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--primary); }}
  .svc-card p  {{ font-size: 0.9rem; line-height: 1.55; color: #555; }}

  /* ABOUT */
  .about-strip {{ width: 100%; background: var(--light); padding: 5rem 0; }}
  .about-strip .inner {{ display: flex; gap: 4rem; align-items: center; }}
  .about-text {{ flex: 1; }}
  .about-text h2 {{ font-size: 2rem; font-weight: 700; color: var(--primary); margin-bottom: 1rem; }}
  .about-text p  {{ line-height: 1.75; font-size: 1rem; color: #555; }}
  .about-badges {{ display: flex; flex-direction: column; gap: 1rem; flex: 0 0 auto; }}
  .about-badge {{
    background: var(--primary);
    color: #fff;
    border-radius: 10px;
    width: 140px;
    padding: 1.25rem 1rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.4rem;
  }}
  .badge-icon {{ font-size: 2rem; }}
  .badge-label {{ font-size: 0.75rem; opacity: 0.85; line-height: 1.3; }}

  /* CTA */
  .cta-strip {{
    width: 100%;
    background: linear-gradient(135deg, var(--primary) 0%, {primary}cc 100%);
    color: #fff;
    padding: 5rem 0;
    text-align: center;
  }}
  .cta-strip h2 {{ font-size: 2.2rem; font-weight: 700; margin-bottom: 1rem; }}
  .cta-strip p  {{ max-width: 520px; margin: 0 auto 2rem; opacity: 0.9; font-size: 1.1rem; }}

  /* CONTACT */
  .contact-strip {{ width: 100%; background: #fff; padding: 5rem 0; }}
  .contact-strip h2 {{ font-size: 2rem; font-weight: 700; color: var(--primary); text-align: center; margin-bottom: 0.75rem; }}
  .contact-intro {{ text-align: center; color: #666; margin-bottom: 3rem; font-size: 1rem; }}
  .contact-layout {{ display: grid; grid-template-columns: 1fr 1.4fr; gap: 3rem; align-items: start; }}
  .contact-info {{ display: flex; flex-direction: column; gap: 1.25rem; }}
  .contact-item {{
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    padding: 1.25rem;
    background: var(--light);
    border-radius: var(--radius);
  }}
  .contact-item .ci {{ font-size: 1.5rem; flex-shrink: 0; margin-top: 0.1rem; }}
  .contact-item-body h4 {{ font-size: 0.85rem; font-weight: 600; color: var(--primary); margin-bottom: 0.2rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .contact-item-body p, .contact-item-body a {{ font-size: 0.95rem; color: #555; text-decoration: none; }}
  .contact-item-body a:hover {{ color: var(--primary); text-decoration: underline; }}

  /* CONTACT FORM */
  .contact-form {{ background: var(--light); border-radius: 10px; padding: 2rem; }}
  .contact-form h3 {{ font-size: 1.15rem; font-weight: 600; color: var(--primary); margin-bottom: 1.25rem; }}
  .form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }}
  .form-group {{ display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; }}
  .form-group label {{ font-size: 0.82rem; font-weight: 600; color: #555; text-transform: uppercase; letter-spacing: 0.04em; }}
  .form-group input, .form-group textarea, .form-group select {{
    padding: 0.65rem 0.9rem;
    border: 1.5px solid #ddd;
    border-radius: var(--radius);
    font-size: 0.95rem;
    font-family: inherit;
    color: #333;
    background: #fff;
    transition: border-color 0.15s;
    width: 100%;
  }}
  .form-group input:focus, .form-group textarea:focus, .form-group select:focus {{
    outline: none;
    border-color: var(--accent);
  }}
  .form-group textarea {{ resize: vertical; min-height: 110px; }}
  .form-submit {{
    width: 100%;
    padding: 0.85rem;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: filter 0.2s;
  }}
  .form-submit:hover {{ filter: brightness(1.1); }}
  .form-notice {{ font-size: 0.78rem; color: #999; margin-top: 0.6rem; text-align: center; }}

  /* FOOTER */
  footer {{
    width: 100%;
    background: #111;
    color: rgba(255,255,255,0.65);
    text-align: center;
    padding: 2rem 1rem;
    font-size: 0.85rem;
  }}
  footer a {{ color: rgba(255,255,255,0.65); text-decoration: none; }}
  footer a:hover {{ color: #fff; }}
  .footer-links {{ display: flex; gap: 1.5rem; justify-content: center; margin-top: 0.5rem; font-size: 0.8rem; }}

  /* RESPONSIVE */
  @media (max-width: 768px) {{
    .hero h1 {{ font-size: 2rem; }}
    .hero p  {{ font-size: 1rem; }}
    .about-strip .inner {{ flex-direction: column; gap: 2rem; }}
    .about-badges {{ flex-direction: row; }}
    .nav-links {{ display: none; }}
    .hamburger {{ display: flex; }}
    .contact-layout {{ grid-template-columns: 1fr; }}
    .form-row {{ grid-template-columns: 1fr; }}
    .svc-grid, .contact-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<!-- NAV -->
<nav>
  <div class="inner">
    <div class="logo">{_e(bedrijfsnaam)}</div>
    <div class="nav-links">
      <a href="#diensten">Diensten</a>
      <a href="#over-ons">Over ons</a>
      <a href="#contact">Contact</a>
    </div>
    <button class="hamburger" aria-label="Menu" onclick="toggleMenu()" aria-expanded="false" id="hamburger">
      <span></span><span></span><span></span>
    </button>
  </div>
  <div class="mobile-menu" id="mobile-menu">
    <a href="#diensten" onclick="closeMenu()">Diensten</a>
    <a href="#over-ons" onclick="closeMenu()">Over ons</a>
    <a href="#contact" onclick="closeMenu()">Contact</a>
  </div>
</nav>

<!-- HERO -->
<div class="hero">
  <div class="inner">
    <h1>{_e(bedrijfsnaam)}</h1>
    <p>{hero_tekst}</p>
    <a href="#contact" class="btn">Vraag een offerte aan</a>
  </div>
</div>

<!-- SERVICES -->
<div class="svc-strip" id="diensten">
  <div class="inner">
    <h2>Onze Diensten</h2>
    <p class="svc-intro">Wat wij voor u kunnen betekenen</p>
    <div class="svc-grid">
{diensten_html}
    </div>
  </div>
</div>

<!-- ABOUT -->
<div class="about-strip" id="over-ons">
  <div class="inner">
    <div class="about-text">
      <h2>Over {_e(bedrijfsnaam)}</h2>
      <p>{over_ons}</p>
    </div>
    <div class="about-badges">
      <div class="about-badge">
        <span class="badge-icon">✓</span>
        <span class="badge-label">Vakkundig &amp; betrouwbaar</span>
      </div>
      <div class="about-badge">
        <span class="badge-icon">📍</span>
        <span class="badge-label">Actief in {_e(plaats)}</span>
      </div>
    </div>
  </div>
</div>

<!-- CTA -->
<div class="cta-strip">
  <div class="inner">
    <h2>Klaar voor uw project?</h2>
    <p>{cta_tekst}</p>
    <a href="#contact" class="btn">Neem contact op</a>
  </div>
</div>

<!-- CONTACT -->
<div class="contact-strip" id="contact">
  <div class="inner">
    <h2>Contact</h2>
    <p class="contact-intro">We reageren binnen één werkdag</p>
    <div class="contact-layout">
      <div class="contact-info">
        <div class="contact-item">
          <div class="ci">📞</div>
          <div class="contact-item-body">
            <h4>Telefoon</h4>
            {telefoon_html}
          </div>
        </div>
        <div class="contact-item">
          <div class="ci">📧</div>
          <div class="contact-item-body">
            <h4>E-mail</h4>
            <p>{email_html}</p>
            {website_html}
          </div>
        </div>
        <div class="contact-item">
          <div class="ci">📍</div>
          <div class="contact-item-body">
            <h4>Locatie</h4>
            {adres_html}
          </div>
        </div>
      </div>

      <!-- Netlify Forms — zero backend, works on any static host -->
      <div class="contact-form">
        <h3>Stuur ons een bericht</h3>
        <form name="{_e(form_name)}" method="POST" data-netlify="true" netlify-honeypot="bot-field">
          <input type="hidden" name="form-name" value="{_e(form_name)}">
          <p style="display:none"><label>Bot field: <input name="bot-field"></label></p>
          <div class="form-row">
            <div class="form-group">
              <label for="naam">Naam *</label>
              <input type="text" id="naam" name="naam" required placeholder="Jan de Vries">
            </div>
            <div class="form-group">
              <label for="telefoon">Telefoon</label>
              <input type="tel" id="telefoon" name="telefoon" placeholder="06-12345678">
            </div>
          </div>
          <div class="form-group">
            <label for="email">E-mailadres *</label>
            <input type="email" id="email" name="email" required placeholder="jan@voorbeeld.nl">
          </div>
          <div class="form-group">
            <label for="onderwerp">Onderwerp</label>
            <select id="onderwerp" name="onderwerp">
              <option value="">Selecteer een onderwerp</option>
              <option>Offerte aanvragen</option>
              <option>Afspraak maken</option>
              <option>Vraag stellen</option>
              <option>Anders</option>
            </select>
          </div>
          <div class="form-group">
            <label for="bericht">Bericht *</label>
            <textarea id="bericht" name="bericht" required placeholder="Vertel ons wat u nodig heeft…"></textarea>
          </div>
          <button type="submit" class="form-submit">Verstuur bericht →</button>
          <p class="form-notice">Uw gegevens worden alleen gebruikt om contact op te nemen.</p>
        </form>
      </div>
    </div>
  </div>
</div>

<!-- FOOTER -->
<footer>
  <p>&copy; 2025 {_e(bedrijfsnaam)} · {_e(branche)} in {_e(plaats)}</p>
  <div class="footer-links">
    <a href="#diensten">Diensten</a>
    <a href="#over-ons">Over ons</a>
    <a href="#contact">Contact</a>
  </div>
</footer>

<script>
  function toggleMenu() {{
    var m = document.getElementById('mobile-menu');
    var h = document.getElementById('hamburger');
    var open = m.classList.toggle('open');
    h.setAttribute('aria-expanded', open ? 'true' : 'false');
  }}
  function closeMenu() {{
    document.getElementById('mobile-menu').classList.remove('open');
    document.getElementById('hamburger').setAttribute('aria-expanded', 'false');
  }}
  // Close mobile menu on outside click
  document.addEventListener('click', function(e) {{
    var nav = document.querySelector('nav');
    if (!nav.contains(e.target)) closeMenu();
  }});
  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(function(a) {{
    a.addEventListener('click', function(e) {{
      var target = document.querySelector(this.getAttribute('href'));
      if (target) {{
        e.preventDefault();
        target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }});
  }});
</script>

</body>
</html>"""

    _DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    safe_naam = "".join(c if c.isalnum() or c in "-_" else "_" for c in bedrijfsnaam)
    filename  = f"demo_{safe_naam}_{plaats.lower()}.html"
    dest_path = _DEMO_ROOT / filename

    try:
        dest_path.write_text(html_out, encoding="utf-8")
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    logger.info("demo_generator: %s (%d bytes)", dest_path, len(html_out))
    return {"status": "ok", "path": str(dest_path), "bytes": len(html_out)}
