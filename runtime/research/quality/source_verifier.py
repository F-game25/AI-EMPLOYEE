"""Source verification — syntactic always, live HTTP only when opted in.

For each source URL in the report's own list:
  - syntactic validation (always, offline, deterministic)
  - live reachability check (HEAD, GET fallback) ONLY when
    ``RESEARCH_VERIFY_LIVE=1`` — default OFF so tests are offline-deterministic.
    Live checks are SSRF-guarded via ``core.url_guard.validate_url`` and
    capped (count + timeout, both env-tunable).

Statuses are honest: with live checks off, a syntactically valid URL is
reported as ``unchecked`` — never claimed as verified.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse as _up

from research.quality.citation_anchor import get_source_list, normalize_url, tokenize

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _live_enabled() -> bool:
    return os.getenv("RESEARCH_VERIFY_LIVE", "0").strip() == "1"


def _live_timeout_s() -> float:
    return float(os.getenv("RESEARCH_VERIFY_TIMEOUT_S", "5"))


def _live_max_sources() -> int:
    return int(os.getenv("RESEARCH_VERIFY_MAX_SOURCES", "10"))


# ── Checks ───────────────────────────────────────────────────────────────────

def _syntactic_error(url: str) -> str | None:
    """Offline structural validation. Returns reason string or None when ok."""
    if not url or not isinstance(url, str):
        return "empty or non-string URL"
    try:
        p = _up.urlsplit(url.strip())
    except ValueError as e:
        return f"unparseable URL: {e}"
    if p.scheme not in ("http", "https"):
        return f"scheme '{p.scheme}' not allowed (http/https only)"
    if not p.hostname or "." not in p.hostname:
        return "missing or implausible hostname"
    return None


def _live_check(url: str, expected_title: str, timeout: float) -> dict:
    """HEAD (GET fallback) with SSRF guard. Returns partial source record."""
    try:
        from core.url_guard import validate_url
        guard_err = validate_url(url)
    except Exception as e:  # guard import/availability failure → don't fetch
        guard_err = f"url_guard unavailable: {e}"
    if guard_err is not None:
        return {"status": "unreachable", "reason": guard_err}

    import urllib.error
    import urllib.request
    headers = {"User-Agent": "AI-EMPLOYEE-ResearchQuality/1.0", "Accept": "text/html,*/*"}

    def _request(method: str):
        req = urllib.request.Request(url, headers=headers, method=method)
        return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — guarded above

    try:
        try:
            resp = _request("HEAD")
        except urllib.error.HTTPError as he:
            if he.code in (405, 501):  # HEAD unsupported → retry with GET
                resp = _request("GET")
            else:
                return {"status": "unreachable", "http_status": he.code,
                        "reason": f"HTTP {he.code}"}
        with resp:
            status = getattr(resp, "status", None) or resp.getcode()
            out: dict = {"status": "verified", "http_status": int(status)}
            if expected_title:
                body = b""
                try:
                    body = resp.read(8192)
                except Exception:
                    pass
                if not body:  # HEAD has no body → small GET just for the title
                    try:
                        with _request("GET") as g:
                            body = g.read(8192)
                    except Exception:
                        body = b""
                m = _TITLE_RE.search(body.decode("utf-8", errors="ignore"))
                if m:
                    page_tokens = tokenize(m.group(1))
                    out["title_match"] = bool(page_tokens & tokenize(expected_title))
            return out
    except Exception as e:
        return {"status": "unreachable", "reason": str(e)[:200]}


# ── Public API ───────────────────────────────────────────────────────────────

def verify_sources(report: dict) -> dict:
    """Verify the report's source list.

    Returns ``{sources: [{url, status, http_status?, title_match?, reason?}],
    summary: {total, verified, unreachable, malformed, unchecked, live_checked}}``.
    Statuses: ``verified | unreachable | malformed | unchecked``.
    """
    live = _live_enabled()
    timeout, budget = _live_timeout_s(), _live_max_sources()

    results: list[dict] = []
    seen: set[str] = set()
    live_used = 0

    for src in get_source_list(report):
        url = src.get("url", "")
        norm = normalize_url(url)
        if norm in seen:
            continue
        seen.add(norm)

        record: dict = {"url": url}
        syn_err = _syntactic_error(url)
        if syn_err:
            record.update(status="malformed", reason=syn_err)
        elif not live:
            record["status"] = "unchecked"
        elif live_used >= budget:
            record.update(status="unchecked", reason="live verification budget exhausted")
        else:
            live_used += 1
            record.update(_live_check(url, src.get("title", ""), timeout))
        results.append(record)

    counts = {s: 0 for s in ("verified", "unreachable", "malformed", "unchecked")}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "sources": results,
        "summary": {"total": len(results), **counts, "live_checked": live},
    }
