"""Autonomous research agent.

Given knowledge gaps, runs ``search_web → CloakBrowser.fetch_url → LLM summarize``
in parallel for the top sources, then persists every finding to all three
memory layers: vector store (via :class:`MemoryRouter`), Neo4j brain graph,
and the durable ``knowledge_store.json``. Optionally writes screenshots to
disk for auditability.

Adaptive depth: hop 0 → 3 sources, hop 1 → 6, hop 2 → 10. The caller
(``AgentController``) loops up to ``max_hops`` until context sufficiency is met.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from core.source_trust import trust_for_url

try:
    from memory.verification import get_engine as _get_verification_engine
    from memory.pending_queue import add as _pending_queue_add
    _VERIFY_AVAILABLE = True
except Exception:  # pragma: no cover
    _VERIFY_AVAILABLE = False
    _get_verification_engine = None  # type: ignore
    _pending_queue_add = None  # type: ignore


def _classify_source_type(url: str) -> str:
    u = (url or "").lower()
    if any(d in u for d in ("arxiv.org", "scholar.google", ".edu/", "doi.org")): return "academic"
    if any(d in u for d in ("github.com", "gitlab.com", "stackoverflow", "docs.")): return "docs"
    if any(d in u for d in ("reddit.com", "forum", "discourse", "hackernews")): return "forum"
    if any(d in u for d in ("twitter.com", "x.com", "facebook.com", "linkedin.com", "instagram")): return "social"
    if any(d in u for d in ("news", "nytimes", "bbc", "reuters", "theguardian", "cnn")): return "news"
    return "web"

logger = logging.getLogger(__name__)

_DEFAULT_BUDGET = int(os.getenv("RESEARCH_MAX_PAGES_PER_DAY", "200"))
_DEPTH_PLAN = {0: 3, 1: 6, 2: 10}
_SCREENSHOT_DIR = Path(__file__).resolve().parents[2] / "state" / "research_screenshots"
_BUDGET_FILE = Path(__file__).resolve().parents[2] / "state" / "research_budget.json"

# Ensure runtime/ on sys.path for sibling imports (search_web, cloak fetcher)
_RUNTIME_ROOT = str(Path(__file__).resolve().parents[1])
if _RUNTIME_ROOT not in sys.path:
    sys.path.insert(0, _RUNTIME_ROOT)


# ── lazy imports for optional/heavy deps ─────────────────────────────────
def _import_search_web() -> Callable[..., list]:
    """Lazy-import to avoid hard dependency on the agents path at module load."""
    agents_router = Path(__file__).resolve().parents[1] / "agents" / "ai-router"
    if str(agents_router) not in sys.path:
        sys.path.insert(0, str(agents_router))
    from ai_router import search_web  # type: ignore
    return search_web


def _import_cloak_fetch() -> Callable[[str], Any]:
    try:
        from infra.rpa.cloak_browser import fetch_url  # type: ignore
        return fetch_url
    except Exception as e:
        logger.warning("CloakBrowser not available (%s); falling back to plain HTTP", e)
        return _http_fallback_fetch


async def _http_fallback_fetch(url: str) -> dict:
    """Minimal fallback when Playwright isn't installed."""
    from core.url_guard import require_safe_url, UnsafeURLError  # type: ignore
    try:
        require_safe_url(url)
    except UnsafeURLError as _e:
        return {"url": url, "final_url": url, "title": "", "text": "",
                "screenshot_b64": None, "error": f"SSRF blocked: {_e}"}
    try:
        import urllib.request
        loop = asyncio.get_event_loop()
        def _do() -> dict:
            req = urllib.request.Request(url, headers={"User-Agent": "AIEmployee/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read(200_000).decode("utf-8", errors="ignore")
            return {"url": url, "final_url": url, "title": "", "text": body, "screenshot_b64": None}
        return await loop.run_in_executor(None, _do)
    except Exception as e:
        return {"url": url, "final_url": url, "title": "", "text": "", "screenshot_b64": None, "error": str(e)}


# ── budget tracking (per-day, on-disk) ───────────────────────────────────
def _load_budget() -> dict:
    try:
        return json.loads(_BUDGET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_budget(b: dict) -> None:
    try:
        _BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BUDGET_FILE.write_text(json.dumps(b), encoding="utf-8")
    except Exception:
        pass


def _today_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def budget_remaining() -> int:
    state = _load_budget()
    used = int(state.get(_today_key(), 0))
    return max(0, _DEFAULT_BUDGET - used)


def _budget_consume(n: int) -> None:
    state = _load_budget()
    key = _today_key()
    state[key] = int(state.get(key, 0)) + int(n)
    # Trim old days
    state = {k: v for k, v in state.items() if k >= _today_key()[:-2] + "01"}
    _save_budget(state)


# ── main agent ───────────────────────────────────────────────────────────
class AutoResearchAgent:
    """Web research + persistence to vector + graph + durable knowledge store."""

    def __init__(
        self,
        memory_router: Any,
        brain_graph: Optional[Any] = None,
        knowledge_store: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        *,
        search_fn: Optional[Callable[..., list]] = None,
        fetch_fn: Optional[Callable[[str], Any]] = None,
        broadcaster: Optional[Callable[[str, dict], None]] = None,
        save_screenshots: bool = True,
    ) -> None:
        self._memory = memory_router
        self._graph = brain_graph
        self._knowledge = knowledge_store
        self._llm = llm_client
        self._search = search_fn or _import_search_web()
        self._fetch = fetch_fn or _import_cloak_fetch()
        self._broadcast = broadcaster or (lambda _e, _p: None)
        self._save_screenshots = save_screenshots and os.getenv("CLOAK_SCREENSHOT", "1") == "1"
        if self._save_screenshots:
            _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────────────────
    async def research(
        self,
        gaps: list[str],
        goal: str = "",
        *,
        hop: int = 0,
        task_id: str = "",
        seed_urls: Optional[list[str]] = None,
        max_hops: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> dict:
        if budget_remaining() <= 0:
            self._broadcast("task:research_budget_exhausted", {"task_id": task_id, "goal": goal})
            return {
                "hop": hop, "gaps_researched": [], "findings_count": 0,
                "sources": [], "budget_exhausted": True,
            }

        gaps = [g for g in (gaps or []) if g.strip()][:5]
        if not gaps:
            return {"hop": hop, "gaps_researched": [], "findings_count": 0, "sources": []}

        self._broadcast("task:research_started", {
            "task_id": task_id, "goal": goal, "hop": hop, "gaps": gaps,
        })

        all_findings: list[dict] = []
        sources: list[str] = []
        # If caller supplied seed URLs (Phase 2 of Research v2), use them as the
        # candidate set for the first gap and skip the search step entirely.
        _seed = list(seed_urls or [])
        _cap = int(max_pages) if max_pages else None
        for idx, gap in enumerate(gaps):
            try:
                findings = await self._research_one(
                    gap, hop=hop,
                    seed_urls=(_seed if idx == 0 else None),
                    cap=_cap,
                )
            except Exception as e:
                logger.warning("research failed for gap '%s': %s", gap, e)
                findings = []
            self._persist(gap=gap, goal=goal, findings=findings)
            all_findings.extend(findings)
            sources.extend(f["url"] for f in findings if f.get("url"))

        _budget_consume(len(all_findings))

        result = {
            "hop": hop,
            "gaps_researched": gaps,
            "findings_count": len(all_findings),
            "sources": sources,
        }
        self._broadcast("task:research_completed", {"task_id": task_id, "goal": goal, **result})
        return result

    # ── Research v2: 2-phase API ─────────────────────────────────────────
    async def discover_sources(self, query: str, max_results: int = 10) -> list[dict]:
        """Phase 1: return candidate sources without fetching or summarizing.

        Reuses ``self._search`` but skips the stealth fetch + LLM summarize steps.
        Returns light source metadata for user-driven selection.
        """
        from urllib.parse import urlparse
        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, self._search, query, max_results)
        except Exception as e:
            logger.warning("discover_sources search failed: %s", e)
            results = []
        sources: list[dict] = []
        for r in results or []:
            url = (r.get("url") if isinstance(r, dict) else getattr(r, "url", "")) or ""
            if not url.startswith(("http://", "https://")):
                continue
            domain = urlparse(url).netloc
            sources.append({
                "id": hashlib.md5(url.encode("utf-8")).hexdigest()[:12],
                "url": url,
                "title": (r.get("title") if isinstance(r, dict) else "") or domain,
                "snippet": ((r.get("snippet") if isinstance(r, dict) else "") or "")[:500],
                "domain": domain,
                "trust_score": float(trust_for_url(url)),
                "source_type": _classify_source_type(url),
            })
        return sources

    async def run_research(self, query: str, sources: list[str]) -> list[dict]:
        """Fetch and summarize the given sources. Returns [{source, summary, tokens}]."""
        result = await self.research_selected(query, urls=sources)
        findings = []
        for gap in (result.get("gaps_researched") or []):
            # Reconstruct per-source rows from what was persisted in memory
            findings.append({"source": gap, "summary": "", "tokens": 0})
        # Richer: pull from the raw findings stored in _research_one via the result dict
        raw = result.get("findings") or []
        if raw:
            return [
                {
                    "source": f.get("url") or f.get("source", ""),
                    "summary": f.get("summary", ""),
                    "tokens": 0,
                }
                for f in raw
            ]
        return findings

    async def research_selected(
        self,
        query: str,
        urls: list[str],
        depth: str = "normal",
        task_id: str = "",
    ) -> dict:
        """Phase 2: run full pipeline on user-selected URLs only.

        depth: 'shallow' (1 hop, 3 pages), 'normal' (2 hops, 6 pages), 'deep' (3 hops, 10 pages).
        """
        depth_map = {"shallow": (1, 3), "normal": (2, 6), "deep": (3, 10)}
        max_hops, max_pages = depth_map.get(depth, (2, 6))
        return await self.research(
            gaps=[query],
            goal=query,
            task_id=task_id,
            seed_urls=urls,
            max_hops=max_hops,
            max_pages=max_pages,
        )

    # ── per-gap research ─────────────────────────────────────────────────
    async def _research_one(
        self,
        gap: str,
        *,
        hop: int,
        seed_urls: Optional[list[str]] = None,
        cap: Optional[int] = None,
    ) -> list[dict]:
        n = cap if cap else _DEPTH_PLAN.get(hop, 10)
        if seed_urls:
            search_results = [
                {"url": u, "title": "", "snippet": "", "source": "USER_SELECTED"}
                for u in seed_urls[:n]
            ]
        else:
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(None, self._search, gap, n)
        if not search_results:
            return []
        # Filter to results with usable URLs
        candidates = [r for r in search_results[:n] if (r.get("url") or "").startswith(("http://", "https://"))]
        if not candidates:
            # Search returned only synthetic/offline notices — store the snippet anyway
            return [{
                "url": "", "final_url": "",
                "title": r.get("title", ""),
                "summary": r.get("snippet", ""),
                "screenshot_b64": None,
                "source": r.get("source", "WEB"),
                "fetched_at": time.time(),
                "trust": 0.4,
            } for r in search_results[:n]]

        fetch_tasks = [self._fetch_safe(r["url"]) for r in candidates]
        pages = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        findings: list[dict] = []
        for r, page in zip(candidates, pages):
            if isinstance(page, Exception) or not isinstance(page, dict):
                continue
            text = (page.get("text") or "").strip()
            if not text:
                # Still record the search snippet so we have *something*
                summary = r.get("snippet", "")
            else:
                summary = await self._summarize(gap, text[:6000])
            findings.append({
                "url": page.get("final_url") or r.get("url"),
                "title": (page.get("title") or r.get("title") or "")[:240],
                "summary": summary,
                "screenshot_b64": page.get("screenshot_b64"),
                "source": r.get("source", "WEB"),
                "fetched_at": time.time(),
                "trust": trust_for_url(page.get("final_url") or r.get("url") or ""),
            })
        return findings

    async def _fetch_safe(self, url: str) -> dict:
        try:
            return await self._fetch(url)
        except Exception as e:
            return {"url": url, "final_url": url, "title": "", "text": "", "screenshot_b64": None, "error": str(e)}

    # ── summarization ────────────────────────────────────────────────────
    async def _summarize(self, gap: str, page_text: str) -> str:
        if not self._llm:
            # Fall back to first 600 chars as raw summary
            return page_text[:600]
        loop = asyncio.get_event_loop()
        def _do() -> str:
            try:
                prompt = (
                    f"Extract 3-5 key facts about '{gap}' from this page text. "
                    "Be concise, factual, cite specifics (numbers, names, dates) when present.\n\n"
                    f"PAGE TEXT:\n{page_text}\n\n"
                    "Reply with a tight bulleted list, no preamble."
                )
                resp = self._llm.complete(prompt=prompt, system="You are a precise research extractor.")
                if isinstance(resp, dict):
                    return (resp.get("text") or resp.get("output") or "").strip() or page_text[:600]
                return str(resp).strip() or page_text[:600]
            except Exception as e:
                logger.debug("LLM summarize failed: %s", e)
                return page_text[:600]
        return await loop.run_in_executor(None, _do)

    # ── three-layer persistence ──────────────────────────────────────────
    def _persist(self, *, gap: str, goal: str, findings: list[dict]) -> None:
        if not findings:
            return
        for f in findings:
            url = f.get("url") or ""
            url_hash = hashlib.sha1((url or f.get("title", "")).encode("utf-8")).hexdigest()[:16]
            shot_path = self._save_screenshot(url_hash, f.get("screenshot_b64"))
            if shot_path:
                f["screenshot_path"] = shot_path
                # Don't carry the heavy b64 into long-term stores
                f["screenshot_b64"] = None

            # ── Verification gate ──────────────────────────────────────
            # Decide auto_save / pending_review / discard for the claim
            # represented by this finding's summary. Hardened: any failure
            # falls back to the legacy auto-save behaviour so we never lose
            # findings due to a verifier hiccup.
            verification_dict: dict = {}
            decision = "auto_save"
            summary_text = (f.get("summary") or "").strip()
            if _VERIFY_AVAILABLE and summary_text and _get_verification_engine is not None:
                try:
                    vresult = _get_verification_engine().verify(
                        claim=summary_text,
                        sources=[url] if url else [],
                        context={"goal": goal, "gap": gap, "topic": gap[:80]},
                    )
                    decision = vresult.decision
                    verification_dict = vresult.to_dict()
                    f["verification"] = verification_dict
                except Exception as e:
                    logger.debug("verification failed (auto-saving): %s", e)

            if decision == "discard":
                logger.info(
                    "auto_research: discarded low-confidence finding "
                    "(confidence=%s) url=%s",
                    verification_dict.get("confidence"), url,
                )
                continue

            if decision == "pending_review" and _pending_queue_add is not None:
                try:
                    _pending_queue_add(
                        claim=summary_text,
                        verification=verification_dict,
                        topic=gap[:80] or "general_research",
                        sources=[url] if url else [],
                        raw_metadata={
                            "goal": goal,
                            "title": f.get("title", ""),
                            "url_hash": url_hash,
                            "screenshot_path": f.get("screenshot_path"),
                        },
                    )
                    logger.info(
                        "auto_research: queued for human review "
                        "(confidence=%s) url=%s",
                        verification_dict.get("confidence"), url,
                    )
                except Exception as e:
                    logger.debug("pending_queue add failed: %s", e)
                # Skip vector + graph stores until human approves
                continue

            # decision == 'auto_save' (or verifier unavailable) → persist below

            # Layer 1 — Memory router (vector + cache)
            try:
                self._memory.store(
                    key=f"research:{url_hash}",
                    text=f"GAP: {gap}\n\n{f.get('summary', '')}\n\nSOURCE: {url}",
                    memory_type="semantic",
                    source="auto-research",
                    importance=max(0.5, float(f.get("trust", 0.5))),
                    agent="auto-research",
                    extra={
                        "goal": goal,
                        "gap": gap,
                        "url": url,
                        "title": f.get("title", ""),
                        "screenshot_path": f.get("screenshot_path"),
                        "verification": verification_dict or None,
                    },
                )
            except Exception as e:
                logger.debug("memory store failed: %s", e)

            # Layer 2 — Brain graph (concept + relationships)
            self._graph_persist(gap=gap, goal=goal, finding=f, url_hash=url_hash)

        # Layer 3 — durable knowledge_store.json
        try:
            if self._knowledge:
                self._knowledge.add_knowledge(
                    topic=gap[:80] or "general_research",
                    content={
                        "goal": goal,
                        "gap": gap,
                        "findings": [
                            {k: v for k, v in f.items() if k != "screenshot_b64"} for f in findings
                        ],
                        "source": "auto-research",
                    },
                )
        except Exception as e:
            logger.debug("knowledge_store add failed: %s", e)

        # Outcome record (powers BrainInsightsPanel)
        try:
            self._memory.record_outcome(
                action="auto_research",
                success=True,
                context=f"goal={goal[:120]}",
                result={"gap": gap, "findings_count": len(findings)},
                goal_type="research",
            )
        except Exception:
            pass

    def _graph_persist(self, *, gap: str, goal: str, finding: dict, url_hash: str) -> None:
        graph = self._graph
        if not graph or not getattr(graph, "available", False):
            return
        try:
            gap_cid = graph.upsert_concept(label=gap[:80], type="Concept", weight=0.7)
            if goal:
                goal_cid = graph.upsert_concept(label=goal[:80], type="Task", weight=0.5)
                graph.link(gap_cid, goal_cid, rel="RELATES_TO", strength=0.6)
            title = (finding.get("title") or finding.get("url") or url_hash)[:80]
            src_cid = graph.upsert_concept(label=title, type="Memory", weight=float(finding.get("trust", 0.5)))
            graph.link(gap_cid, src_cid, rel="DERIVED_FROM", strength=float(finding.get("trust", 0.5)))
            mem_id = f"research:{url_hash}"
            graph.attach_memory(mem_id, [gap_cid, src_cid], label="MENTIONS")
        except Exception as e:
            logger.debug("graph persist failed: %s", e)

    def _save_screenshot(self, url_hash: str, b64: Optional[str]) -> Optional[str]:
        if not self._save_screenshots or not b64:
            return None
        try:
            path = _SCREENSHOT_DIR / f"{url_hash}.png"
            path.write_bytes(base64.b64decode(b64))
            return str(path)
        except Exception as e:
            logger.debug("screenshot save failed: %s", e)
            return None


# ── module-level singleton ───────────────────────────────────────────────
_instance: Optional[AutoResearchAgent] = None


def get_auto_researcher(broadcaster: Optional[Callable[[str, dict], None]] = None) -> AutoResearchAgent:
    """Singleton accessor — lazy-wires every dependency."""
    global _instance
    if _instance is None:
        from memory.memory_router import get_memory_router
        try:
            from neural_brain.graph.brain_graph import BrainGraph
            from neural_brain.graph.neo4j_adapter import Neo4jAdapter
            graph: Optional[Any] = BrainGraph(Neo4jAdapter())
        except Exception:
            graph = None
        try:
            from core.orchestrator import get_llm_client
            llm: Optional[Any] = get_llm_client()
        except Exception:
            llm = None
        try:
            from core.knowledge_store import get_knowledge_store
            ks: Optional[Any] = get_knowledge_store()
        except Exception:
            ks = None
        _instance = AutoResearchAgent(
            memory_router=get_memory_router(),
            brain_graph=graph,
            knowledge_store=ks,
            llm_client=llm,
            broadcaster=broadcaster,
        )
    elif broadcaster is not None:
        _instance._broadcast = broadcaster
    return _instance
