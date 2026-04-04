"""Web Research Bot — autonomous web search and information synthesis.

Provides web research capability for the entire AI Employee system:

  1. Standalone use: send `research <query>` in chat to get researched answers.
  2. Cross-bot service: other agents post a request to the research_requests.json
     file and this bot processes it, writing results back for the requester.

Both uses leverage the ai_router search_web() + research() functions:
  - DuckDuckGo Instant Answers + Wikipedia (free, no key needed)
  - Tavily AI Search (best quality, requires TAVILY_API_KEY)
  - SerpAPI Google (requires SERP_API_KEY)
  - NewsAPI (requires NEWS_API_KEY)

Configuration (~/.ai-employee/config/web-researcher.env):
    WEB_RESEARCHER_POLL_INTERVAL  — chatlog poll interval in seconds (default: 5)
    WEB_RESEARCHER_MAX_RESULTS    — max web results per query (default: 5)
    WEB_RESEARCHER_SEARCH_TIMEOUT — search HTTP timeout (default: 15)
    TAVILY_API_KEY                — Tavily search key (optional, best quality)
    SERP_API_KEY                  — SerpAPI key (optional)
    NEWS_API_KEY                  — NewsAPI key (optional)

Cross-bot request format (~/.ai-employee/state/research_requests.json):
    [
      {
        "id": "unique-request-id",
        "query": "topic to research",
        "context": "optional context for the AI synthesis",
        "requester": "bot-name or user",
        "status": "pending",
        "created_at": "ISO timestamp"
      }
    ]

Results are appended to ~/.ai-employee/state/research_results.jsonl and also
written back to the request entry as "result" + "status": "done".
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "web-researcher.state.json"
REQUESTS_FILE = AI_HOME / "state" / "research_requests.json"
RESULTS_FILE = AI_HOME / "state" / "research_results.jsonl"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"

POLL_INTERVAL = int(os.environ.get("WEB_RESEARCHER_POLL_INTERVAL", "5"))
MAX_RESULTS = int(os.environ.get("WEB_RESEARCHER_MAX_RESULTS", "5"))

# ── AI router (web search + synthesis) ───────────────────────────────────────

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import research as _research_fn  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Chat log helpers ──────────────────────────────────────────────────────────

def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        lines = [l for l in CHATLOG.read_text().splitlines() if l.strip()]
        return [json.loads(l) for l in lines]
    except Exception:
        return []


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Research requests (cross-bot IPC) ─────────────────────────────────────────

def load_requests() -> list:
    if not REQUESTS_FILE.exists():
        return []
    try:
        return json.loads(REQUESTS_FILE.read_text())
    except Exception:
        return []


def save_requests(requests: list) -> None:
    REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REQUESTS_FILE.write_text(json.dumps(requests, indent=2))


def append_result(result: dict) -> None:
    """Append a completed research result to the results log."""
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(result) + "\n")


# ── Core research logic ───────────────────────────────────────────────────────

def do_research(query: str, context: str = "", include_news: bool = False) -> dict:
    """Perform web research and return a structured result dict."""
    if not _AI_AVAILABLE:
        return {
            "query": query,
            "answer": "AI router not available. Cannot perform research.",
            "sources": [],
            "provider": "error",
            "error": "ai_router import failed",
        }

    is_news_query = any(kw in query.lower() for kw in
                        ("news", "latest", "recent", "today", "2025", "2026", "breaking"))
    sys_prompt = (
        "You are a precise research assistant. Provide factual, well-sourced answers. "
        "If asked about recent events, prioritize the most current information available. "
        f"{context}" if context else
        "You are a precise research assistant. Provide factual, well-sourced answers."
    )

    try:
        result = _research_fn(
            query,
            system_prompt=sys_prompt,
            max_results=MAX_RESULTS,
            include_news=include_news or is_news_query,
        )
        return {
            "query": query,
            "answer": result.get("answer", "No answer generated."),
            "sources": result.get("sources", []),
            "provider": result.get("provider", "unknown"),
            "error": result.get("error"),
            "ts": now_iso(),
        }
    except Exception as exc:
        return {
            "query": query,
            "answer": f"Research failed: {exc}",
            "sources": [],
            "provider": "error",
            "error": str(exc),
            "ts": now_iso(),
        }


def _format_response(result: dict) -> str:
    """Format a research result for display in chat."""
    answer = result.get("answer", "No results.")
    sources = result.get("sources", [])
    provider = result.get("provider", "unknown")
    error = result.get("error")

    if error and not answer:
        return f"⚠️ Research failed: {error}"

    lines = [f"🔍 *Research: {result.get('query', '')}*\n"]
    lines.append(answer)

    # Add source list (up to 5)
    unique_sources = []
    seen_urls = set()
    for src in sources:
        url = src.get("url", "")
        title = src.get("title", "")
        if url and url not in seen_urls and title:
            unique_sources.append(f"  • [{title[:60]}]({url})")
            seen_urls.add(url)
        elif title and url not in seen_urls:
            unique_sources.append(f"  • {title[:60]}")
        if len(unique_sources) >= 5:
            break

    if unique_sources:
        lines.append("\n📚 *Sources:*")
        lines.extend(unique_sources)

    lines.append(f"\n_[research via {provider}]_")
    return "\n".join(lines)


# ── Process chatlog commands ──────────────────────────────────────────────────

def process_chatlog(last_processed_idx: int) -> int:
    """Scan chatlog for research commands and process them."""
    chatlog = load_chatlog()
    new_entries = chatlog[last_processed_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        message = entry.get("message", "").strip()
        msg_lower = message.lower()

        # Detect research commands
        query = None
        include_news = False
        if msg_lower.startswith("research "):
            query = message[9:].strip()
        elif msg_lower.startswith("find "):
            query = message[5:].strip()
        elif msg_lower.startswith("web search "):
            query = message[11:].strip()
        elif msg_lower.startswith("search web "):
            query = message[11:].strip()
        elif msg_lower.startswith("latest news ") or msg_lower.startswith("news about "):
            query = message.split(" ", 2)[-1].strip()
            include_news = True
        elif msg_lower.startswith("lookup "):
            query = message[7:].strip()
        elif msg_lower == "research status":
            _report_status()
            continue

        if not query:
            continue

        print(f"[{now_iso()}] web-researcher: researching '{query[:60]}'")
        result = do_research(query, include_news=include_news)
        response = _format_response(result)
        append_chatlog({"ts": now_iso(), "type": "bot", "message": response})
        append_result({**result, "requester": "user", "id": f"chat_{entry.get('ts',now_iso())}"})
        print(f"[{now_iso()}] web-researcher: done (provider={result.get('provider')})")

    return new_idx


def _report_status() -> None:
    """Post research bot status to chatlog."""
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    msg = (
        f"🔍 *Web Researcher Status*\n"
        f"  Status: {state.get('status', 'unknown')}\n"
        f"  Searches done: {state.get('total_searches', 0)}\n"
        f"  Active providers: {state.get('active_providers', 'unknown')}\n"
        f"  Commands: research <query>, find <topic>, web search <query>, "
        f"latest news <topic>, lookup <term>"
    )
    append_chatlog({"ts": now_iso(), "type": "bot", "message": msg})


# ── Process cross-bot requests ────────────────────────────────────────────────

def process_requests() -> int:
    """Process pending research requests from other agents."""
    requests = load_requests()
    pending = [r for r in requests if r.get("status") == "pending"]
    if not pending:
        return 0

    completed = 0
    for req in pending:
        req_id = req.get("id", "unknown")
        query = req.get("query", "").strip()
        if not query:
            req["status"] = "error"
            req["error"] = "Empty query"
            continue

        print(f"[{now_iso()}] web-researcher: bot request '{req_id}': '{query[:60]}'")
        result = do_research(query, context=req.get("context", ""), include_news=req.get("include_news", False))
        req["status"] = "done"
        req["result"] = result
        req["completed_at"] = now_iso()
        append_result({**result, "requester": req.get("requester", "bot"), "id": req_id})
        completed += 1
        print(f"[{now_iso()}] web-researcher: request '{req_id}' complete")

    if completed:
        save_requests(requests)
    return completed


# ── Main loop ─────────────────────────────────────────────────────────────────

def _detect_active_providers() -> list:
    """Detect which web search providers are active."""
    active = ["DuckDuckGo", "Wikipedia"]  # Always available
    if os.environ.get("TAVILY_API_KEY"):
        active.insert(0, "Tavily AI")
    if os.environ.get("SERP_API_KEY"):
        active.insert(0 if not os.environ.get("TAVILY_API_KEY") else 1, "SerpAPI")
    if os.environ.get("NEWS_API_KEY"):
        active.append("NewsAPI")
    return active


def main() -> None:
    active_providers = _detect_active_providers()
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router unavailable (install deps)"
    print(
        f"[{now_iso()}] web-researcher started; poll={POLL_INTERVAL}s; "
        f"max_results={MAX_RESULTS}; {ai_status}; providers: {', '.join(active_providers)}"
    )

    last_idx = len(load_chatlog())
    total_searches = 0

    write_state({
        "bot": "web-researcher",
        "ts": now_iso(),
        "status": "starting",
        "active_providers": ", ".join(active_providers),
        "total_searches": total_searches,
    })

    while True:
        # Process chat commands
        new_idx = process_chatlog(last_idx)
        searches_this_cycle = new_idx - last_idx
        last_idx = new_idx

        # Process cross-bot requests
        bot_searches = process_requests()
        total_searches += searches_this_cycle + bot_searches

        write_state({
            "bot": "web-researcher",
            "ts": now_iso(),
            "status": "running",
            "active_providers": ", ".join(active_providers),
            "total_searches": total_searches,
            "ai_available": _AI_AVAILABLE,
            "note": (
                "Commands: research <query> | find <topic> | web search <query> | "
                "latest news <topic> | lookup <term>"
            ),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
