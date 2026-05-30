"""Bedrijf Research — haal echte info op over een bedrijf via DuckDuckGo.

Geen verzonnen gegevens: velden die niet gevonden worden staan op None.
Lars beslist zelf wat hij aanvult.
"""
from __future__ import annotations

import json
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
_URL      = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)


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
    """Fetch the DuckDuckGo HTML results page and return the visible text."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    return _fetch(url, timeout=12)


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def research_bedrijf(bedrijfsnaam: str, plaats: str) -> dict[str, Any]:
    """Search the web for real info about a business.

    Returns a dict with keys:
      telefoon  : str | None  — first NL phone number found
      adres     : str | None  — first postcode+city snippet found
      website   : str | None  — most likely official website URL
      social    : list[str]   — social media profile URLs found
      snippet   : str         — raw text snippet (first 500 chars)
      bron      : str         — search query used
    """
    query = f'"{bedrijfsnaam}" "{plaats}"'
    html  = _ddg_snippet(query)
    text  = _strip_tags(html)

    phones   = _NL_PHONE.findall(text)
    postcodes = _NL_POST.findall(text)
    socials  = _SOCIAL.findall(text)

    # Best-guess website: non-DDG, non-social, non-infrastructure URL in results
    _SKIP_DOMAINS = (
        "duckduckgo", "google", "facebook", "instagram", "linkedin",
        "twitter", "bing", "yahoo", "kvk.nl", "w3.org", "schema.org",
        "mozilla.org", "apple.com", "microsoft.com", "openstreetmap",
        "wikimedia", "wikipedia", "cdn.", "ajax.", "jquery",
    )
    website = None
    for url in _URL.findall(html):
        u = url.lower()
        if any(skip in u for skip in _SKIP_DOMAINS):
            continue
        # Must look like a real business site (ends at TLD, not a deep path to a resource)
        if re.search(r"https?://[a-z0-9.-]+\.[a-z]{2,4}/?$", u):
            website = url.rstrip("/")
            break

    adres = None
    if postcodes:
        # Try to extract a short address string around the postcode
        idx = text.find(postcodes[0])
        adres = text[max(0, idx-30):idx+20].strip()
        adres = re.sub(r"\s+", " ", adres)

    result: dict[str, Any] = {
        "telefoon": phones[0] if phones else None,
        "adres":    adres if adres else None,
        "website":  website,
        "social":   list(dict.fromkeys(socials))[:3],  # deduplicate, max 3
        "snippet":  text[:500].strip(),
        "bron":     query,
    }
    logger.info(
        "bedrijf_research: '%s' %s — telefoon=%s website=%s",
        bedrijfsnaam, plaats, result["telefoon"], result["website"],
    )
    return result
