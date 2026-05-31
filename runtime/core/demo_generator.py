"""Demo-website generator — one business at a time.

Calls the local Ollama model to write Dutch copy for each section,
then assembles a single-file HTML page.

Hard limit: ONE business per call. No batching.
"""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re
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
    return "#1a3a5c", "#e87b1e"


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

    # ── LLM calls — all outputs are html-escaped before template insertion ──────
    hero_tekst = _e(_llm(
        f"Schrijf een korte hero-tekst (2 zinnen) voor de website van {bedrijfsnaam}, "
        f"een {branche} bedrijf in {plaats}. Spreek de bezoeker direct aan.",
        max_tokens=80,
    ))

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

    over_ons = _e(_llm(
        f"Schrijf een 'Over ons' alinea (3-4 zinnen) voor {bedrijfsnaam}, "
        f"een {branche} bedrijf dat al jaren actief is in {plaats} en omgeving. "
        f"Nadruk op vakmanschap en betrouwbaarheid.",
        max_tokens=120,
    ))

    cta_tekst = _e(_llm(
        f"Schrijf een uitnodigende call-to-action (1 zin) voor {bedrijfsnaam} "
        f"om een offerte aan te vragen.",
        max_tokens=40,
    ))

    # Real contact info from research_data — never invent phone/address
    telefoon_html = (
        f"<p>{_e(rd['telefoon'])}</p>" if rd.get("telefoon")
        else "<p>Bel ons voor een afspraak</p>"
    )
    adres_html = (
        f"<p>{_e(rd['adres'])}</p>" if rd.get("adres")
        else f"<p>{_e(plaats)} en omgeving</p>"
    )
    website_html = (
        f'<p><a href="{_e(rd["website"])}" style="color:var(--accent)">{_e(rd["website"])}</a></p>'
        if rd.get("website") else ""
    )

    # ── Services HTML ──────────────────────────────────────────────────────────
    diensten_html = "\n".join(
        f"""        <div class="svc-card">
          <div class="svc-icon">&#10003;</div>
          <h3>{naam}</h3>
          <p>{omschr}</p>
        </div>"""
        for naam, omschr in diensten_items
    )

    # Only show email if we have a real website to derive it from — never invent one
    real_website = (research_data or {}).get("website")
    if real_website:
        domain = re.sub(r"https?://(www\.)?", "", real_website).rstrip("/")
        safe_email = _e(f"info@{domain}")
    else:
        safe_email = None

    # ── Full HTML template ─────────────────────────────────────────────────────
    # Layout principle: full-width colored stripes via outer divs,
    # centered content via inner .inner divs. body has no max-width.
    html_out = f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(bedrijfsnaam)} — {_e(branche)} in {_e(plaats)}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 100%;
    min-height: 100vh;
    font-family: 'Segoe UI', Arial, sans-serif;
    color: #333;
    background: #fff;
  }}
  :root {{
    --primary: {primary};
    --accent:  {accent};
    --light:   #f4f6f8;
    --text:    #333;
  }}

  /* ── centered content container ── */
  .inner {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 2rem;
  }}

  /* ── NAV (full-width stripe) ── */
  nav {{
    width: 100%;
    background: var(--primary);
    color: #fff;
    position: sticky;
    top: 0;
    z-index: 100;
  }}
  nav .inner {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 1rem;
    padding-bottom: 1rem;
  }}
  .logo {{ font-size: 1.4rem; font-weight: 700; }}
  .nav-links a {{
    color: #fff;
    text-decoration: none;
    margin-left: 1.5rem;
    font-size: 0.95rem;
    opacity: 0.9;
  }}
  .nav-links a:hover {{ opacity: 1; text-decoration: underline; }}

  /* ── HERO (full-width stripe) ── */
  .hero {{
    width: 100%;
    background: linear-gradient(135deg, var(--primary) 0%, {primary}cc 100%);
    color: #fff;
    padding: 5rem 0;
    text-align: center;
  }}
  .hero h1 {{ font-size: 2.8rem; margin-bottom: 1rem; line-height: 1.2; }}
  .hero p  {{ font-size: 1.2rem; max-width: 640px; margin: 0 auto 2rem; opacity: 0.9; }}
  .btn {{
    display: inline-block;
    background: var(--accent);
    color: #fff;
    padding: 0.9rem 2.2rem;
    border-radius: 4px;
    text-decoration: none;
    font-weight: 600;
    font-size: 1rem;
    transition: opacity 0.2s;
  }}
  .btn:hover {{ opacity: 0.85; }}

  /* ── SERVICES (full-width stripe, light bg) ── */
  .svc-strip {{
    width: 100%;
    background: #fff;
    padding: 4rem 0;
  }}
  .svc-strip h2 {{
    font-size: 1.9rem;
    color: var(--primary);
    text-align: center;
    margin-bottom: 2.5rem;
  }}
  .svc-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1.5rem;
  }}
  .svc-card {{
    background: var(--light);
    border-radius: 8px;
    padding: 1.8rem 1.5rem;
    border-top: 4px solid var(--accent);
    text-align: center;
  }}
  .svc-icon {{ font-size: 1.6rem; color: var(--accent); margin-bottom: 0.5rem; }}
  .svc-card h3 {{ font-size: 1.05rem; margin-bottom: 0.5rem; color: var(--primary); }}
  .svc-card p  {{ font-size: 0.9rem; line-height: 1.5; }}

  /* ── ABOUT (full-width, light bg) ── */
  .about-strip {{
    width: 100%;
    background: var(--light);
    padding: 4rem 0;
  }}
  .about-strip .inner {{ display: flex; gap: 3rem; align-items: center; }}
  .about-text {{ flex: 1; }}
  .about-text h2 {{ font-size: 1.9rem; color: var(--primary); margin-bottom: 1rem; }}
  .about-text p  {{ line-height: 1.7; font-size: 1rem; }}
  .about-badge {{
    flex: 0 0 auto;
    background: var(--primary);
    color: #fff;
    border-radius: 50%;
    width: 140px;
    height: 140px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 1rem;
  }}
  .about-badge .badge-icon {{ font-size: 2.5rem; }}
  .about-badge .badge-label {{ font-size: 0.75rem; opacity: 0.85; margin-top: 0.3rem; }}

  /* ── CTA (full-width, primary bg) ── */
  .cta-strip {{
    width: 100%;
    background: var(--primary);
    color: #fff;
    padding: 4rem 0;
    text-align: center;
  }}
  .cta-strip h2 {{ font-size: 2rem; margin-bottom: 1rem; }}
  .cta-strip p  {{ max-width: 520px; margin: 0 auto 2rem; opacity: 0.9; font-size: 1.1rem; }}

  /* ── CONTACT (full-width, white) ── */
  .contact-strip {{
    width: 100%;
    background: #fff;
    padding: 4rem 0;
  }}
  .contact-strip h2 {{
    font-size: 1.9rem;
    color: var(--primary);
    text-align: center;
    margin-bottom: 2.5rem;
  }}
  .contact-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.5rem;
    text-align: center;
  }}
  .contact-item {{
    padding: 1.8rem 1.5rem;
    background: var(--light);
    border-radius: 8px;
  }}
  .contact-item .ci {{ font-size: 2rem; margin-bottom: 0.5rem; }}
  .contact-item h4 {{ color: var(--primary); margin-bottom: 0.4rem; font-size: 1rem; }}
  .contact-item p, .contact-item a {{ font-size: 0.95rem; color: var(--text); }}

  /* ── FOOTER (full-width, dark) ── */
  footer {{
    width: 100%;
    background: #111;
    color: rgba(255,255,255,0.75);
    text-align: center;
    padding: 1.5rem;
    font-size: 0.85rem;
  }}

  /* ── RESPONSIVE ── */
  @media (max-width: 768px) {{
    .hero h1 {{ font-size: 1.9rem; }}
    .hero p  {{ font-size: 1rem; }}
    .about-strip .inner {{ flex-direction: column; }}
    .about-badge {{ width: 110px; height: 110px; }}
    .nav-links {{ display: none; }}
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
    <div class="about-badge">
      <span class="badge-icon">✓</span>
      <span class="badge-label">Vakman in<br>{_e(plaats)}</span>
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
    <div class="contact-grid">
      <div class="contact-item">
        <div class="ci">📞</div>
        <h4>Bel ons</h4>
        {telefoon_html}
      </div>
      <div class="contact-item">
        <div class="ci">📧</div>
        <h4>E-mail</h4>
        {f'<p>{safe_email}</p>' if safe_email else '<p style="color:#999">Neem contact op via het formulier</p>'}
        {website_html}
      </div>
      <div class="contact-item">
        <div class="ci">📍</div>
        <h4>Locatie</h4>
        {adres_html}
      </div>
    </div>
  </div>
</div>

<!-- FOOTER -->
<footer>
  <p>&copy; 2025 {_e(bedrijfsnaam)} — {_e(branche)} in {_e(plaats)}</p>
  <p style="margin-top:0.4rem;opacity:0.6;font-size:0.75rem;">Demo-website gegenereerd door AI Employee</p>
</footer>

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
    return {"status": "ok", "path": str(dest_path), "bytes": len(html_out.encode("utf-8"))}
