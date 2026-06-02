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
            "schrijft voor lokale bedrijven. Schrijf beknopte, wervende teksten in "
            "natuurlijk Nederlands. Geen markdown, geen Engels, alleen platte tekst. "
            "Verzin GEEN feiten, namen, diensten, jaartallen of cijfers die niet in "
            "de opdracht staan — schrijf alleen wervende, verbindende zinnen."
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


def _norm_pairs(items, k1: str, k2: str) -> list[tuple[str, str]]:
    """Normalize a list of dicts/strings/tuples into [(a, b)] pairs, dropping empties.

    Only uses what's there — never fabricates. Used for diensten/reviews/stats from
    the (Lars-confirmed) research data.
    """
    out: list[tuple[str, str]] = []
    for it in (items or []):
        if isinstance(it, dict):
            a, b = str(it.get(k1, "")).strip(), str(it.get(k2, "")).strip()
        elif isinstance(it, (list, tuple)) and len(it) >= 2:
            a, b = str(it[0]).strip(), str(it[1]).strip()
        else:
            a, b = str(it).strip(), ""
        if a:
            out.append((a, b))
    return out


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

    # ── Echte data uit research/Lars — diensten/reviews/stats/foto's: nooit verzonnen ──
    diensten_items = _norm_pairs(rd.get("diensten"), "naam", "omschrijving")
    review_items   = _norm_pairs(rd.get("reviews"), "tekst", "naam")
    stat_items     = _norm_pairs(rd.get("stats"), "cijfer", "label")
    fotos          = [f for f in (rd.get("fotos") or []) if isinstance(f, str) and f.strip()]
    social         = [s for s in (rd.get("social") or []) if isinstance(s, str) and s.strip()]
    telefoon       = (rd.get("telefoon") or "").strip()
    email          = (rd.get("email") or "").strip()
    adres          = (rd.get("adres") or "").strip()
    openingstijden = (rd.get("openingstijden") or "").strip()
    website        = (rd.get("website") or "").strip()
    diensten_namen = ", ".join(n for n, _ in diensten_items) if diensten_items else ""

    # ── Copy: de LLM schrijft ALLEEN wervende/verbindende zinnen rond echte data ──
    p_head = (f"Schrijf een korte, pakkende website-kop (H1, max 8 woorden) voor {bedrijfsnaam}, "
              f"een {branche} in {plaats}. Alleen wervende tekst, geen aanhalingstekens, geen verzonnen cijfers.")
    p_hero = (f"Schrijf 1-2 wervende zinnen onder de kop voor {bedrijfsnaam}, {branche} in {plaats}. "
              f"Spreek de bezoeker direct aan. Verzin geen feiten of cijfers.")
    p_meta = (f"Schrijf een Google meta-omschrijving (max 150 tekens) voor {bedrijfsnaam}, {branche} in {plaats}. "
              f"Uitnodigend, met een call-to-action.")
    _dienst_hint = f" Noem dat ze onder meer {diensten_namen} doen." if diensten_namen else ""
    p_over = (f"Schrijf een warme, wervende 'Over ons'-tekst (3-4 zinnen) voor {bedrijfsnaam}, "
              f"een {branche} in {plaats} en omgeving.{_dienst_hint} "
              f"Alleen wervende tekst — verzin GEEN jaartallen, cijfers, namen of diensten die niet genoemd zijn.")
    p_cta = f"Schrijf één wervende zin die aanzet tot contact opnemen met {bedrijfsnaam}. Geen prijs, geen cijfers."

    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="demo-copy") as pool:
        f_head = pool.submit(_llm, p_head, 30)
        f_hero = pool.submit(_swarm_or_llm, p_hero, ctxname, 80)
        f_meta = pool.submit(_llm, p_meta, 60)
        f_over = pool.submit(_swarm_or_llm, p_over, ctxname, 160)
        f_cta  = pool.submit(_llm, p_cta, 40)

        def _safe(fut, fallback):
            try:
                val = fut.result()
                return val.strip().strip('"“”') if val and val.strip() else fallback
            except Exception:  # noqa: BLE001
                return fallback

        head = _safe(f_head, f"Welkom bij {bedrijfsnaam}")
        hero_text = _safe(f_hero, f"{bedrijfsnaam} — uw {branche} in {plaats} en omgeving. Neem gerust contact op.")
        meta = _safe(f_meta, f"{bedrijfsnaam} — {branche} in {plaats}. Neem vrijblijvend contact op.")
        over_text = _safe(f_over, f"Bij {bedrijfsnaam} staat persoonlijke service voorop. Als {branche} in {plaats} "
                          f"helpen we je graag verder met een duidelijke, eerlijke aanpak.")
        cta_text = _safe(f_cta, f"Neem vandaag nog vrijblijvend contact op met {bedrijfsnaam}.")

    # ── Foto's (echt of leeg) ─────────────────────────────────────────────────
    hero_img  = fotos[0] if len(fotos) >= 1 else ""
    about_img = fotos[1] if len(fotos) >= 2 else ""
    gallery   = fotos[2:8]

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
        # Alleen echte, door Lars bevestigde data — leeg = sectie weg:
        "diensten": [(_e(n), _e(o)) for n, o in diensten_items],
        "reviews":  [(_e(t), _e(w)) for t, w in review_items if t],
        "stats":    [(_e(c), _e(l)) for c, l in stat_items if c],
        "values": [
            ("✓", "Persoonlijke aanpak", "Eén vast aanspreekpunt dat met je meedenkt."),
            ("★", "Duidelijke afspraken", "Heldere afspraken vooraf, geen verrassingen achteraf."),
            ("⚡", "Snel geregeld", "Korte lijnen — je hoeft nooit lang op antwoord te wachten."),
        ],
        "hero_img": _e(hero_img), "about_img": _e(about_img),
        "gallery": [_e(f) for f in gallery],
        "telefoon": _e(telefoon), "telefoon_raw": telefoon,
        "email": _e(email),
        "email_link": (f'<a href="mailto:{_e(email)}">{_e(email)}</a>' if email else ""),
        "adres": _e(adres),
        "openingstijden": _e(openingstijden),
        "social": [_e(s) for s in social],
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
