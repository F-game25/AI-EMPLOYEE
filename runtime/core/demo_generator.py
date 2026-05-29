"""Demo-website generator — one business at a time.

Calls the local Ollama model to write Dutch copy for each section,
then assembles a single-file HTML page and writes it via write_file_tool.

Hard limit: ONE business per call. No batching.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:latest")

# Output goes into ~/.ai-employee/state/artifacts/demos/
_AI_HOME    = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_DEMO_ROOT  = _AI_HOME / "state" / "artifacts" / "demos"

# Validate at import time — target is fully determined by env var, never by user input.
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
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310 — scheme validated above
        body = json.loads(resp.read())
    return body.get("response", "").strip()


def _kleur_voor_branche(branche: str) -> tuple[str, str]:
    """Return (primary, accent) hex colours based on branche."""
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
    return "#1a3a5c", "#e87b1e"


def genereer_demo(
    *,
    bedrijfsnaam: str,
    plaats: str,
    branche: str,
    diensten: list[str] | None = None,
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

    logger.info("demo_generator: genereren voor '%s' (%s, %s)", bedrijfsnaam, plaats, branche)

    # ── LLM calls ──────────────────────────────────────────────────────────────
    hero_tekst = _llm(
        f"Schrijf een korte hero-tekst (2 zinnen) voor de website van {bedrijfsnaam}, "
        f"een {branche} bedrijf in {plaats}. Spreek de bezoeker direct aan.",
        max_tokens=80,
    )

    diensten_tekst_items: list[tuple[str, str]] = []
    if diensten:
        for d in diensten[:4]:
            omschr = _llm(
                f"Schrijf één zin (max 15 woorden) die de dienst '{d}' beschrijft "
                f"voor {bedrijfsnaam} in {plaats}.",
                max_tokens=40,
            )
            diensten_tekst_items.append((d, omschr))
    else:
        # Let LLM invent 3 typical services
        raw = _llm(
            f"Noem 3 typische diensten van een {branche} bedrijf in Nederland. "
            f"Geef alleen een komma-gescheiden lijst, geen nummers.",
            max_tokens=40,
        )
        for d in raw.split(",")[:3]:
            d = d.strip().rstrip(".")
            if d:
                omschr = _llm(
                    f"Schrijf één zin (max 15 woorden) die '{d}' beschrijft voor {bedrijfsnaam}.",
                    max_tokens=40,
                )
                diensten_tekst_items.append((d, omschr))

    over_ons = _llm(
        f"Schrijf een 'Over ons' alinea (3-4 zinnen) voor {bedrijfsnaam}, "
        f"een {branche} bedrijf dat al jaren actief is in {plaats} en omgeving. "
        f"Nadruk op vakmanschap en betrouwbaarheid.",
        max_tokens=120,
    )

    cta_tekst = _llm(
        f"Schrijf een uitnodigende call-to-action (1 zin) voor {bedrijfsnaam} "
        f"om een offerte aan te vragen.",
        max_tokens=40,
    )

    # ── HTML assembly ──────────────────────────────────────────────────────────
    diensten_html = "\n".join(
        f"""
        <div class="service-card">
          <div class="service-icon">&#10003;</div>
          <h3>{naam}</h3>
          <p>{omschr}</p>
        </div>"""
        for naam, omschr in diensten_tekst_items
    )

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{bedrijfsnaam} — {branche} in {plaats}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --primary: {primary};
    --accent:  {accent};
    --light:   #f8f9fa;
    --text:    #333;
  }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: var(--text); }}

  /* NAV */
  nav {{
    background: var(--primary); color: #fff; padding: 1rem 2rem;
    display: flex; justify-content: space-between; align-items: center;
    position: sticky; top: 0; z-index: 100;
  }}
  .logo {{ font-size: 1.4rem; font-weight: 700; letter-spacing: -0.5px; }}
  .nav-links a {{
    color: #fff; text-decoration: none; margin-left: 1.5rem;
    font-size: 0.95rem; opacity: 0.9;
  }}
  .nav-links a:hover {{ opacity: 1; text-decoration: underline; }}

  /* HERO */
  .hero {{
    background: linear-gradient(135deg, var(--primary) 0%, {primary}cc 100%);
    color: #fff; padding: 5rem 2rem; text-align: center;
  }}
  .hero h1 {{ font-size: 2.5rem; margin-bottom: 1rem; line-height: 1.2; }}
  .hero p  {{ font-size: 1.2rem; max-width: 600px; margin: 0 auto 2rem; opacity: 0.9; }}
  .btn {{
    display: inline-block; background: var(--accent); color: #fff;
    padding: 0.85rem 2rem; border-radius: 4px; text-decoration: none;
    font-weight: 600; font-size: 1rem; transition: opacity 0.2s;
  }}
  .btn:hover {{ opacity: 0.85; }}

  /* SECTIONS */
  section {{ padding: 4rem 2rem; max-width: 1000px; margin: 0 auto; }}
  section h2 {{
    font-size: 1.9rem; color: var(--primary);
    margin-bottom: 2rem; text-align: center;
  }}

  /* SERVICES */
  .services-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.5rem;
  }}
  .service-card {{
    background: var(--light); border-radius: 8px; padding: 1.5rem;
    border-top: 4px solid var(--accent); text-align: center;
  }}
  .service-icon {{ font-size: 1.5rem; color: var(--accent); margin-bottom: 0.5rem; }}
  .service-card h3 {{ font-size: 1.1rem; margin-bottom: 0.5rem; color: var(--primary); }}
  .service-card p  {{ font-size: 0.9rem; line-height: 1.5; }}

  /* ABOUT */
  .about-section {{ background: var(--light); }}
  .about-section section {{ display: flex; gap: 3rem; align-items: center; }}
  .about-text {{ flex: 1; }}
  .about-text p {{ line-height: 1.7; font-size: 1rem; }}
  .about-badge {{
    flex: 0 0 auto; background: var(--primary); color: #fff;
    border-radius: 50%; width: 140px; height: 140px;
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; text-align: center; padding: 1rem;
  }}
  .about-badge .years {{ font-size: 2.5rem; font-weight: 700; }}
  .about-badge .label {{ font-size: 0.75rem; opacity: 0.85; }}

  /* CTA */
  .cta-section {{
    background: var(--primary); color: #fff; text-align: center; padding: 4rem 2rem;
  }}
  .cta-section h2 {{ color: #fff; }}
  .cta-section p  {{ margin: 1rem auto 2rem; max-width: 500px; opacity: 0.9; }}

  /* CONTACT */
  .contact-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.5rem; text-align: center;
  }}
  .contact-item {{ padding: 1.5rem; background: var(--light); border-radius: 8px; }}
  .contact-item .ci {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
  .contact-item h4 {{ color: var(--primary); margin-bottom: 0.25rem; }}

  /* FOOTER */
  footer {{
    background: var(--primary); color: #fff; text-align: center;
    padding: 1.5rem; font-size: 0.85rem; opacity: 0.9;
  }}

  @media (max-width: 600px) {{
    .hero h1 {{ font-size: 1.8rem; }}
    .about-section section {{ flex-direction: column; }}
    .nav-links {{ display: none; }}
  }}
</style>
</head>
<body>

<nav>
  <div class="logo">{bedrijfsnaam}</div>
  <div class="nav-links">
    <a href="#diensten">Diensten</a>
    <a href="#over-ons">Over ons</a>
    <a href="#contact">Contact</a>
  </div>
</nav>

<div class="hero">
  <h1>{bedrijfsnaam}</h1>
  <p>{hero_tekst}</p>
  <a href="#contact" class="btn">Vraag een offerte aan</a>
</div>

<section id="diensten">
  <h2>Onze Diensten</h2>
  <div class="services-grid">
    {diensten_html}
  </div>
</section>

<div class="about-section">
  <section id="over-ons">
    <div class="about-text">
      <h2 style="text-align:left;">Over {bedrijfsnaam}</h2>
      <p>{over_ons}</p>
    </div>
    <div class="about-badge">
      <span class="years">✓</span>
      <span class="label">Vakman in<br>{plaats}</span>
    </div>
  </section>
</div>

<div class="cta-section">
  <h2>Klaar voor uw project?</h2>
  <p>{cta_tekst}</p>
  <a href="#contact" class="btn">Neem contact op</a>
</div>

<section id="contact">
  <h2>Contact</h2>
  <div class="contact-grid">
    <div class="contact-item">
      <div class="ci">📞</div>
      <h4>Bel ons</h4>
      <p>Wij staan voor u klaar</p>
    </div>
    <div class="contact-item">
      <div class="ci">📧</div>
      <h4>E-mail</h4>
      <p>info@{bedrijfsnaam.lower().replace(' ','-')}.nl</p>
    </div>
    <div class="contact-item">
      <div class="ci">📍</div>
      <h4>Locatie</h4>
      <p>{plaats} en omgeving</p>
    </div>
  </div>
</section>

<footer>
  <p>&copy; 2025 {bedrijfsnaam} — {branche} in {plaats} | Alle rechten voorbehouden</p>
  <p style="font-size:0.75rem;margin-top:0.4rem;opacity:0.6;">Demo-website gegenereerd door AI Employee</p>
</footer>

</body>
</html>"""

    # ── Write to disk via write_file_tool ──────────────────────────────────────
    _DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    safe_naam = "".join(c if c.isalnum() or c in "-_" else "_" for c in bedrijfsnaam)
    filename  = f"demo_{safe_naam}_{plaats.lower()}.html"
    dest_path = _DEMO_ROOT / filename

    try:
        dest_path.write_text(html, encoding="utf-8")
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    logger.info("demo_generator: weggeschreven naar %s (%d bytes)", dest_path, len(html))
    return {"status": "ok", "path": str(dest_path), "bytes": len(html.encode("utf-8"))}
