"""Bedrijf Research — haal echte info op over een bedrijf via DuckDuckGo.

Geen verzonnen gegevens: velden die niet gevonden worden staan op None.

Website-kwaliteitsscore (website_status):
  "geen_site"   — geen website gevonden → ideale klant
  "slechte_site" — site gevonden maar waarschijnlijk verouderd/mobiel-onvriendelijk → kans
  "goede_site"  — site ziet er modern uit → sla over, of pitch redesign

Lars beslist zelf wat hij doet met elke kandidaat.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl,en;q=0.9",
}

_NL_PHONE = re.compile(r"\b(?:0[0-9]{8,9}|\+31[0-9]{8,9})\b")
_NL_POST  = re.compile(r"\b[1-9][0-9]{3}\s?[A-Z]{2}\b")
_SOCIAL   = re.compile(
    r"https?://(?:www\.)?"
    r"(?:facebook\.com|instagram\.com|linkedin\.com|twitter\.com|x\.com)"
    r"/[A-Za-z0-9._/-]+",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)

_SKIP_DOMAINS = (
    "duckduckgo", "google", "facebook", "instagram", "linkedin",
    "twitter", "bing", "yahoo", "kvk.nl", "w3.org", "schema.org",
    "mozilla.org", "apple.com", "microsoft.com", "openstreetmap",
    "wikimedia", "wikipedia", "cdn.", "ajax.", "jquery",
)

# HTML signals that suggest a modern, well-maintained site
_MODERN_SIGNALS = re.compile(
    r"viewport|bootstrap|tailwind|react|vue|next\.js|gatsby|webflow|"
    r"elementor|divi|shopify|woocommerce|wp-content/themes/[a-z-]+-2[012][0-9]",
    re.IGNORECASE,
)
# Signals that suggest an old/bad site
_OLD_SIGNALS = re.compile(
    r"table\s+width|<font\s|bgcolor=|frameset|flash|\.swf|"
    r"wp-content/themes/(twentyten|twentyeleven|twentytwelve|twentythirteen|twentyfourteen)|"
    r"copyright\s+20(0[0-9]|1[0-5])",
    re.IGNORECASE,
)
# No viewport meta = not mobile-friendly
_VIEWPORT = re.compile(r'<meta[^>]+name=["\']viewport', re.IGNORECASE)


def _fetch(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
            charset = "utf-8"
            ct = r.headers.get("Content-Type", "")
            for part in ct.split(";"):
                if "charset=" in part:
                    charset = part.split("=", 1)[1].strip()
            return r.read(80_000).decode(charset, errors="replace")
    except Exception as exc:
        logger.debug("bedrijf_research fetch failed for %s: %s", url, exc)
        return ""


def _ddg_snippet(query: str) -> str:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    return _fetch(url, timeout=12)


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _score_website(url: str) -> tuple[str, str]:
    """Fetch the site and return (website_status, website_reden).

    website_status: "geen_site" | "slechte_site" | "goede_site"
    website_reden : Dutch explanation shown to Lars
    """
    html = _fetch(url, timeout=8)
    if not html:
        return "slechte_site", "Site niet bereikbaar of geeft geen antwoord"

    old_hits   = len(_OLD_SIGNALS.findall(html))
    modern_hits = len(_MODERN_SIGNALS.findall(html))
    has_viewport = bool(_VIEWPORT.search(html))

    if not has_viewport:
        return "slechte_site", "Niet mobielvriendelijk (geen viewport meta)"
    if old_hits >= 2 and modern_hits == 0:
        return "slechte_site", f"Verouderd design ({old_hits} oude signalen gevonden)"
    if modern_hits >= 2:
        return "goede_site", f"Moderne site ({modern_hits} moderne signalen)"
    if old_hits >= 1:
        return "slechte_site", "Mogelijk verouderd — controleer zelf"
    return "goede_site", "Site ziet er redelijk modern uit"


def _parse_single_result(html: str) -> dict[str, Any]:
    """Parse one DuckDuckGo HTML result into structured fields."""
    text = _strip_tags(html)
    phones    = _NL_PHONE.findall(text)
    postcodes = _NL_POST.findall(text)
    socials   = _SOCIAL.findall(text)

    website = None
    for url in _URL.findall(html):
        u = url.lower()
        if any(skip in u for skip in _SKIP_DOMAINS):
            continue
        if re.search(r"https?://[a-z0-9.-]+\.[a-z]{2,4}/?$", u):
            website = url.rstrip("/")
            break

    adres = None
    if postcodes:
        idx = text.find(postcodes[0])
        adres = text[max(0, idx - 30):idx + 20].strip()
        adres = re.sub(r"\s+", " ", adres)

    return {
        "telefoon": phones[0] if phones else None,
        "adres":    adres,
        "website":  website,
        "social":   list(dict.fromkeys(socials))[:3],
        "snippet":  text[:500].strip(),
    }


def _merge_results(results: list[dict[str, Any]], queries: list[str]) -> dict[str, Any]:
    """Merge results from multiple swarm queries — prefer non-None fields."""
    merged: dict[str, Any] = {"telefoon": None, "adres": None, "website": None, "social": [], "snippet": ""}
    seen_socials: set[str] = set()
    for r in results:
        for field in ("telefoon", "adres", "website"):
            if merged[field] is None and r.get(field):
                merged[field] = r[field]
        for s in r.get("social", []):
            if s not in seen_socials:
                seen_socials.add(s)
                merged["social"].append(s)
        if not merged["snippet"] and r.get("snippet"):
            merged["snippet"] = r["snippet"]
    merged["social"] = merged["social"][:5]
    merged["bron"] = " | ".join(queries)
    return merged


def research_bedrijf(bedrijfsnaam: str, plaats: str) -> dict[str, Any]:
    """Search the web for real info about a business using parallel swarm queries.

    Runs 3 DuckDuckGo queries in parallel with different angles, merges the
    richest results. This finds phone numbers and websites that a single query
    would miss.

    Returns a dict with keys:
      telefoon       : str | None
      adres          : str | None
      website        : str | None
      website_status : "geen_site" | "slechte_site" | "goede_site"
      website_reden  : str
      social         : list[str]
      snippet        : str
      bron           : str
    """
    # Swarm: 3 parallel queries with different search angles
    queries = [
        f'"{bedrijfsnaam}" "{plaats}"',
        f'{bedrijfsnaam} {plaats} telefoon website',
        f'{bedrijfsnaam} {plaats} contact',
    ]

    from concurrent.futures import ThreadPoolExecutor, as_completed
    raw_results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="research-swarm") as pool:
        futures = {pool.submit(_ddg_snippet, q): q for q in queries}
        for fut in as_completed(futures, timeout=20):
            q = futures[fut]
            try:
                html = fut.result()
                if html:
                    raw_results.append(_parse_single_result(html))
            except Exception as exc:
                logger.debug("research swarm query '%s' failed: %s", q, exc)

    if not raw_results:
        # total fallback: single query
        html = _ddg_snippet(queries[0])
        raw_results = [_parse_single_result(html)] if html else []

    merged = _merge_results(raw_results, queries)

    telefoon  = merged["telefoon"]
    postcodes = []
    adres     = merged["adres"]

    website = merged["website"]

    if website:
        website_status, website_reden = _score_website(website)
    else:
        website_status, website_reden = "geen_site", "Geen website gevonden — ideale kandidaat"

    result: dict[str, Any] = {
        "telefoon":       telefoon,
        "adres":          adres,
        "website":        website,
        "website_status": website_status,
        "website_reden":  website_reden,
        "social":         merged["social"],
        "snippet":        merged["snippet"],
        "bron":           merged["bron"],
        "swarm_queries":  len(raw_results),
    }
    logger.info(
        "bedrijf_research: '%s' %s — website=%s status=%s queries=%d",
        bedrijfsnaam, plaats, website, website_status, len(raw_results),
    )
    return result
