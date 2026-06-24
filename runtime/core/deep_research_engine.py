"""DeepResearchEngine — exhaustive multi-hop research that produces a structured report.

Architecture:
  1. Query decomposition  — LLM breaks topic into N sub-questions
  2. Parallel source discovery — DDG + Wikipedia per sub-question (up to 50 sources)
  3. Iterative page fetch + extraction — respects budget, dedupes by domain
  4. Cross-source synthesis — LLM merges findings per sub-question
  5. Gap detection — LLM asks "what do we still not know?" → up to 2 follow-up rounds
  6. Report generation — structured markdown with executive summary, sections, citations
  7. Memory commit — writes to KnowledgeVault + knowledge_store.json + memory router

Progress is streamed via an asyncio.Queue so callers can yield SSE events.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_STATE_DIR = Path(os.path.expanduser("~")) / ".ai-employee" / "state"
_REPORTS_DIR = _STATE_DIR / "deep_research_reports"
_REPORTS_INDEX = _STATE_DIR / "deep_research_index.json"

# Max sources to fetch per run (hard cap to avoid runaway budgets)
_MAX_SOURCES = int(os.getenv("DEEP_RESEARCH_MAX_SOURCES", "40"))
_MAX_SUB_QUESTIONS = int(os.getenv("DEEP_RESEARCH_MAX_SUBQUESTIONS", "6"))
_MAX_FOLLOW_UP_ROUNDS = 2
_PAGE_FETCH_CONCURRENCY = 6
_SOURCE_TEXT_LIMIT = 8000  # chars per page
# Resilience: a run reiterates on failure but is HARD-CAPPED so it can never loop
# forever — after this many escalating attempts it stops and informs the user.
_RESEARCH_ATTEMPTS_CEILING = 5


def _env_int(name: str, default: int) -> int:
    """Parse an int env var, falling back to default on any malformed value."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


_MAX_RESEARCH_ATTEMPTS = max(1, min(_RESEARCH_ATTEMPTS_CEILING,
                                    _env_int("RESEARCH_MAX_ATTEMPTS", 3)))


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SourceResult:
    url: str
    title: str
    snippet: str
    text: str = ""
    summary: str = ""
    sub_question: str = ""
    trust: float = 0.5
    fetched: bool = False
    error: str = ""


@dataclass
class DeepResearchReport:
    id: str
    topic: str
    created_at: float
    status: str = "in_progress"  # in_progress | done | failed
    sub_questions: list[str] = field(default_factory=list)
    sources_found: int = 0
    sources_fetched: int = 0
    executive_summary: str = ""
    sections: list[dict] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    gaps_identified: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    report_md: str = ""
    committed_to_memory: bool = False
    partial: bool = False  # True = delivered with incomplete sources after retries
    error: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ── Report persistence ────────────────────────────────────────────────────────

def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_index() -> list[dict]:
    try:
        return json.loads(_REPORTS_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_report(report: DeepResearchReport) -> None:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _REPORTS_DIR / f"{report.id}.json"
    _write_json_atomic(path, report.to_dict())
    # Update index
    index = _load_index()
    entry = {
        "id": report.id,
        "topic": report.topic,
        "status": report.status,
        "created_at": report.created_at,
        "sources_fetched": report.sources_fetched,
        "committed_to_memory": report.committed_to_memory,
    }
    index = [e for e in index if e.get("id") != report.id]
    index.insert(0, entry)
    _write_json_atomic(_REPORTS_INDEX, index[:200])


def load_report(report_id: str) -> Optional[dict]:
    try:
        path = _REPORTS_DIR / f"{report_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_reports(limit: int = 50) -> list[dict]:
    return _load_index()[:limit]


def delete_report(report_id: str) -> bool:
    try:
        (_REPORTS_DIR / f"{report_id}.json").unlink(missing_ok=True)
        index = [e for e in _load_index() if e.get("id") != report_id]
        _write_json_atomic(_REPORTS_INDEX, index)
        return True
    except Exception:
        return False


# ── LLM helpers (call Ollama directly, same pattern as auto_research_agent) ──

def _ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")


def _ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")


def _llm_complete(prompt: str, system: str = "", timeout: int = 90) -> str:
    """Synchronous LLM call via Ollama — returns text or empty string on failure."""
    import urllib.request
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": _ollama_model(),
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 2048},
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{_ollama_host()}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return (data.get("message") or {}).get("content", "").strip()
    except Exception as e:
        logger.debug("_llm_complete failed: %s", e)
        return ""


async def _llm_async(prompt: str, system: str = "", timeout: int = 90) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _llm_complete, prompt, system, timeout)


# ── Source fetching ──────────────────────────────────────────────────────────

async def _fetch_page(url: str) -> dict:
    """Fetch a page with the existing http fallback fetcher."""
    try:
        import urllib.request as _ur
        loop = asyncio.get_event_loop()
        def _do():
            req = _ur.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,text/plain",
            })
            with _ur.urlopen(req, timeout=12) as r:
                raw = r.read(300_000)
            ct = r.headers.get("Content-Type", "")
            if "html" in ct or not ct:
                text = _strip_html(raw.decode("utf-8", errors="ignore"))
            else:
                text = raw.decode("utf-8", errors="ignore")
            return {"url": url, "text": text[:_SOURCE_TEXT_LIMIT]}
        return await loop.run_in_executor(None, _do)
    except Exception as e:
        return {"url": url, "text": "", "error": str(e)}


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    # Remove scripts/styles blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    for ent, ch in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')]:
        html = html.replace(ent, ch)
    # Collapse whitespace
    return re.sub(r"\s{2,}", " ", html).strip()


# ── Main engine ───────────────────────────────────────────────────────────────

class DeepResearchEngine:
    """Run a full deep research cycle and stream progress events."""

    def __init__(self, progress_queue: Optional[asyncio.Queue] = None) -> None:
        self._q = progress_queue or asyncio.Queue()

    async def _emit(self, event: str, data: dict) -> None:
        await self._q.put({"event": event, "data": data, "ts": time.time()})

    # ── Public entry point ────────────────────────────────────────────────

    async def run(self, topic: str, depth: str = "deep", report_id: Optional[str] = None) -> DeepResearchReport:
        """Execute a deep research run that NEVER fails terminally.

        Resilience contract (Lars: "research can never fail — reiterate and restart"):
        the pipeline is attempted up to RESEARCH_MAX_ATTEMPTS times. Each retry is a
        REITERATION with an escalated strategy (broader depth) and an emitted
        'reiterate' event so the chat shows it adapting. If every attempt raises or
        yields zero usable sources, we still deliver a best-effort PARTIAL report
        (status='done', partial=True) from whatever was gathered — the terminal
        state is always a report the user can act on, never a dead 'failed'.

        *report_id* is used end-to-end so callers can poll/subscribe with the id
        they were handed.
        """
        report = DeepResearchReport(
            id=report_id or uuid.uuid4().hex[:16],
            topic=topic,
            created_at=time.time(),
        )
        _save_report(report)
        t0 = time.time()
        max_attempts = max(1, _MAX_RESEARCH_ATTEMPTS)
        depths = ["shallow", "normal", "deep"]
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            # Escalate the strategy on each reiteration so a retry casts a wider net.
            try:
                base_idx = depths.index(depth)
            except ValueError:
                base_idx = len(depths) - 1
            eff_depth = depths[min(len(depths) - 1, base_idx + (attempt - 1))]

            if attempt == 1:
                await self._emit("started", {"id": report.id, "topic": topic, "depth": eff_depth})
            else:
                await self._emit("reiterate", {"id": report.id, "attempt": attempt,
                                               "max_attempts": max_attempts, "depth": eff_depth,
                                               "reason": last_error or "insufficient sources — broadening search"})
            try:
                await self._run_pipeline(report, topic, eff_depth)
                if report.sources_fetched > 0 or (report.report_md or report.executive_summary):
                    report.status = "done"
                    report.duration_s = round(time.time() - t0, 1)
                    _save_report(report)
                    await self._emit("done", {"id": report.id, "duration_s": report.duration_s,
                                               "sources": report.sources_fetched, "topic": topic,
                                               "attempts": attempt})
                    return report
                last_error = "no usable sources found"
            except Exception as exc:  # noqa: BLE001 — reiterate instead of dying
                last_error = str(exc)
                logger.warning("deep research attempt %d/%d failed: %s", attempt, max_attempts, exc)

        # All attempts exhausted → deliver a best-effort PARTIAL report (never 'failed').
        report.status = "done"
        report.partial = True
        report.error = last_error or "completed with partial results after retries"
        report.duration_s = round(time.time() - t0, 1)
        if not report.report_md and not report.executive_summary:
            report.executive_summary = (
                f"Partial result: research on “{topic}” could not gather full sources after "
                f"{max_attempts} attempts ({report.error}). Findings are limited; consider refining the topic or retrying later."
            )
        _save_report(report)
        await self._emit("done", {"id": report.id, "duration_s": report.duration_s,
                                   "sources": report.sources_fetched, "topic": topic,
                                   "attempts": max_attempts, "partial": True})
        return report

    async def _run_pipeline(self, report: "DeepResearchReport", topic: str, depth: str) -> None:
        """One full research pass. Raises on hard failure (the caller reiterates)."""
        # 1. Decompose topic into sub-questions
        await self._emit("phase", {"phase": "decompose", "msg": "Breaking topic into research questions…"})
        report.sub_questions = await self._decompose(topic, depth)
        _save_report(report)
        await self._emit("sub_questions", {"questions": report.sub_questions})

        # 2. Discover sources for all sub-questions in parallel
        await self._emit("phase", {"phase": "discover", "msg": f"Discovering sources for {len(report.sub_questions)} questions…"})
        all_sources = await self._discover_all(topic, report.sub_questions)
        report.sources_found = len(all_sources)
        _save_report(report)
        await self._emit("sources_found", {"count": len(all_sources)})

        # 3. Fetch and extract page text
        await self._emit("phase", {"phase": "fetch", "msg": f"Reading {len(all_sources)} sources…"})
        fetched = await self._fetch_all(all_sources, report)
        report.sources_fetched = sum(1 for s in fetched if s.fetched)
        _save_report(report)
        await self._emit("fetched", {"count": report.sources_fetched, "total": len(fetched)})

        # 4. Summarize per sub-question
        await self._emit("phase", {"phase": "synthesize", "msg": "Synthesizing findings per question…"})
        syntheses = await self._synthesize_all(topic, report.sub_questions, fetched, report)

        # 5. Detect gaps → follow-up rounds
        await self._emit("phase", {"phase": "gaps", "msg": "Detecting knowledge gaps…"})
        gap_sources = await self._fill_gaps(topic, syntheses, report)
        if gap_sources:
            fetched.extend(gap_sources)
            report.sources_fetched += sum(1 for s in gap_sources if s.fetched)
            _save_report(report)

        # 6. Generate final report
        await self._emit("phase", {"phase": "report", "msg": "Generating research report…"})
        await self._generate_report(topic, report.sub_questions, fetched, syntheses, report)
        _save_report(report)

        return report

    # ── Phase 1: Decompose ───────────────────────────────────────────────

    async def _decompose(self, topic: str, depth: str) -> list[str]:
        n = {"shallow": 3, "normal": 5, "deep": _MAX_SUB_QUESTIONS}.get(depth, _MAX_SUB_QUESTIONS)
        prompt = (
            f"Topic to research: {topic}\n\n"
            f"Generate exactly {n} specific research sub-questions that together give a complete understanding of this topic. "
            "Cover: definition/overview, current state, key players/examples, practical applications, "
            "challenges/limitations, and future outlook where relevant.\n\n"
            "Return ONLY a numbered list, one question per line. No extra text."
        )
        raw = await _llm_async(prompt, system="You are a precise research planner.", timeout=60)
        questions = []
        for line in raw.splitlines():
            line = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
            if len(line) > 15:
                questions.append(line)
        if not questions:
            # Fallback: generic sub-questions
            questions = [
                f"What is {topic} and how does it work?",
                f"What are the key components and examples of {topic}?",
                f"What are the current best practices for {topic}?",
                f"What are the main challenges and limitations of {topic}?",
                f"What is the future outlook for {topic}?",
            ]
        return questions[:n]

    # ── Phase 2: Discover sources ─────────────────────────────────────────

    async def _discover_all(self, topic: str, sub_questions: list[str]) -> list[SourceResult]:
        """Search for sources per sub-question, dedupe by URL."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents" / "ai-router"))
        try:
            from ai_router import search_web  # type: ignore
        except ImportError:
            search_web = None

        per_q = max(4, _MAX_SOURCES // max(1, len(sub_questions)))
        seen_urls: set[str] = set()
        all_sources: list[SourceResult] = []

        async def _search_one(q: str) -> list[SourceResult]:
            loop = asyncio.get_event_loop()
            try:
                if search_web:
                    results = await loop.run_in_executor(None, search_web, q, per_q)
                else:
                    results = []
            except Exception:
                results = []
            out = []
            for r in results or []:
                url = (r.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                out.append(SourceResult(
                    url=url,
                    title=(r.get("title") or "")[:200],
                    snippet=(r.get("snippet") or "")[:500],
                    sub_question=q,
                    trust=float(_trust_score(url)),
                ))
            return out

        tasks = [_search_one(q) for q in sub_questions]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_sources.extend(r)
        return all_sources[:_MAX_SOURCES]

    # ── Phase 3: Fetch pages ──────────────────────────────────────────────

    async def _fetch_all(self, sources: list[SourceResult], report: DeepResearchReport) -> list[SourceResult]:
        sem = asyncio.Semaphore(_PAGE_FETCH_CONCURRENCY)
        fetched_count = 0

        async def _one(src: SourceResult) -> SourceResult:
            nonlocal fetched_count
            async with sem:
                # Announce the site BEFORE fetching so the live view shows what is
                # being visited in real time (not only completed reads).
                await self._emit("source_visit", {"url": src.url, "title": (src.title or "")[:80]})
                result = await _fetch_page(src.url)
                src.text = result.get("text", "")
                src.fetched = bool(src.text)
                src.error = result.get("error", "")
                if src.fetched:
                    fetched_count += 1
                    report.sources_fetched = fetched_count
                    await self._emit("source_read", {
                        "url": src.url, "title": src.title[:80],
                        "chars": len(src.text), "count": fetched_count,
                    })
                else:
                    await self._emit("source_failed", {"url": src.url, "error": (src.error or "no content")[:120]})
                return src

        return list(await asyncio.gather(*[_one(s) for s in sources]))

    # ── Phase 4: Synthesize ───────────────────────────────────────────────

    async def _synthesize_all(
        self, topic: str, sub_questions: list[str],
        sources: list[SourceResult], report: DeepResearchReport,
    ) -> dict[str, str]:
        """For each sub-question, gather relevant source texts and synthesize."""
        syntheses: dict[str, str] = {}
        for q in sub_questions:
            relevant = [s for s in sources if s.sub_question == q and s.text]
            if not relevant:
                # Use any fetched source as fallback
                relevant = [s for s in sources if s.text][:4]
            combined = "\n\n---\n\n".join(
                f"SOURCE: {s.url}\nTITLE: {s.title}\n{s.text[:3000]}"
                for s in relevant[:6]
            )
            if not combined:
                combined = "\n".join(s.snippet for s in relevant[:6] if s.snippet)
            if not combined:
                syntheses[q] = ""
                continue

            prompt = (
                f"Research question: {q}\n\n"
                f"Context topic: {topic}\n\n"
                f"Source material:\n{combined}\n\n"
                "Based solely on the source material above, write a comprehensive answer to the research question. "
                "Include specific facts, numbers, names, dates when present. "
                "Cite sources using [domain.com] notation inline. "
                "Be thorough — this will become a section in a research report. Min 200 words."
            )
            synthesis = await _llm_async(prompt, system="You are a thorough research analyst.", timeout=120)
            syntheses[q] = synthesis
            await self._emit("section_done", {"question": q[:80], "chars": len(synthesis)})

        return syntheses

    # ── Phase 5: Gap detection + follow-up ───────────────────────────────

    async def _fill_gaps(
        self, topic: str, syntheses: dict[str, str], report: DeepResearchReport,
    ) -> list[SourceResult]:
        """Ask LLM what is still unknown, do 1 follow-up search round."""
        synthesis_text = "\n\n".join(
            f"Q: {q}\nA: {a[:800]}" for q, a in syntheses.items() if a
        )
        if not synthesis_text:
            return []

        prompt = (
            f"Topic: {topic}\n\n"
            f"Current research findings:\n{synthesis_text}\n\n"
            "What specific factual gaps remain? List up to 3 concrete follow-up search queries "
            "(things we still don't know or need more detail on). "
            "Return ONLY a numbered list, one query per line. No extra text."
        )
        raw = await _llm_async(prompt, system="You are a research gap analyst.", timeout=60)
        gap_queries = []
        for line in raw.splitlines():
            line = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
            if len(line) > 10:
                gap_queries.append(line)
        gap_queries = gap_queries[:3]

        if not gap_queries:
            return []

        report.gaps_identified = gap_queries
        await self._emit("gaps_found", {"gaps": gap_queries})

        # One follow-up search round for the gaps
        gap_sources = await self._discover_all(topic, gap_queries)
        if gap_sources:
            await self._emit("phase", {"phase": "fetch_gaps", "msg": f"Reading {len(gap_sources)} gap sources…"})
            return await self._fetch_all(gap_sources, report)
        return []

    # ── Phase 6: Report generation ────────────────────────────────────────

    async def _generate_report(
        self,
        topic: str,
        sub_questions: list[str],
        all_sources: list[SourceResult],
        syntheses: dict[str, str],
        report: DeepResearchReport,
    ) -> None:
        # Build citations list
        seen = set()
        citations = []
        for s in all_sources:
            if s.url and s.url not in seen and (s.fetched or s.snippet):
                seen.add(s.url)
                citations.append({"url": s.url, "title": s.title or s.url, "sub_question": s.sub_question})
        report.citations = citations[:50]

        # Executive summary
        all_synthesis = "\n\n".join(f"### {q}\n{a}" for q, a in syntheses.items() if a)
        exec_prompt = (
            f"Topic: {topic}\n\n"
            f"Research findings:\n{all_synthesis[:6000]}\n\n"
            "Write a concise executive summary (3-5 paragraphs) that captures the most important insights. "
            "Start with a 1-sentence overview, then key findings, then implications. "
            "Cite sources inline as [domain.com]. Plain prose, no headers."
        )
        report.executive_summary = await _llm_async(
            exec_prompt, system="You are an expert research analyst.", timeout=120
        )

        # Key findings bullet list
        kf_prompt = (
            f"Topic: {topic}\n\n"
            f"Research:\n{all_synthesis[:4000]}\n\n"
            "Extract exactly 8-10 key findings as bullet points. "
            "Each bullet: one specific, factual insight. Start each with '- '. No preamble."
        )
        kf_raw = await _llm_async(kf_prompt, system="You are a research analyst.", timeout=60)
        report.key_findings = [
            line.lstrip("- •").strip()
            for line in kf_raw.splitlines()
            if line.strip().startswith(("-", "•", "*"))
        ][:10]

        # Build sections
        report.sections = [
            {"title": q, "content": syntheses.get(q, "No data found for this question.")}
            for q in sub_questions
        ]

        # Assemble full markdown report
        report.report_md = _build_report_md(topic, report)

    # ── Memory commit ─────────────────────────────────────────────────────

    async def commit_to_memory(self, report_id: str) -> dict:
        """Commit a completed report to all memory layers."""
        data = load_report(report_id)
        if not data:
            return {"ok": False, "error": "report not found"}
        if data.get("status") != "done":
            return {"ok": False, "error": "report not complete"}

        topic = data["topic"]
        report_md = data.get("report_md", "")
        executive_summary = data.get("executive_summary", "")
        key_findings = data.get("key_findings", [])
        citations = data.get("citations", [])

        committed = []

        # 1. KnowledgeVault — full report as a vault entry
        try:
            from memory.knowledge_vault import KnowledgeVault
            vault = KnowledgeVault()
            slug = re.sub(r"[^\w\s-]", "", topic.lower()).strip().replace(" ", "-")[:80]
            vault_content = f"{executive_summary}\n\n## Key Findings\n\n"
            for kf in key_findings:
                vault_content += f"- {kf}\n"
            vault_content += f"\n## Sources\n\n"
            for c in citations[:20]:
                vault_content += f"- [{c.get('title', c['url'])[:80]}]({c['url']})\n"
            vault.store(
                title=f"Deep Research: {topic}",
                content=vault_content,
                tags=["deep-research", "auto-generated"],
                status="verified",
                extra={"report_id": report_id, "source": "deep-research"},
            )
            committed.append("vault")
        except Exception as e:
            logger.debug("vault commit failed: %s", e)

        # 2. knowledge_store.json — queryable by agent_controller
        try:
            from core.knowledge_store import get_knowledge_store
            ks = get_knowledge_store()
            ks.add_knowledge(
                topic=topic[:80],
                content={
                    "source": "deep-research",
                    "report_id": report_id,
                    "executive_summary": executive_summary,
                    "key_findings": key_findings,
                    "sections": data.get("sections", []),
                    "citations": [c["url"] for c in citations[:20]],
                },
            )
            committed.append("knowledge_store")
        except Exception as e:
            logger.debug("knowledge_store commit failed: %s", e)

        # 3. Memory router (vector store) — chunk + embed
        try:
            from core.auto_research_agent import get_auto_researcher
            agent = get_auto_researcher()
            # Store executive summary + each section as separate vector entries
            chunks = [("overview", executive_summary)] + [
                (s["title"], s["content"])
                for s in (data.get("sections") or [])
            ]
            for chunk_title, chunk_text in chunks:
                if not chunk_text:
                    continue
                agent._memory.store(
                    key=f"deep-research:{report_id}:{hashlib.sha1(chunk_title.encode()).hexdigest()[:8]}",
                    text=f"TOPIC: {topic}\nSECTION: {chunk_title}\n\n{chunk_text[:2000]}",
                    memory_type="semantic",
                    source="deep-research",
                    importance=0.9,
                    agent="deep-research",
                    extra={"report_id": report_id, "topic": topic},
                )
            committed.append("vector_store")
        except Exception as e:
            logger.debug("memory router commit failed: %s", e)

        # Mark as committed
        try:
            path = _REPORTS_DIR / f"{report_id}.json"
            d = json.loads(path.read_text())
            d["committed_to_memory"] = True
            _write_json_atomic(path, d)
            index = _load_index()
            for e in index:
                if e.get("id") == report_id:
                    e["committed_to_memory"] = True
            _write_json_atomic(_REPORTS_INDEX, index)
        except Exception:
            pass

        return {"ok": True, "committed_to": committed, "report_id": report_id}


# ── Report markdown builder ───────────────────────────────────────────────────

def _build_report_md(topic: str, report: DeepResearchReport) -> str:
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(report.created_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Deep Research Report: {topic}",
        f"",
        f"**Generated:** {dt}  ",
        f"**Sources:** {report.sources_fetched} pages fetched  ",
        f"**Status:** {report.status}",
        f"",
        f"---",
        f"",
        f"## Executive Summary",
        f"",
        report.executive_summary or "_No summary generated._",
        f"",
        f"---",
        f"",
        f"## Key Findings",
        f"",
    ]
    for kf in report.key_findings:
        lines.append(f"- {kf}")
    lines += ["", "---", "", "## Research Sections", ""]
    for section in report.sections:
        lines += [
            f"### {section['title']}",
            f"",
            section.get("content", "_No content._"),
            f"",
        ]
    if report.gaps_identified:
        lines += ["---", "", "## Knowledge Gaps Identified", ""]
        for g in report.gaps_identified:
            lines.append(f"- {g}")
        lines.append("")
    lines += ["---", "", "## Sources & Citations", ""]
    for i, c in enumerate(report.citations, 1):
        lines.append(f"{i}. [{c.get('title', c['url'])[:100]}]({c['url']})")
    return "\n".join(lines)


# ── Trust scoring (lightweight, no imports) ──────────────────────────────────

def _trust_score(url: str) -> float:
    u = url.lower()
    if any(d in u for d in (".edu/", "arxiv.org", "doi.org", "scholar.google")): return 0.95
    if any(d in u for d in ("wikipedia.org", "reuters.com", "bbc.com", "nature.com")): return 0.9
    if any(d in u for d in ("github.com", "stackoverflow.com", "docs.")): return 0.85
    if any(d in u for d in ("reddit.com", "forum", "quora.com")): return 0.5
    return 0.7


# ── Module-level sys.path fix ─────────────────────────────────────────────────

import sys
_RUNTIME_ROOT = str(Path(__file__).resolve().parents[1])
if _RUNTIME_ROOT not in sys.path:
    sys.path.insert(0, _RUNTIME_ROOT)
