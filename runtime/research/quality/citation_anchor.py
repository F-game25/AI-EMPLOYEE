"""Citation anchoring — bind report claims to the report's OWN source list.

Splits each section's content into claim-sized statements (sentence
heuristics) and anchors every claim to the sources the report actually
collected, via inline URL/domain mentions or keyword overlap. A claim with
no plausible source is returned with ``anchored: False``.

Fully deterministic: no LLM, no network. Thresholds are env-tunable.
Also hosts the shared text/URL primitives used by the rest of the
quality package (single source of truth, no duplication).
"""
from __future__ import annotations

import os
import re
import urllib.parse as _up

# ── Tunables (read at call time so tests/ops can override via env) ──────────

def _min_claim_chars() -> int:
    return int(os.getenv("RESEARCH_ANCHOR_MIN_CLAIM_CHARS", "30"))


def _min_overlap_tokens() -> int:
    return int(os.getenv("RESEARCH_ANCHOR_MIN_OVERLAP", "2"))


def _min_overlap_ratio() -> float:
    return float(os.getenv("RESEARCH_ANCHOR_MIN_RATIO", "0.15"))


# ── Shared primitives ────────────────────────────────────────────────────────

_STOPWORDS = frozenset(
    "the a an and or but of to in on for with by from as at is are was were "
    "be been being this that these those it its which what how why when who "
    "whom will would can could may might shall should has have had not no "
    "nor more most other some such than then also into over under between "
    "about after before during while where there their they them his her "
    "our your you we he she i do does did done if else each both all any "
    "few many much very own same so too only just per via".split()
)

URL_RE = re.compile(r"https?://[^\s\)\]\}>\"']+", re.IGNORECASE)
BRACKET_DOMAIN_RE = re.compile(r"\[([a-z0-9][a-z0-9.\-]*\.[a-z]{2,})\]", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


def normalize_url(url: str) -> str:
    """Canonical form for URL comparison: trim, strip trailing punctuation,
    lowercase scheme/host, drop www., trailing slash, and fragment."""
    u = (url or "").strip().rstrip(".,;:!?")
    try:
        p = _up.urlsplit(u)
    except ValueError:
        return u.lower()
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "").rstrip("/")
    query = f"?{p.query}" if p.query else ""
    return f"{p.scheme.lower()}://{host}{path}{query}"


def url_domain(url: str) -> str:
    """Host of a URL, lowercased, without a leading www."""
    try:
        host = (_up.urlsplit((url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def domains_related(a: str, b: str) -> bool:
    """True when one domain equals or is a subdomain of the other."""
    a, b = a.lower().lstrip("."), b.lower().lstrip(".")
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def extract_inline_urls(text: str) -> list[str]:
    """All http(s) URLs appearing literally in text (raw, un-normalized)."""
    return [m.group(0).rstrip(".,;:!?") for m in URL_RE.finditer(text or "")]


def extract_bracket_domains(text: str) -> list[str]:
    """Domains cited in the engine's ``[domain.tld]`` inline notation."""
    return [m.group(1).lower() for m in BRACKET_DOMAIN_RE.finditer(text or "")]


def tokenize(text: str) -> set[str]:
    """Lowercase keyword tokens (len>=3) minus stopwords."""
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS}


def split_claims(text: str) -> list[str]:
    """Split prose into claim-sized statements via sentence heuristics."""
    min_chars = _min_claim_chars()
    out = []
    for para in (text or "").splitlines():
        para = para.strip().lstrip("-•* ").strip()
        if not para:
            continue
        for sent in _SENTENCE_SPLIT_RE.split(para):
            sent = sent.strip()
            if len(sent) >= min_chars:
                out.append(sent)
    return out


def get_source_list(report: dict) -> list[dict]:
    """The report's OWN source list. DeepResearchReport persists it as
    ``citations`` ([{url,title,sub_question}]); tolerate a ``sources`` key."""
    raw = report.get("citations") or report.get("sources") or []
    out = []
    for s in raw:
        if isinstance(s, dict) and s.get("url"):
            out.append(s)
        elif isinstance(s, str) and s.strip():
            out.append({"url": s.strip()})
    return out


# ── Anchoring ────────────────────────────────────────────────────────────────

def _index_sources(sources: list[dict]) -> list[dict]:
    idx = []
    for s in sources:
        url = s.get("url", "")
        path_words = re.sub(r"[/_\-.+%]", " ", _up.urlsplit(url).path)
        idx.append({
            "url": url,
            "norm": normalize_url(url),
            "domain": url_domain(url),
            "tokens": tokenize(" ".join((
                s.get("title", ""), s.get("sub_question", ""),
                s.get("snippet", ""), path_words,
            ))),
        })
    return idx


def anchor_claims(report: dict) -> dict:
    """Anchor every claim in the report's sections to its own source list.

    Returns ``{claims: [{id, text, section, source_urls, anchored}],
    total, anchored, anchored_ratio}``. Deterministic.
    """
    src_index = _index_sources(get_source_list(report))
    min_overlap, min_ratio = _min_overlap_tokens(), _min_overlap_ratio()

    claims: list[dict] = []
    for section in report.get("sections") or []:
        title = section.get("title", "")
        for sent in split_claims(section.get("content", "")):
            inline_norms = {normalize_url(u) for u in extract_inline_urls(sent)}
            bracket_domains = extract_bracket_domains(sent)
            claim_tokens = tokenize(sent)

            matched: list[str] = []
            for src in src_index:
                if src["norm"] in inline_norms or any(
                    domains_related(d, src["domain"]) for d in bracket_domains
                ):
                    matched.append(src["url"])
                    continue
                overlap = claim_tokens & src["tokens"]
                if (len(overlap) >= min_overlap
                        and len(overlap) / max(1, len(claim_tokens)) >= min_ratio):
                    matched.append(src["url"])

            claims.append({
                "id": f"c{len(claims) + 1:04d}",
                "text": sent,
                "section": title,
                "source_urls": matched,
                "anchored": bool(matched),
            })

    anchored = sum(1 for c in claims if c["anchored"])
    return {
        "claims": claims,
        "total": len(claims),
        "anchored": anchored,
        "anchored_ratio": round(anchored / len(claims), 3) if claims else 0.0,
    }
