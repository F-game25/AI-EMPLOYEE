"""AI Router — Ollama-first with cloud AI fallback + per-agent model routing + web search.

Routes AI queries to the best available provider in priority order:
  1. Ollama  (local, free, private — preferred)
  2. Anthropic Claude  (cloud, costs tokens — fallback)
  3. OpenAI  (cloud, costs tokens — last resort)

Per-agent model routing (query_ai_for_agent):
  - sales / persuasive   → OpenAI GPT-4o (best persuasive writing)
  - analytical / data    → Anthropic Claude (long context, deep reasoning)
  - creative             → OpenAI GPT-4o (best creative output)
  - coding               → OpenAI GPT-4o (strong code generation)
  - general / local      → Ollama (free, privacy-preserving)

Also provides search_web() for web research tasks:
  - DuckDuckGo Instant Answers (free, no API key)
  - Wikipedia summary (free, no API key)
  - NewsAPI (free tier, requires NEWS_API_KEY)
  - Tavily AI search (requires TAVILY_API_KEY)
  - SerpAPI (requires SERP_API_KEY)

Usage (from any bot that adds this directory to sys.path):

    import sys, os
    from pathlib import Path
    AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
    sys.path.insert(0, str(AI_HOME / "bots" / "ai-router"))
    from ai_router import query_ai, query_ai_for_agent, search_web

    result = query_ai("Explain quantum computing in simple terms")
    print(result["answer"])    # the response text
    print(result["provider"])  # "ollama" | "anthropic" | "openai" | "error"

    # Agent-aware routing: picks the best model for the task type
    result = query_ai_for_agent("sales", "Write a cold email for a SaaS product")
    result = query_ai_for_agent("analytical", "Analyse this dataset...", history=[...])

    hits = search_web("latest AI news 2025")
    for h in hits:
        print(h["title"], h["url"], h["snippet"])

Environment variables (loaded from ~/.ai-employee/.env):
    OLLAMA_HOST           — Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL          — model name (default: llama3.2)
    OLLAMA_TIMEOUT        — request timeout in seconds (default: 60)
    ANTHROPIC_API_KEY     — Anthropic key (optional cloud fallback)
    CLAUDE_MODEL          — Claude model name (default: claude-opus-4-5)
    OPENAI_API_KEY        — OpenAI key (optional last-resort fallback)
    OPENAI_MODEL          — OpenAI model name (default: gpt-4o-mini)
    OPENAI_MODEL_SALES    — override model for sales/persuasive tasks (default: gpt-4o)
    OPENAI_MODEL_CREATIVE — override model for creative tasks (default: gpt-4o)
    CLOUD_AI_TIMEOUT      — cloud request timeout in seconds (default: 30)
    TAVILY_API_KEY        — Tavily AI search key (optional, best quality)
    SERP_API_KEY          — SerpAPI key (optional)
    NEWS_API_KEY          — NewsAPI key (optional, for news searches)
    WEB_SEARCH_TIMEOUT    — web search timeout in seconds (default: 15)
"""
import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("ai_router")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MODEL_SALES = os.environ.get("OPENAI_MODEL_SALES", "gpt-4o")
OPENAI_MODEL_CREATIVE = os.environ.get("OPENAI_MODEL_CREATIVE", "gpt-4o")

CLOUD_AI_TIMEOUT = int(os.environ.get("CLOUD_AI_TIMEOUT", "30"))

# ── Per-agent model routing ───────────────────────────────────────────────────
# Maps agent_type keyword → preferred (provider, model) pair.
# Provider is tried first; falls back through the normal chain if unavailable.
_AGENT_ROUTING: dict[str, tuple[str, str]] = {
    # Sales & persuasion — GPT-4o excels at persuasive, human-sounding copy
    "sales":       ("openai", OPENAI_MODEL_SALES),
    "persuasive":  ("openai", OPENAI_MODEL_SALES),
    "email-ninja": ("openai", OPENAI_MODEL_SALES),
    "outreach":    ("openai", OPENAI_MODEL_SALES),
    # Data & analysis — Claude handles long context / deep reasoning
    "analytical":  ("anthropic", CLAUDE_MODEL),
    "data":        ("anthropic", CLAUDE_MODEL),
    "research":    ("anthropic", CLAUDE_MODEL),
    "intel-agent": ("anthropic", CLAUDE_MODEL),
    "finance":     ("anthropic", CLAUDE_MODEL),
    # Creative — GPT-4o produces the best creative / ad copy
    "creative":    ("openai", OPENAI_MODEL_CREATIVE),
    "content":     ("openai", OPENAI_MODEL_CREATIVE),
    "social":      ("openai", OPENAI_MODEL_CREATIVE),
    # Coding — GPT-4o is strongest for code generation
    "coding":      ("openai", OPENAI_MODEL_CREATIVE),
    "bot-dev":     ("openai", OPENAI_MODEL_CREATIVE),
    # Orchestration / general — Claude for long-context planning
    "orchestrator": ("anthropic", CLAUDE_MODEL),
    "planning":    ("anthropic", CLAUDE_MODEL),
    # Default / local — Ollama (free, privacy-preserving)
    "general":     ("ollama", OLLAMA_MODEL),
    "local":       ("ollama", OLLAMA_MODEL),
}

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
SERP_API_KEY = os.environ.get("SERP_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
WEB_SEARCH_TIMEOUT = int(os.environ.get("WEB_SEARCH_TIMEOUT", "15"))


def _build_messages(prompt: str, system_prompt: str, history: list) -> list:
    """Build a messages list from prompt, optional system prompt, and history."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    return messages


def _try_ollama(prompt: str, system_prompt: str, history: list) -> Optional[dict]:
    """Attempt to get a response from the local Ollama instance."""
    try:
        import requests  # lightweight stdlib-like dep already used by ollama-agent

        messages = _build_messages(prompt, system_prompt, history)
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("message", {}).get("content", "").strip()
        if answer:
            logger.debug("ai_router: used Ollama (%s)", OLLAMA_MODEL)
            return {
                "answer": answer,
                "provider": "ollama",
                "model": OLLAMA_MODEL,
                "error": None,
            }
    except Exception as exc:
        logger.debug("ai_router: Ollama unavailable — %s", exc)
    return None


def _try_anthropic(prompt: str, system_prompt: str, history: list) -> Optional[dict]:
    """Attempt to get a response from Anthropic Claude (cloud fallback)."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        messages = list(history) if history else []
        messages.append({"role": "user", "content": prompt})
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt or "You are a helpful AI assistant.",
            messages=messages,
        )
        answer = response.content[0].text.strip()
        logger.debug("ai_router: used Anthropic Claude (%s)", CLAUDE_MODEL)
        return {
            "answer": answer,
            "provider": "anthropic",
            "model": CLAUDE_MODEL,
            "error": None,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }
    except Exception as exc:
        logger.debug("ai_router: Anthropic unavailable — %s", exc)
    return None


def _try_openai(prompt: str, system_prompt: str, history: list) -> Optional[dict]:
    """Attempt to get a response from OpenAI (last-resort cloud fallback)."""
    if not OPENAI_API_KEY:
        return None
    try:
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        messages = _build_messages(prompt, system_prompt, history)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=4096,
            timeout=CLOUD_AI_TIMEOUT,
        )
        answer = response.choices[0].message.content.strip()
        logger.debug("ai_router: used OpenAI (%s)", OPENAI_MODEL)
        return {
            "answer": answer,
            "provider": "openai",
            "model": OPENAI_MODEL,
            "error": None,
            "usage": {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
        }
    except Exception as exc:
        logger.debug("ai_router: OpenAI unavailable — %s", exc)
    return None


def query_ai(
    prompt: str,
    system_prompt: str = "",
    history: Optional[list] = None,
) -> dict:
    """Route an AI query through providers in priority order.

    Priority:
        1. Ollama (local, free) — always tried first
        2. Anthropic Claude (cloud) — only if Ollama unavailable and key set
        3. OpenAI (cloud) — only if both above fail and key set

    Args:
        prompt: The user message or question.
        system_prompt: Optional system/role instructions for the AI.
        history: Optional list of previous messages in OpenAI chat format,
                 e.g. [{"role": "user", "content": "..."}, {"role": "assistant", ...}]

    Returns:
        dict with keys:
            answer   (str)  — AI response text, empty string on failure
            provider (str)  — "ollama" | "anthropic" | "openai" | "error"
            model    (str)  — model identifier used
            error    (str|None) — error description if all providers failed
            usage    (dict|None) — token usage for cloud providers
    """
    history = history or []

    # 1. Try Ollama first (local, free, privacy-preserving)
    result = _try_ollama(prompt, system_prompt, history)
    if result:
        return result

    # 2. Try Anthropic Claude (cloud, costs tokens — fallback)
    result = _try_anthropic(prompt, system_prompt, history)
    if result:
        return result

    # 3. Try OpenAI (cloud, costs tokens — last resort)
    result = _try_openai(prompt, system_prompt, history)
    if result:
        return result

    # All providers failed
    return {
        "answer": "",
        "provider": "error",
        "model": "",
        "error": (
            "No AI provider available. "
            "Start Ollama (`ollama serve`) or set ANTHROPIC_API_KEY / OPENAI_API_KEY "
            "in ~/.ai-employee/.env and restart."
        ),
        "usage": None,
    }


def is_ollama_available() -> bool:
    """Quick check whether the local Ollama instance is reachable."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def query_ai_for_agent(
    agent_type: str,
    prompt: str,
    system_prompt: str = "",
    history: Optional[list] = None,
) -> dict:
    """Route an AI query to the best model for a specific agent type.

    Uses _AGENT_ROUTING to select the optimal provider/model for each task
    category (e.g. sales → GPT-4o, analytics → Claude, general → Ollama),
    then falls back through the standard provider chain if the preferred
    provider is unavailable.

    Args:
        agent_type:   Agent category key (e.g. "sales", "analytical", "creative").
                      Case-insensitive. Falls back to general routing if unknown.
        prompt:       The user message or question.
        system_prompt: Optional system/role instructions.
        history:      Optional conversation history.

    Returns:
        Same dict structure as query_ai():
            answer, provider, model, error, usage
    """
    history = history or []
    agent_key = agent_type.lower()

    # Look up preferred provider/model for this agent type
    preferred_provider, preferred_model = _AGENT_ROUTING.get(
        agent_key, _AGENT_ROUTING.get("general", ("ollama", OLLAMA_MODEL))
    )

    logger.debug(
        "ai_router: agent_type=%s → preferred_provider=%s model=%s",
        agent_type, preferred_provider, preferred_model,
    )

    # Override model env vars temporarily for this call using local variables
    result = None
    if preferred_provider == "openai" and OPENAI_API_KEY:
        try:
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            messages = _build_messages(prompt, system_prompt, history)
            response = client.chat.completions.create(
                model=preferred_model,
                messages=messages,
                max_tokens=4096,
                timeout=CLOUD_AI_TIMEOUT,
            )
            answer = response.choices[0].message.content.strip()
            logger.debug("ai_router: agent=%s used OpenAI/%s", agent_type, preferred_model)
            result = {
                "answer": answer,
                "provider": "openai",
                "model": preferred_model,
                "error": None,
                "usage": {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                },
            }
        except Exception as exc:
            logger.debug("ai_router: preferred OpenAI/%s failed — %s", preferred_model, exc)

    elif preferred_provider == "anthropic" and ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            messages = list(history) if history else []
            messages.append({"role": "user", "content": prompt})
            response = client.messages.create(
                model=preferred_model,
                max_tokens=4096,
                system=system_prompt or "You are a helpful AI assistant.",
                messages=messages,
            )
            answer = response.content[0].text.strip()
            logger.debug("ai_router: agent=%s used Anthropic/%s", agent_type, preferred_model)
            result = {
                "answer": answer,
                "provider": "anthropic",
                "model": preferred_model,
                "error": None,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }
        except Exception as exc:
            logger.debug("ai_router: preferred Anthropic/%s failed — %s", preferred_model, exc)

    elif preferred_provider == "ollama":
        result = _try_ollama(prompt, system_prompt, history)

    # Fall back to the standard chain if preferred provider failed
    if result:
        return result

    logger.debug(
        "ai_router: preferred provider for agent=%s unavailable, falling back to standard chain",
        agent_type,
    )
    return query_ai(prompt, system_prompt=system_prompt, history=history)


# ── Web Search ────────────────────────────────────────────────────────────────

def _http_get_json(url: str, headers: Optional[dict] = None, timeout: int = WEB_SEARCH_TIMEOUT) -> Optional[dict]:
    """Fetch a URL and parse as JSON using only stdlib."""
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "AI-Employee/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        logger.debug("_http_get_json error for %s: %s", url, exc)
        return None


def _ddg_instant(query: str) -> list:
    """DuckDuckGo Instant Answer API — free, no key required."""
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query, "format": "json", "no_html": "1", "skip_disambig": "1",
    })
    data = _http_get_json(url)
    if not data:
        return []
    results = []
    abstract = data.get("AbstractText", "").strip()
    abstract_url = data.get("AbstractURL", "").strip()
    abstract_src = data.get("AbstractSource", "")
    if abstract:
        results.append({
            "title": data.get("Heading", query),
            "url": abstract_url,
            "snippet": abstract,
            "source": abstract_src or "DuckDuckGo",
        })
    for rel in data.get("RelatedTopics", [])[:4]:
        if isinstance(rel, dict) and rel.get("Text") and rel.get("FirstURL"):
            results.append({
                "title": rel.get("Text", "")[:80],
                "url": rel["FirstURL"],
                "snippet": rel.get("Text", ""),
                "source": "DuckDuckGo",
            })
    return results


def _wiki_search(query: str, max_results: int = 3) -> list:
    """Wikipedia search + extract summary — free, no key required."""
    results = []
    # Step 1: search for titles
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "opensearch", "search": query, "limit": max_results,
        "namespace": "0", "format": "json",
    })
    data = _http_get_json(search_url)
    if not data or len(data) < 4:
        return []
    titles = data[1][:max_results]
    urls = data[3][:max_results]
    # Step 2: fetch extract for first result
    if titles:
        extract_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "prop": "extracts", "exintro": "1",
            "explaintext": "1", "titles": titles[0], "format": "json",
        })
        ext_data = _http_get_json(extract_url)
        if ext_data:
            pages = ext_data.get("query", {}).get("pages", {})
            for page in pages.values():
                extract = page.get("extract", "").strip()
                if extract:
                    results.append({
                        "title": titles[0],
                        "url": urls[0] if urls else "",
                        "snippet": extract[:800],
                        "source": "Wikipedia",
                    })
                    break
    # Add remaining titles without full extracts
    for i, (title, url) in enumerate(zip(titles[1:], urls[1:]), 1):
        results.append({"title": title, "url": url, "snippet": title, "source": "Wikipedia"})
    return results


def _news_api_search(query: str, max_results: int = 5) -> list:
    """NewsAPI search — free tier, requires NEWS_API_KEY."""
    if not NEWS_API_KEY:
        return []
    url = "https://newsapi.org/v2/everything?" + urllib.parse.urlencode({
        "q": query, "apiKey": NEWS_API_KEY, "pageSize": max_results,
        "sortBy": "relevancy", "language": "en",
    })
    data = _http_get_json(url)
    if not data or data.get("status") != "ok":
        return []
    results = []
    for art in data.get("articles", [])[:max_results]:
        results.append({
            "title": art.get("title", ""),
            "url": art.get("url", ""),
            "snippet": art.get("description") or art.get("content", "")[:300],
            "source": art.get("source", {}).get("name", "NewsAPI"),
            "published_at": art.get("publishedAt", ""),
        })
    return results


def _tavily_search(query: str, max_results: int = 5) -> list:
    """Tavily AI Search — best quality for AI research, requires TAVILY_API_KEY."""
    if not TAVILY_API_KEY:
        return []
    try:
        import requests as _requests
        resp = _requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results,
                  "search_depth": "basic", "include_answer": True},
            timeout=WEB_SEARCH_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        # Include Tavily's synthesized answer as a top result
        if data.get("answer"):
            results.append({
                "title": f"Summary: {query}",
                "url": "",
                "snippet": data["answer"],
                "source": "Tavily AI",
            })
        for r in data.get("results", [])[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:400],
                "source": "Tavily",
            })
        return results
    except Exception as exc:
        logger.debug("Tavily search error: %s", exc)
        return []


def _serp_search(query: str, max_results: int = 5) -> list:
    """SerpAPI Google search — requires SERP_API_KEY."""
    if not SERP_API_KEY:
        return []
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode({
        "q": query, "api_key": SERP_API_KEY, "num": max_results,
        "engine": "google",
    })
    data = _http_get_json(url)
    if not data:
        return []
    results = []
    for r in data.get("organic_results", [])[:max_results]:
        results.append({
            "title": r.get("title", ""),
            "url": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "source": "Google via SerpAPI",
        })
    return results


def search_web(query: str, max_results: int = 5, include_news: bool = False) -> list:
    """Search the web using the best available provider.

    Priority:
        1. Tavily AI Search (if TAVILY_API_KEY set — best quality for AI use)
        2. SerpAPI (if SERP_API_KEY set — comprehensive Google results)
        3. DuckDuckGo Instant Answers + Wikipedia (always available, no key needed)
        4. NewsAPI (if NEWS_API_KEY set and include_news=True or query is news-like)

    Args:
        query:        Search query string.
        max_results:  Maximum number of results to return.
        include_news: Also include NewsAPI results when key is available.

    Returns:
        List of dicts with keys: title, url, snippet, source.
        Empty list if all providers fail.
    """
    # Try best-quality providers first
    results = _tavily_search(query, max_results)
    if results:
        if include_news and NEWS_API_KEY:
            results += _news_api_search(query, 3)
        return results[:max_results + 3]

    results = _serp_search(query, max_results)
    if results:
        if include_news and NEWS_API_KEY:
            results += _news_api_search(query, 3)
        return results

    # Free fallback: DuckDuckGo + Wikipedia
    ddg = _ddg_instant(query)
    wiki = _wiki_search(query, max_results=2)
    results = ddg + wiki

    # Add news for news-like queries or if explicitly requested
    news_keywords = ("news", "latest", "recent", "today", "2024", "2025", "2026")
    if NEWS_API_KEY and (include_news or any(kw in query.lower() for kw in news_keywords)):
        results += _news_api_search(query, 3)

    return results[:max_results + 3]


def research(
    query: str,
    system_prompt: str = "",
    max_results: int = 5,
    include_news: bool = False,
) -> dict:
    """Search the web and synthesize results using AI.

    Combines search_web() with query_ai() to produce a single coherent answer
    from multiple web sources — useful when bots need up-to-date information.

    Args:
        query:         Research question or topic.
        system_prompt: Optional additional instructions for the AI synthesis step.
        max_results:   Maximum number of web results to fetch.
        include_news:  Include NewsAPI results if available.

    Returns:
        dict with keys:
            answer   (str)   — synthesized answer
            sources  (list)  — raw search results used
            provider (str)   — AI provider used for synthesis
            error    (str|None) — error if synthesis failed
    """
    sources = search_web(query, max_results=max_results, include_news=include_news)

    if not sources:
        # No web results — ask AI from training knowledge only
        result = query_ai(query, system_prompt=system_prompt or "You are a helpful research assistant.")
        return {
            "answer": result.get("answer", ""),
            "sources": [],
            "provider": result.get("provider", "error"),
            "error": result.get("error"),
        }

    # Format sources for AI synthesis
    context_parts = []
    for i, src in enumerate(sources[:max_results], 1):
        title = src.get("title", "")
        snippet = src.get("snippet", "")
        url = src.get("url", "")
        context_parts.append(f"[{i}] {title}\n{snippet}\nSource: {url}")
    context = "\n\n".join(context_parts)

    synthesis_prompt = (
        f"Research question: {query}\n\n"
        f"Web search results:\n{context}\n\n"
        "Based on the above sources, provide a comprehensive, accurate answer. "
        "Cite source numbers [1], [2], etc. where relevant. "
        "If the sources don't fully answer the question, note what is known vs uncertain."
    )
    sys_p = system_prompt or (
        "You are an expert research assistant. Synthesize web search results into "
        "clear, accurate, well-structured answers. Always note your sources."
    )

    result = query_ai(synthesis_prompt, system_prompt=sys_p)
    return {
        "answer": result.get("answer", ""),
        "sources": sources,
        "provider": result.get("provider", "error"),
        "error": result.get("error"),
    }
