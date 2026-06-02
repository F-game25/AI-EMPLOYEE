"""Demo-website generator — one business at a time.

Generates a UNIQUE, multi-page demo website (Home, Diensten, Over ons, Contact).
The local Ollama model writes only the Dutch copy; layout, styling and structure
come from the hand-built block design system in `core.demo_blocks`, so model
output can never break the page. Every business gets a distinct palette, font
pair, style theme and section-variant mix (deterministic per business), while the
four pages stay coherent as one site.

- All copy is HTML-escaped before insertion (see `_e`)
- No fake phone/address/email — only real data from research_data
- Output: a folder of HTML files under state/artifacts/demos/<slug>/
"""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import demo_blocks

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


def _unsplash_url(branche: str, w: int = 1400, h: int = 600, sig: int = 1) -> str:
    b = branche.lower()
    keyword = "local+business+professional"
    for k, v in _UNSPLASH_KEYWORDS.items():
        if k in b:
            keyword = v
            break
    # Unsplash Source — stable, no API key, delivers high-quality CC0 images.
    # `sig` varies the image between hero and about so they are not identical.
    return f"https://source.unsplash.com/featured/{w}x{h}/?{urllib.parse.quote(keyword)}&sig={sig}"


def _slugify(*parts: str) -> str:
    raw = "_".join(p for p in parts if p)
    slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return slug[:60] or "demo"


def _swarm_or_llm(prompt: str, context: str, max_tokens: int = 120) -> str:
    """Run the swarm engine if available, otherwise a single LLM call."""
    if os.environ.get("SWARM_DEMO", "1") != "0":
        try:
            from core.swarm_engine import swarm_pitch
            result = swarm_pitch(prompt, context=context, n_agents=3)
            if result.answer and result.confidence > 0.3:
                return result.answer
        except Exception as exc:  # noqa: BLE001 — best-effort, fall back to LLM
            logger.debug("demo swarm fallback: %s", exc)
    return _llm(prompt, max_tokens=max_tokens)


def _diensten_uit_llm(bedrijfsnaam: str, branche: str, plaats: str) -> list[tuple[str, str]]:
    """Ask for 4 services + one-line descriptions in a single call; parse safely."""
    raw = _llm(
        f"Noem 4 typische diensten van een {branche} bedrijf in Nederland. "
        f"Geef elke dienst op een nieuwe regel in het formaat 'Dienst: korte omschrijving "
        f"van max 12 woorden'. Geen nummers, geen markdown.",
        max_tokens=160,
    )
    items: list[tuple[str, str]] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-•0123456789. ").strip()
        if not line:
            continue
        if ":" in line:
            naam, _, omschr = line.partition(":")
        elif "—" in line:
            naam, _, omschr = line.partition("—")
        else:
            naam, omschr = line, ""
        naam = naam.strip().rstrip(".")
        omschr = omschr.strip() or f"Vakkundig {naam.lower()} door {bedrijfsnaam}."
        if naam:
            items.append((naam, omschr))
        if len(items) >= 4:
            break
    if not items:
        items = [
            ("Advies op maat", f"Persoonlijk advies voor uw situatie in {plaats}."),
            ("Vakkundige uitvoering", "Net en volgens afspraak uitgevoerd."),
            ("Onderhoud & service", "Wij blijven bereikbaar, ook na de klus."),
            ("Spoedhulp", "Snel ter plaatse wanneer het nodig is."),
        ]
    return items


def genereer_demo(
    *,
    bedrijfsnaam: str,
    plaats: str,
    branche: str,
    diensten: list[str] | None = None,
    research_data: dict | None = None,
    job_id: str | None = None,
) -> dict:
    """Generate a unique multi-page demo website for ONE business.

    Returns:
        {"status": "ok", "dir": "<abs dir>", "slug": "<slug>",
         "pages": ["index.html", ...], "path": "<abs index.html>", "bytes": N}
    or  {"status": "error", "error": "..."}
    """
    if not bedrijfsnaam or not plaats or not branche:
        return {"status": "error", "error": "bedrijfsnaam, plaats en branche zijn verplicht"}

    rd = research_data or {}
    slug = _slugify(bedrijfsnaam, plaats)
    seed = job_id or slug
    ctxname = f"{bedrijfsnaam}, {branche} in {plaats}"
    logger.info("demo_generator: genereren voor '%s' (%s, %s)", bedrijfsnaam, plaats, branche)

    # ── Copy generation — batched in parallel threads ─────────────────────────
    p_head = (f"Schrijf een korte, pakkende website-koptekst (H1, max 8 woorden) voor {bedrijfsnaam}, "
              f"een {branche} bedrijf in {plaats}. Geen aanhalingstekens.")
    p_hero = (f"Schrijf 1-2 wervende zinnen onder de koptekst voor {bedrijfsnaam}, {branche} in {plaats}. "
              f"Spreek de bezoeker direct aan.")
    p_meta = (f"Schrijf een Google meta-description (max 150 tekens) voor {bedrijfsnaam}, {branche} in {plaats}. "
              f"Zakelijk met een call-to-action.")
    p_over = (f"Schrijf een 'Over ons'-tekst van 4-5 zinnen voor {bedrijfsnaam}, een {branche} bedrijf "
              f"dat actief is in {plaats} en omgeving. Nadruk op vakmanschap en betrouwbaarheid.")
    p_cta = f"Schrijf één wervende zin die aanzet tot het aanvragen van een offerte bij {bedrijfsnaam}."
    p_rev = [
        f"Schrijf een korte klantreview (2 zinnen) voor {bedrijfsnaam}, {branche}. Positief en realistisch, zonder aanhalingstekens.",
        f"Schrijf een andere korte klantreview (2 zinnen) voor {bedrijfsnaam}, {branche}. Andere toon, noem een concreet detail, zonder aanhalingstekens.",
        f"Schrijf nog een korte klantreview (1-2 zinnen) voor {bedrijfsnaam}, {branche}. Kort en krachtig, zonder aanhalingstekens.",
    ]

    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="demo-copy") as pool:
        f_head = pool.submit(_llm, p_head, 30)
        f_hero = pool.submit(_swarm_or_llm, p_hero, ctxname, 80)
        f_meta = pool.submit(_llm, p_meta, 60)
        f_over = pool.submit(_swarm_or_llm, p_over, ctxname, 160)
        f_cta = pool.submit(_llm, p_cta, 40)
        f_dien = pool.submit(_diensten_uit_llm, bedrijfsnaam, branche, plaats)
        f_rev = [pool.submit(_llm, pr, 60) for pr in p_rev]

        def _safe(fut, fallback):
            try:
                val = fut.result()
                return val.strip() if val and val.strip() else fallback
            except Exception:  # noqa: BLE001
                return fallback

        head = _safe(f_head, f"Uw {branche} in {plaats}")
        hero_text = _safe(f_hero, f"Vakwerk en persoonlijke service van {bedrijfsnaam} — in {plaats} en omgeving.")
        meta = _safe(f_meta, f"{bedrijfsnaam} — {branche} in {plaats}. Vraag vrijblijvend een offerte aan.")
        over_text = _safe(f_over, f"{bedrijfsnaam} is een betrouwbaar {branche} bedrijf in {plaats}. "
                          f"Wij staan voor vakmanschap, eerlijk advies en netjes werk.")
        cta_text = _safe(f_cta, f"Vraag vandaag nog vrijblijvend een offerte aan bij {bedrijfsnaam}.")
        diensten_items = _safe_list(f_dien)
        reviews = []
        rev_fallbacks = [
            f"Erg tevreden met {bedrijfsnaam}. Snel, netjes en een eerlijke prijs.",
            f"Vakkundige service en goede communicatie. Ik raad {bedrijfsnaam} zeker aan.",
            f"Keurig werk geleverd, helemaal volgens afspraak.",
        ]
        for fut, fb in zip(f_rev, rev_fallbacks):
            reviews.append(_safe(fut, fb).strip('"“” '))

    # ── Real contact data only ────────────────────────────────────────────────
    telefoon = rd.get("telefoon") or ""
    adres = rd.get("adres") or ""
    website = rd.get("website") or ""
    if website:
        domain = re.sub(r"https?://(www\.)?", "", website).rstrip("/")
        email = f"info@{domain}"
    else:
        email = ""

    # ── Build escaped context for the block system ────────────────────────────
    over_paras = _split_paragraphs(over_text)
    ctx = {
        "naam": _e(bedrijfsnaam), "naam_raw": bedrijfsnaam,
        "branche": _e(branche), "branche_raw": branche,
        "plaats": _e(plaats), "plaats_raw": plaats,
        "initial": _e(bedrijfsnaam.strip()[:1].upper() or "•"),
        "hero_title": _e(head), "hero_text": _e(hero_text), "meta": _e(meta),
        "over_kort": _e(over_paras[0]),
        "over_lang": [_e(p) for p in over_paras],
        "cta_text": _e(cta_text),
        "diensten": [(_e(n), _e(o)) for n, o in diensten_items],
        "reviews": [(_e(t), w) for t, w in zip(reviews, ["Particuliere klant", f"Ondernemer uit {_e(plaats)}", "Vaste klant"])],
        "values": [
            ("✓", "Betrouwbaar", "Afspraak is afspraak — op tijd en zonder verrassingen."),
            ("★", "Vakkundig", "Jarenlange ervaring en oog voor detail in elke klus."),
            ("⚡", "Snel ter plaatse", "Korte lijnen en snelle service, ook bij spoed."),
        ],
        "stats": [("Gratis", "Offerte op maat"), ("1 dag", "Snelle reactie"),
                  ("Lokaal", f"Actief in {_e(plaats)}"), ("Eerlijk", "Vaste prijzen")],
        "hero_img": _unsplash_url(branche, sig=1),
        "about_img": _unsplash_url(branche, 1000, 800, sig=2),
        "telefoon": _e(telefoon), "telefoon_raw": telefoon,
        "adres": _e(adres),
        "email": _e(email),
        "email_link": (f'<a href="mailto:{_e(email)}">{_e(email)}</a>' if email else ""),
        "website": _e(website), "website_raw": website,
        "website_link": (f'<a href="{_e(website)}" target="_blank" rel="noopener">{_e(website)}</a>' if website else ""),
        "form_name": "contact-" + re.sub(r"[^a-z0-9]", "-", bedrijfsnaam.lower())[:30],
        "jaar": _e(str(__import__("datetime").datetime.now().year)),
    }

    # ── Compose + write the multi-page site ───────────────────────────────────
    theme = demo_blocks.build_theme(seed, branche)
    pages = demo_blocks.render_site(ctx, theme)

    dest_dir = _DEMO_ROOT / slug
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for fname, html_doc in pages.items():
            (dest_dir / fname).write_text(html_doc, encoding="utf-8")
            total += len(html_doc)
    except OSError as exc:
        return {"status": "error", "error": f"Kon demo niet wegschrijven: {exc}"}

    logger.info("demo_generator: %s (%d pagina's, %d bytes, thema %s)",
                dest_dir, len(pages), total, theme["key"])
    return {
        "status": "ok",
        "dir": str(dest_dir),
        "slug": slug,
        "pages": list(pages.keys()),
        "path": str(dest_dir / "index.html"),  # backward compat
        "theme": theme["key"],
        "bytes": total,
    }


def _split_paragraphs(text: str) -> list[str]:
    """Split a copy block into 1-2 paragraphs for the about section."""
    text = (text or "").strip()
    if not text:
        return [""]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) <= 2:
        return [text]
    mid = (len(sentences) + 1) // 2
    return [" ".join(sentences[:mid]).strip(), " ".join(sentences[mid:]).strip()]


def _safe_list(fut) -> list[tuple[str, str]]:
    try:
        val = fut.result()
        return val if val else []
    except Exception:  # noqa: BLE001
        return [
            ("Advies op maat", "Persoonlijk advies voor uw situatie."),
            ("Vakkundige uitvoering", "Net en volgens afspraak uitgevoerd."),
            ("Onderhoud & service", "Wij blijven bereikbaar, ook na de klus."),
            ("Spoedhulp", "Snel ter plaatse wanneer het nodig is."),
        ]
