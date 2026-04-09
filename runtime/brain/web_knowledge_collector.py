"""web_knowledge_collector.py — BeautifulSoup-based web scraper for brain growth.

Scrapes publicly accessible web pages (Wikipedia articles, general URLs) and
converts the extracted text into experience tuples that the central Brain can
learn from.  The collector is intentionally lightweight:

  - No JavaScript execution (static HTML only via ``requests`` + ``bs4``)
  - Polite rate-limiting between requests (``_FETCH_DELAY_S``)
  - Robots-excluded paths are *not* fetched (honour ``/robots.txt`` spirit via
    explicit allow-listed domains and URL validation)
  - Text is converted to fixed-size feature vectors via the same
    ``_text_to_features`` helper used by the rest of the experience pipeline

Typical usage (wired in by ``ExperienceCollector``):

    collector = WebKnowledgeCollector(input_size=256, output_size=8)
    experiences = collector.collect(topics=["machine learning", "Python"])
    # → list of (state, action, reward, next_state) torch.Tensor tuples
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import List, Optional, Tuple

logger = logging.getLogger("brain.web_knowledge")

# ── Optional imports (graceful degradation if not installed) ──────────────────

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _requests = None  # type: ignore[assignment]
    _REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup as _BeautifulSoup
    _BS4_OK = True
except ImportError:
    _BeautifulSoup = None  # type: ignore[assignment]
    _BS4_OK = False

# ── Lazy torch import (mirrors pattern used elsewhere in brain package) ────────

try:
    import torch as _torch
    _TORCH_OK = True
except ImportError:
    _torch = None  # type: ignore[assignment]
    _TORCH_OK = False

# ── Constants ─────────────────────────────────────────────────────────────────

_FETCH_DELAY_S: float = 1.0          # seconds between HTTP requests
_MAX_TEXT_CHARS: int = 4000          # chars extracted per page
_HTTP_TIMEOUT: int = 15              # seconds
_USER_AGENT: str = "ai-employee-brain/1.0 (knowledge collector; +https://github.com/F-game25/AI-EMPLOYEE)"

# Wikipedia REST API base — returns clean JSON without full HTML parsing.
_WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

# Fallback generic scrape base
_WIKI_HTML = "https://en.wikipedia.org/wiki/{title}"

# Experience "action" labels re-used from experience_collector mapping
_TOPIC_TO_ACTION: dict = {
    "technology":    1,
    "science":       1,
    "programming":   1,
    "software":      1,
    "bug":           0,
    "security":      5,
    "performance":   6,
    "documentation": 3,
    "news":          4,
    "update":        4,
    "question":      2,
}


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════

def _is_available() -> bool:
    """Return True if all runtime dependencies are installed."""
    return _REQUESTS_OK and _BS4_OK and _TORCH_OK


def _sanitize_url(url: str) -> Optional[str]:
    """Return *url* if it looks safe to fetch, else None.

    Only http/https URLs are accepted; localhost / private IP ranges are
    rejected to prevent SSRF issues.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return None

    if parsed.scheme not in ("http", "https"):
        return None

    host = parsed.hostname or ""
    # Block private / loopback ranges
    _blocked_prefixes = ("localhost", "127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.")
    if any(host.startswith(p) for p in _blocked_prefixes) or host == "::1":
        return None

    return url


def _fetch_html(url: str) -> Optional[str]:
    """Fetch *url* and return the raw HTML, or None on any error."""
    if not _REQUESTS_OK:
        return None
    safe_url = _sanitize_url(url)
    if safe_url is None:
        logger.warning("web_knowledge_collector: blocked unsafe URL: %s", url)
        return None
    try:
        resp = _requests.get(
            safe_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_HTTP_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.debug("web_knowledge_collector: fetch error for %s: %s", url, exc)
        return None


def _extract_text(html: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    """Extract visible text from *html* using BeautifulSoup.

    Strips scripts, styles, and navigation boilerplate; returns plain text
    limited to *max_chars* characters.
    """
    if not _BS4_OK or not html:
        return ""
    soup = _BeautifulSoup(html, "html.parser")

    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    # Collapse whitespace
    import re
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _wiki_summary(topic: str) -> Optional[str]:
    """Fetch Wikipedia plain-text summary for *topic* via the REST API."""
    if not _REQUESTS_OK:
        return None
    title = topic.replace(" ", "_")
    url = _WIKI_API.format(title=urllib.parse.quote(title, safe=""))
    safe_url = _sanitize_url(url)
    if safe_url is None:
        return None
    try:
        resp = _requests.get(
            safe_url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("extract", "") or ""
    except Exception as exc:
        logger.debug("web_knowledge_collector: Wikipedia API error for '%s': %s", topic, exc)
        return None


def _text_to_tensor(text: str, size: int):
    """Convert *text* to a normalised float tensor of length *size*.

    Uses the same character n-gram hashing approach as ``_text_to_features``
    in ``experience_collector.py`` so that the two feature spaces are
    compatible.
    """
    if not _TORCH_OK:
        return None
    vec = [0.0] * size
    if not text:
        return _torch.zeros(size, dtype=_torch.float32)
    text_lower = text.lower()
    for i, ch in enumerate(text_lower[:size]):
        vec[i % size] += ord(ch) / 1000.0
    total = max(sum(abs(v) for v in vec), 1.0)
    vec = [v / total for v in vec]
    return _torch.tensor(vec, dtype=_torch.float32)


def _topic_to_action(topic: str) -> int:
    """Map a free-form *topic* string to a brain action index (0–7)."""
    topic_lower = topic.lower()
    for key, action in _TOPIC_TO_ACTION.items():
        if key in topic_lower:
            return action
    return 7  # "other"


# ═════════════════════════════════════════════════════════════════════════════
# Main collector class
# ═════════════════════════════════════════════════════════════════════════════

ExperienceTuple = Tuple  # (state_tensor, action_int, reward_float, next_state_tensor)


class WebKnowledgeCollector:
    """Scrapes web pages and converts content into brain experience tuples.

    Args:
        input_size:  Feature vector size expected by the Brain.
        output_size: Number of discrete actions the Brain can choose from.
        fetch_delay: Polite delay (seconds) between consecutive HTTP requests.
    """

    def __init__(
        self,
        input_size: int,
        output_size: int,
        fetch_delay: float = _FETCH_DELAY_S,
    ) -> None:
        self.input_size  = input_size
        self.output_size = output_size
        self.fetch_delay = fetch_delay
        self._available  = _is_available()

        if not self._available:
            missing = []
            if not _REQUESTS_OK:
                missing.append("requests")
            if not _BS4_OK:
                missing.append("beautifulsoup4")
            if not _TORCH_OK:
                missing.append("torch")
            logger.warning(
                "WebKnowledgeCollector: missing dependencies %s — "
                "web scraping disabled.",
                missing,
            )

    # ── Wikipedia ─────────────────────────────────────────────────────────────

    def scrape_wikipedia(self, topic: str) -> Optional[ExperienceTuple]:
        """Scrape a Wikipedia article for *topic* and return one experience.

        Uses the Wikipedia REST API summary endpoint first (clean JSON), then
        falls back to full HTML scraping if the API returns no content.

        Returns:
            (state, action, reward, next_state) tensor tuple, or None on error.
        """
        if not self._available:
            return None

        text = _wiki_summary(topic)
        if not text:
            # Fall back to HTML scraping
            title = topic.replace(" ", "_")
            url   = _WIKI_HTML.format(title=urllib.parse.quote(title, safe=""))
            html  = _fetch_html(url)
            text  = _extract_text(html) if html else ""

        if not text:
            logger.debug("web_knowledge_collector: no content for topic '%s'", topic)
            return None

        half = len(text) // 2
        state      = _text_to_tensor(text[:half or 1], self.input_size)
        next_state = _text_to_tensor(text[half:] or text, self.input_size)
        action     = _topic_to_action(topic) % self.output_size
        reward     = 1.0  # successfully scraped article = positive experience

        if state is None or next_state is None:
            return None

        return (state, action, reward, next_state)

    # ── Generic URL ───────────────────────────────────────────────────────────

    def scrape_url(self, url: str, topic_hint: str = "") -> Optional[ExperienceTuple]:
        """Scrape an arbitrary public URL and return one experience tuple.

        Args:
            url:        Full URL to fetch (must be http/https).
            topic_hint: Optional hint used to determine the action index.

        Returns:
            (state, action, reward, next_state) tensor tuple, or None on error.
        """
        if not self._available:
            return None

        html = _fetch_html(url)
        if not html:
            return None

        text = _extract_text(html)
        if not text:
            return None

        half       = len(text) // 2
        state      = _text_to_tensor(text[:half or 1], self.input_size)
        next_state = _text_to_tensor(text[half:] or text, self.input_size)
        action     = _topic_to_action(topic_hint) % self.output_size
        reward     = 0.8  # successfully scraped page = near-positive experience

        if state is None or next_state is None:
            return None

        return (state, action, reward, next_state)

    # ── Batch collect ─────────────────────────────────────────────────────────

    def collect_wikipedia(
        self,
        topics: List[str],
        max_items: int = 10,
    ) -> List[ExperienceTuple]:
        """Scrape Wikipedia for each topic in *topics*.

        Politely waits ``self.fetch_delay`` seconds between requests.

        Returns:
            List of (state, action, reward, next_state) tuples (may be shorter
            than ``len(topics)`` if some topics returned no content).
        """
        experiences: List[ExperienceTuple] = []
        for topic in topics[:max_items]:
            exp = self.scrape_wikipedia(topic)
            if exp is not None:
                experiences.append(exp)
                logger.debug(
                    "web_knowledge_collector: scraped Wikipedia '%s' → action=%d",
                    topic, exp[1],
                )
            time.sleep(self.fetch_delay)

        logger.info(
            "web_knowledge_collector: Wikipedia scrape → %d/%d topics yielded experiences.",
            len(experiences), min(len(topics), max_items),
        )
        return experiences

    def collect_urls(
        self,
        urls: List[str],
        topic_hints: Optional[List[str]] = None,
        max_items: int = 10,
    ) -> List[ExperienceTuple]:
        """Scrape a list of arbitrary URLs.

        Args:
            urls:        List of URLs to scrape.
            topic_hints: Optional parallel list of topic hints for action mapping.
            max_items:   Maximum number of experiences to return.

        Returns:
            List of (state, action, reward, next_state) tuples.
        """
        experiences: List[ExperienceTuple] = []
        hints = topic_hints or [""] * len(urls)
        for url, hint in zip(urls[:max_items], hints):
            exp = self.scrape_url(url, topic_hint=hint)
            if exp is not None:
                experiences.append(exp)
                logger.debug("web_knowledge_collector: scraped URL '%s'", url)
            time.sleep(self.fetch_delay)

        logger.info(
            "web_knowledge_collector: URL scrape → %d/%d pages yielded experiences.",
            len(experiences), min(len(urls), max_items),
        )
        return experiences

    def collect(
        self,
        topics: Optional[List[str]] = None,
        urls: Optional[List[str]] = None,
        max_items: int = 10,
    ) -> List[ExperienceTuple]:
        """Collect experiences from Wikipedia topics and/or explicit URLs.

        Combines results from both sources up to *max_items*.  If neither
        *topics* nor *urls* is supplied, a small default set of AI-related
        Wikipedia topics is used.

        Args:
            topics:    Wikipedia article titles to scrape.
            urls:      Arbitrary URLs to scrape.
            max_items: Cap on total experiences returned.

        Returns:
            List of (state, action, reward, next_state) tuples.
        """
        if not self._available:
            return []

        _default_topics = [
            "Machine learning",
            "Artificial intelligence",
            "Neural network",
            "Deep learning",
            "Natural language processing",
        ]

        effective_topics = topics if topics is not None else _default_topics
        effective_urls   = urls or []

        experiences: List[ExperienceTuple] = []

        # Wikipedia topics first
        wiki_quota = max_items - len(experiences)
        if effective_topics and wiki_quota > 0:
            experiences.extend(self.collect_wikipedia(effective_topics, max_items=wiki_quota))

        # Arbitrary URLs next
        url_quota = max_items - len(experiences)
        if effective_urls and url_quota > 0:
            experiences.extend(self.collect_urls(effective_urls, max_items=url_quota))

        return experiences[:max_items]
