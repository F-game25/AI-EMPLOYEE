"""Product Research engine — real web search, no fabricated scores.

Searches DuckDuckGo for supplier/pricing/margin data per product, then uses the
local Ollama model to score each product on demand, marge, and concurrentie.
If search fails, returns an empty list with an error note — never fabricated data.

Usage
-----
    from core.product_researcher import research_products
    result = research_products("fitness accessoires", "nl", 30)
    # result: {"ok": True, "producten": [...], "niche": ..., "timestamp": ...}
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:latest")
_AI_HOME      = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_STORE_FILE   = _AI_HOME / "state" / "product_research.json"
_MAX_ENTRIES  = 200

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl,en;q=0.9",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
            return r.read(60_000).decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug("product_researcher fetch failed %s: %s", url, exc)
        return ""


def _ddg_search(query: str) -> str:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    html = _fetch(url, timeout=14)
    if "anomaly" in html.lower():
        return ""
    # Strip HTML tags to plain text
    text = re.sub(r"<[^>]+>", " ", html)
    # Condense whitespace
    return re.sub(r"\s{2,}", " ", text)[:3000].strip()


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    """Call local Ollama — returns empty string on any failure."""
    payload = {
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "system": system or (
            "Je bent een e-commerce product analist. Geef alleen JSON terug, geen uitleg."
        ),
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    try:
        req = urllib.request.Request(
            f"{_OLLAMA_HOST}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310
            body = json.loads(resp.read())
        return body.get("response", "").strip()
    except Exception as exc:
        logger.warning("product_researcher LLM call failed: %s", exc)
        return ""


# ── Niche discovery ────────────────────────────────────────────────────────────

def _discover_products(niche: str, markt: str) -> list[str]:
    """Run a single DuckDuckGo query to discover top products in the niche.

    Returns up to 8 product name strings.  Falls back to empty list.
    """
    q = f"top producten {niche} dropshipping {markt} 2025 bestseller"
    raw = _ddg_search(q)
    if not raw:
        return []

    prompt = (
        f"Gebaseerd op deze zoekresultaten voor de niche '{niche}', geef me een JSON-array "
        f"met maximaal 8 specifieke productnamen (strings), geen categorieën. "
        f"Alleen de JSON-array, geen andere tekst.\n\n{raw[:2000]}"
    )
    llm_out = _llm(prompt, max_tokens=200)

    # Extract JSON array from LLM output
    m = re.search(r"\[.*?\]", llm_out, re.DOTALL)
    if not m:
        return []
    try:
        products = json.loads(m.group(0))
        return [str(p).strip() for p in products if isinstance(p, str) and p.strip()][:8]
    except json.JSONDecodeError:
        return []


# ── Per-product research ───────────────────────────────────────────────────────

def _research_one_product(product: str, niche: str, markt: str) -> dict[str, Any] | None:
    """Run 2 parallel DuckDuckGo queries for one product and score it via LLM.

    Returns a scored product dict or None if insufficient data.
    """
    queries = [
        f"{product} dropshipping supplier prijs 2025",
        f"{product} verkopen online marge winst {markt}",
    ]

    snippets: list[str] = []
    sources: list[str] = []

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="prod-swarm") as pool:
        futures = {pool.submit(_ddg_search, q): q for q in queries}
        for fut in as_completed(futures, timeout=25):
            q = futures[fut]
            try:
                text = fut.result()
                if text:
                    snippets.append(text[:1200])
                    sources.append(q)
            except Exception as exc:
                logger.debug("product swarm query '%s' failed: %s", q, exc)

    if not snippets:
        return None

    combined = "\n---\n".join(snippets)

    prompt = (
        f"Analyseer de volgende zoekresultaten voor het product '{product}' in niche '{niche}'.\n"
        f"Geef een JSON-object met EXACT deze velden (gebruik alleen echte data uit de tekst, "
        f"GEEN verzonnen cijfers; als je het niet weet zet je 0):\n"
        f'{{"demand": <0-10 float>, "marge": <0-10 float>, "concurrentie": <0-10 float>, '
        f'"aankoopprijs_est": <float EUR>, "verkoopprijs_est": <float EUR>, '
        f'"opmerking": "<max 80 chars Dutch>"}}\n\n'
        f"Data:\n{combined[:3000]}"
    )
    llm_out = _llm(prompt, max_tokens=300)

    m = re.search(r"\{.*?\}", llm_out, re.DOTALL)
    if not m:
        return None
    try:
        scores = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    def _float(key: str, default: float = 0.0) -> float:
        try:
            return float(scores.get(key, default))
        except (TypeError, ValueError):
            return default

    aankoop = _float("aankoopprijs_est")
    verkoop = _float("verkoopprijs_est")
    marge_pct = round((verkoop - aankoop) / verkoop * 100, 1) if verkoop > 0 else 0.0

    return {
        "naam": product,
        "demand": round(min(10.0, max(0.0, _float("demand"))), 2),
        "marge": round(min(10.0, max(0.0, _float("marge"))), 2),
        "concurrentie": round(min(10.0, max(0.0, _float("concurrentie"))), 2),
        "aankoopprijs_est": round(aankoop, 2),
        "verkoopprijs_est": round(verkoop, 2),
        "marge_pct": marge_pct,
        "bronnen": sources,
        "opmerking": str(scores.get("opmerking", ""))[:120],
    }


# ── Persistence ────────────────────────────────────────────────────────────────

def _save_result(result: dict[str, Any]) -> None:
    """Append result to product_research.json (max _MAX_ENTRIES, newest first)."""
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        from core.file_lock import FileLock
        _lock_cls = FileLock
    except ImportError:
        _lock_cls = None

    def _write() -> None:
        existing: list[dict] = []
        if _STORE_FILE.exists():
            try:
                existing = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        entries = [result] + existing
        entries = entries[:_MAX_ENTRIES]
        # Atomic write: write to .tmp then rename
        tmp = _STORE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_STORE_FILE)

    if _lock_cls:
        try:
            with _lock_cls(_STORE_FILE):
                _write()
            return
        except Exception:
            pass
    _write()


# ── Public API ─────────────────────────────────────────────────────────────────

def research_products(niche: str, markt: str = "nl", min_marge: int = 30) -> dict[str, Any]:
    """Research products in a niche and return a scored shortlist.

    Parameters
    ----------
    niche     : Product category to research (e.g. "fitness accessoires").
    markt     : Market/locale string used in search queries (default: "nl").
    min_marge : Minimum margin % threshold — only informational (filter on caller side).

    Returns
    -------
    dict with keys: ok, producten, niche, timestamp.
    Never returns fabricated scores — missing data results in empty list with note.
    """
    timestamp = _now_iso()

    # Step 1: discover product names
    product_names = _discover_products(niche, markt)
    if not product_names:
        result: dict[str, Any] = {
            "ok": False,
            "producten": [],
            "niche": niche,
            "timestamp": timestamp,
            "opmerking": "Geen producten gevonden via web search — controleer niche spelling of probeer later.",
        }
        _save_result(result)
        return result

    # Step 2: research each product in parallel (max 6 to keep latency reasonable)
    scored: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="prod-research") as pool:
        futures = {pool.submit(_research_one_product, p, niche, markt): p for p in product_names[:6]}
        for fut in as_completed(futures, timeout=120):
            p = futures[fut]
            try:
                item = fut.result()
                if item is not None:
                    scored.append(item)
            except Exception as exc:
                logger.warning("product research failed for '%s': %s", p, exc)

    # Step 3: sort by (demand + marge - concurrentie / 2) descending
    scored.sort(key=lambda x: x["demand"] + x["marge"] - x["concurrentie"] / 2, reverse=True)

    result = {
        "ok": True,
        "producten": scored,
        "niche": niche,
        "timestamp": timestamp,
    }
    if not scored:
        result["ok"] = False
        result["opmerking"] = "Web search werkte maar LLM kon geen scores extraheren uit de resultaten."

    _save_result(result)
    return result


# ── CLI entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    niche_arg = sys.argv[1] if len(sys.argv) > 1 else "fitness accessoires"
    markt_arg = sys.argv[2] if len(sys.argv) > 2 else "nl"
    marge_arg = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    out = research_products(niche_arg, markt_arg, marge_arg)
    print(json.dumps(out, ensure_ascii=False))
