"""Bedrijf Finder — vind ECHTE lokale bedrijven via DuckDuckGo.

Geen verzonnen namen meer: we zoeken het web af op de exacte branche + plaats en
parsen echte bedrijven uit de resultaten. Lars selecteert wat hij wil toevoegen;
per kandidaat haalt de research-stap (bedrijf_research) daarna de echte gegevens op.

HARDE REGEL: niets verzinnen. Wat niet gevonden wordt, komt niet in de lijst.
"""
from __future__ import annotations

import logging
import re
import urllib.parse

from core.bedrijf_research import _fetch, _strip_tags, _SKIP_DOMAINS

logger = logging.getLogger(__name__)

# DuckDuckGo HTML result anchors + snippets.
_RESULT_A = re.compile(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_SNIPPET  = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S | re.I)
# Title separators — keep the part before the first one (usually the business name).
_TITLE_SPLIT = re.compile(r"\s*[|\-–—:•·]\s*")
# Leading filler words to drop from page titles.
_TITLE_FILLER = re.compile(r"^(over(\s+ons)?|welkom(\s+bij)?|home|homepage|contact)\s+", re.I)
# Listicles / directory pages / questions — not a single business.
_LISTICLE = re.compile(r"(^\s*(top\s*\d+|beste|de\s+\d+|\d+\s+beste)\b|\?\s*$|\bvergelijk\b|\breviews?\b)", re.I)


def _naam_uit_domein(url: str) -> str:
    """Fallback business name from a domain: beautyshades.nl -> Beautyshades."""
    host = urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    stem = host.split(".")[0] if host else ""
    stem = re.sub(r"[-_]+", " ", stem).strip()
    return stem[:1].upper() + stem[1:] if stem else ""


# Anchors on the lite endpoint (different markup, same uddg wrapping).
_LITE_A = re.compile(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def _is_blocked(html: str) -> bool:
    return "anomaly" in html.lower() or "/anomaly-modal" in html.lower()


def _ddg_results(query: str, timeout: int = 12) -> tuple[list[dict], bool]:
    """Run a DuckDuckGo query → ([{title,url,snippet}], blocked).

    Tries the html endpoint, falls back to the lite endpoint if blocked/empty.
    `blocked` is True when the search engine returned an anomaly/captcha page.
    """
    q = urllib.parse.quote_plus(query)
    html = _fetch("https://html.duckduckgo.com/html/?q=" + q, timeout=timeout)
    blocked = _is_blocked(html)
    out: list[dict] = []
    if html and not blocked:
        snippets = [_strip_tags(s).strip() for s in _SNIPPET.findall(html)]
        for i, (href, raw_title) in enumerate(_RESULT_A.findall(html)):
            real = _decode_ddg_url(href)
            title = re.sub(r"\s+", " ", _strip_tags(raw_title)).strip()
            if real and title:
                out.append({"title": title, "url": real, "snippet": snippets[i] if i < len(snippets) else ""})
    if not out:
        # Fallback: lite endpoint (often throttled less aggressively).
        lite = _fetch("https://lite.duckduckgo.com/lite/?q=" + q, timeout=timeout)
        if _is_blocked(lite):
            blocked = True
        else:
            for href, raw_title in _LITE_A.findall(lite):
                real = _decode_ddg_url(href)
                title = re.sub(r"\s+", " ", _strip_tags(raw_title)).strip()
                if real and title:
                    out.append({"title": title, "url": real, "snippet": ""})
            if out:
                blocked = False
    return out, blocked


def _decode_ddg_url(href: str) -> str:
    """DuckDuckGo wraps links as //duckduckgo.com/l/?uddg=<encoded>. Decode to the real URL."""
    if "uddg=" in href:
        try:
            q = urllib.parse.urlparse(href if href.startswith("http") else "https:" + href).query
            uddg = urllib.parse.parse_qs(q).get("uddg", [""])[0]
            if uddg:
                return urllib.parse.unquote(uddg)
        except Exception:
            return ""
    if href.startswith("http"):
        return href
    return ""


def _clean_naam(title: str, plaats: str) -> str:
    """Pull a business name out of a result title; drop taglines, filler and the city."""
    naam = _TITLE_FILLER.sub("", title).strip()
    naam = _TITLE_SPLIT.split(naam)[0].strip()
    # Strip a trailing ", Plaats" / "in Plaats"
    naam = re.sub(rf"\b(in|te)\s+{re.escape(plaats)}\b.*$", "", naam, flags=re.I).strip(" ,-")
    naam = re.sub(rf",?\s*{re.escape(plaats)}\s*$", "", naam, flags=re.I).strip(" ,-")
    return naam


def zoek_bedrijven(stad: str, branche: str, aantal: int = 8) -> dict:
    """Zoek echte lokale bedrijven via DuckDuckGo voor exact deze branche + plaats.

    Returns:
        {"ok": True, "kandidaten": [{bedrijfsnaam, plaats, branche, website,
          heeft_website, website_kwaliteit, type, contact}]}
    """
    stad = (stad or "").strip()
    branche = (branche or "").strip()
    if not stad or not branche:
        return {"ok": False, "error": "stad en branche zijn verplicht"}

    # Exacte branche-term tussen quotes lost de drift op (geen 'gerelateerde' branches).
    queries = [f'"{branche}" {stad}', f'{branche} {stad} bedrijf']
    results: list[dict] = []
    seen_urls: set[str] = set()
    any_blocked = False
    for q in queries:
        res, blocked = _ddg_results(q)
        any_blocked = any_blocked or blocked
        for r in res:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                results.append(r)
        if len(results) >= aantal * 4:
            break

    if not results and any_blocked:
        return {"ok": True, "kandidaten": [],
                "melding": "De zoekmachine blokkeert tijdelijk (te veel verzoeken). Wacht even en probeer opnieuw."}

    kandidaten: list[dict] = []
    seen_keys: set[str] = set()
    for r in results:
        if _LISTICLE.search(r["title"]):
            continue  # 'Top 10 …', '… reviews', '… ?' — geen los bedrijf
        host = urllib.parse.urlparse(r["url"]).netloc.lower()
        is_directory = any(skip in host for skip in _SKIP_DOMAINS)
        naam = _clean_naam(r["title"], stad)

        if is_directory:
            # Gevonden via een gids/social → eigen website onbekend, geen URL claimen.
            website, heeft_website, kwaliteit = "", False, "onbekend"
        else:
            # Eigen domein gevonden → ze hebben een website. Zwakke titel? Gebruik domeinnaam.
            scheme = urllib.parse.urlparse(r["url"])
            website = f"{scheme.scheme}://{scheme.netloc}"
            heeft_website, kwaliteit = True, "onbekend"
            if len(naam) < 3 or naam.lower() == branche.lower():
                naam = _naam_uit_domein(r["url"]) or naam

        if not naam or len(naam) < 2:
            continue
        key = re.sub(r"[^a-z0-9]", "", naam.lower())[:40]
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        kandidaten.append({
            "bedrijfsnaam": naam,
            "plaats": stad,
            "branche": branche,
            "website": website,
            "heeft_website": heeft_website,
            "website_kwaliteit": kwaliteit,
            "type": (r.get("snippet") or "")[:160],
            "contact": "",
        })
        if len(kandidaten) >= aantal:
            break

    if not kandidaten:
        return {"ok": True, "kandidaten": [], "melding": f"Geen bedrijven gevonden voor '{branche}' in {stad}. Probeer een andere term of plaats."}
    logger.info("bedrijf_finder: '%s' in %s — %d echte kandidaten", branche, stad, len(kandidaten))
    return {"ok": True, "kandidaten": kandidaten}
