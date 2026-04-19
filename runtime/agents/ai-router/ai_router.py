"""AI Router — Two-layer AI routing: free/local first, paid cloud fallback.

Routing Architecture (two layers, always enforced by default):

  ┌─ LAYER 1 — Free / Local (always tried first) ───────────────────────────┐
  │  1a. Ollama  (local, completely free, private, no API key needed)        │
  │  1b. Gemma   (Google open-source — via Ollama or Google AI Studio free)  │
  │  1c. NVIDIA NIM  (free-tier cloud — Nemotron / Qwen / Llama 8B)         │
  └─────────────────────────────────────────────────────────────────────────┘
  ┌─ LAYER 2 — Paid Cloud (only if Layer 1 fully unavailable) ──────────────┐
  │  2a. Anthropic Claude  (costs tokens — preferred for analytics tasks)    │
  │  2b. OpenAI GPT-4o  (costs tokens — preferred for sales/persuasion)     │
  └─────────────────────────────────────────────────────────────────────────┘

Set LOCAL_AI_FIRST=0 to disable and use preferred-provider-first routing instead.

Per-agent model routing (query_ai_for_agent):
  - reasoning      → Layer 1c: NVIDIA Nemotron (deep logic, complex analysis)
  - orchestrator   → Layer 1c: NVIDIA Nemotron (multi-agent planning, synthesis)
  - coding         → Layer 1c: NVIDIA Qwen Coder (code generation, review)
  - bulk           → Layer 1c: NVIDIA Llama 8B (fast, high-volume tasks)
  - general/local  → Layer 1a: Ollama (free, privacy-preserving)
  - creative       → Layer 1b: Gemma (creative writing, content generation)
  - analytics/data → Layer 2a: Anthropic Claude (only if Layer 1 fails)
  - research       → Layer 2a: Anthropic Claude (only if Layer 1 fails)
  - sales          → Layer 2b: OpenAI GPT-4o (only if Layer 1 fails)

Auto-model selection (classify_task / query_ai_auto):
  Automatically classifies prompts into task categories and routes to the
  best available provider without manual agent_type specification.

Sub-agent provider inheritance (ACTIVE_AI_PROVIDER):
  Set ACTIVE_AI_PROVIDER=gemma|ollama|nvidia_nim|anthropic|openai to force
  all sub-agents to use the same provider as the selected main AI.

Batch processing (query_ai_batch):
  Sends multiple prompts to Ollama concurrently (ThreadPoolExecutor), minimising
  latency and cloud API usage.  Each prompt that Ollama cannot handle falls back
  individually through the standard Anthropic → OpenAI chain.

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
    sys.path.insert(0, str(AI_HOME / "agents" / "ai-router"))
    from ai_router import query_ai, query_ai_for_agent, query_ai_batch, query_ai_auto, search_web

    result = query_ai("Explain quantum computing in simple terms")
    print(result["answer"])    # the response text
    print(result["provider"])  # "ollama" | "gemma" | "nvidia_nim" | "anthropic" | "openai" | "error"

    # Auto-routing: classifies task and picks the best model automatically
    result = query_ai_auto("Write me a Python function to sort a list")
    print(result["answer"], result["task_type"])  # e.g. task_type="coding"

    # Agent-aware routing (LOCAL_AI_FIRST=1 by default):
    #   Always tries Ollama → Gemma → NIM first, then preferred cloud provider.
    result = query_ai_for_agent("sales", "Write a cold email for a SaaS product")
    result = query_ai_for_agent("analytical", "Analyse this dataset...", history=[...])
    result = query_ai_for_agent("coding", "Write a Python function to parse JSON")
    result = query_ai_for_agent("reasoning", "Analyse this complex business scenario...")
    print(result["answer"])

    # Batch: process many prompts concurrently via local Ollama
    results = query_ai_batch(["Summarise topic A", "Summarise topic B", "Summarise topic C"])
    for r in results:
        print(r["answer"], r["provider"])

    hits = search_web("latest AI news 2025")
    for h in hits:
        print(h["title"], h["url"], h["snippet"])

Environment variables (loaded from ~/.ai-employee/.env):
    LOCAL_AI_FIRST           — "1" (default) = always try free/local before paid cloud
    OLLAMA_HOST              — Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL             — model name (default: llama3.2)
    OLLAMA_TIMEOUT           — request timeout in seconds (default: 60)
    OLLAMA_BATCH_MAX_WORKERS — max concurrent Ollama workers for query_ai_batch (default: 4)
    GEMMA_MODEL              — Gemma model name for Ollama (default: gemma3)
    GEMMA_VIA_OLLAMA         — "1" (default) = run Gemma through local Ollama
    GOOGLE_API_KEY           — Google AI Studio key for Gemma cloud fallback (free tier)
    GEMMA_CLOUD_MODEL        — Gemma model via Google AI Studio (default: gemma-3-27b-it)
    ACTIVE_AI_PROVIDER       — force all sub-agents to use this provider
                               (ollama|gemma|nvidia_nim|anthropic|openai — empty=auto)
    NVIDIA_API_KEY           — NVIDIA NIM API key (free-tier cloud models)
    NIM_REASONING_MODEL      — reasoning model (default: nvidia/llama-3.3-nemotron-super-49b-v1)
    NIM_CODING_MODEL         — coding model    (default: qwen/qwen2.5-coder-32b-instruct)
    NIM_BULK_MODEL           — bulk model      (default: meta/llama-3.1-8b-instruct)
    ANTHROPIC_API_KEY        — Anthropic key (optional cloud fallback)
    CLAUDE_MODEL             — Claude model name (default: claude-opus-4-6)
    OPENAI_API_KEY           — OpenAI key (optional last-resort fallback)
    OPENAI_MODEL             — OpenAI model name (default: gpt-4o-mini)
    OPENAI_SALES_MODEL       — OpenAI model for sales agents (default: gpt-4o)
    CLOUD_AI_TIMEOUT         — cloud request timeout in seconds (default: 30)
    TAVILY_API_KEY           — Tavily AI search key (optional, best quality)
    SERP_API_KEY             — SerpAPI key (optional)
    NEWS_API_KEY             — NewsAPI key (optional, for news searches)
    WEB_SEARCH_TIMEOUT       — web search timeout in seconds (default: 15)
"""
import concurrent.futures
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ai_router")

# ── Hybrid Mode integration (optional — graceful fallback if not present) ────
_hybrid_mode = None
try:
    _hm_path = Path(__file__).parent
    if str(_hm_path) not in sys.path:
        sys.path.insert(0, str(_hm_path))
    import hybrid_mode as _hybrid_mode  # type: ignore[import]
    logger.debug("ai_router: hybrid_mode loaded — Dual-Mode Architecture active")
except Exception:
    _hybrid_mode = None


def _is_online() -> bool:
    """Return True if the system is effectively online (internet reachable).

    Delegates to hybrid_mode.is_online() when available; falls back to True
    so that existing behaviour is preserved when the module is absent.
    Also respects TurboQuant offline mode when turbo_quant is loaded.
    """
    if _turbo_quant is not None:
        try:
            if _turbo_quant.is_offline_mode():
                return False
        except Exception:
            pass
    if _hybrid_mode is not None:
        try:
            return _hybrid_mode.is_online()
        except Exception:
            pass
    return True


def _record_cloud_failure(provider: str = "") -> None:
    """Signal a cloud provider network failure to the hybrid mode controller."""
    if _hybrid_mode is not None:
        try:
            _hybrid_mode.record_provider_failure(provider)
        except Exception:
            pass


# ── Turbo Quantization integration (optional — graceful fallback if not present) ─
_turbo_quant = None
try:
    _tq_path = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee"))) / "agents" / "turbo-quant"
    if _tq_path.exists() and str(_tq_path) not in sys.path:
        sys.path.insert(0, str(_tq_path))
    import turbo_quant as _turbo_quant  # type: ignore[import]
    logger.debug("ai_router: turbo_quant loaded — Turbo Mode active")
except Exception:
    _turbo_quant = None

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

# ── Google Gemma (free local open-source AI) ──────────────────────────────────
# Primary: run Gemma through local Ollama (ollama pull gemma4).
# Fallback: Google AI Studio free-tier API (GOOGLE_API_KEY required).
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma4")
GEMMA_VIA_OLLAMA: bool = os.environ.get("GEMMA_VIA_OLLAMA", "1").strip().lower() not in ("0", "false", "no")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMMA_CLOUD_MODEL = os.environ.get("GEMMA_CLOUD_MODEL", "gemma-3-27b-it")
GEMMA_TIMEOUT = int(os.environ.get("GEMMA_TIMEOUT", "120"))

# ── Sub-agent provider inheritance ───────────────────────────────────────────
# When set, ALL sub-agents will use this provider instead of their default.
# Valid values: "ollama" | "gemma" | "nvidia_nim" | "anthropic" | "openai" | ""
ACTIVE_AI_PROVIDER: str = os.environ.get("ACTIVE_AI_PROVIDER", "").strip().lower()

# ── NVIDIA NIM (free-tier cloud models) ───────────────────────────────────────
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
NIM_REASONING_MODEL = os.environ.get(
    "NIM_REASONING_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"
)
NIM_CODING_MODEL = os.environ.get("NIM_CODING_MODEL", "qwen/qwen2.5-coder-32b-instruct")
NIM_BULK_MODEL = os.environ.get("NIM_BULK_MODEL", "meta/llama-3.1-8b-instruct")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MODEL_SALES = os.environ.get("OPENAI_MODEL_SALES", "gpt-4o")
OPENAI_MODEL_CREATIVE = os.environ.get("OPENAI_MODEL_CREATIVE", "gpt-4o")

CLOUD_AI_TIMEOUT = int(os.environ.get("CLOUD_AI_TIMEOUT", "30"))

# Always try local Ollama before cloud providers (default: enabled).
# Set LOCAL_AI_FIRST=0 in .env to restore preferred-provider-first behaviour.
LOCAL_AI_FIRST: bool = os.environ.get("LOCAL_AI_FIRST", "1").strip().lower() not in ("0", "false", "no")

# Maximum concurrent Ollama workers used by query_ai_batch().
OLLAMA_BATCH_MAX_WORKERS: int = int(os.environ.get("OLLAMA_BATCH_MAX_WORKERS", "4"))

# ── Turbo Mode (MONEY | POWER | AUTO) ────────────────────────────────────────
# When turbo_quant is available the active mode is read from it.
# Otherwise TURBO_MODE env var is used directly.
# MONEY  → smallest quantized local models (fastest, lowest cost)
# POWER  → largest / best-quality models (higher latency, higher cost)
# AUTO   → picks automatically based on task complexity (default)
def _turbo_mode() -> str:
    """Return the current Turbo Mode string."""
    if _turbo_quant is not None:
        try:
            return _turbo_quant.get_mode()
        except Exception:
            pass
    return os.environ.get("TURBO_MODE", "AUTO").upper()

# ── Per-agent model routing ───────────────────────────────────────────────────
# Maps agent categories and IDs to their preferred AI provider + model.
# Provider values: "openai" | "anthropic" | "ollama" | "nvidia_nim"
_AGENT_ROUTING: dict = {
    # Sales & persuasion agents → GPT-4o (best at persuasive, human-like copy)
    "sales": {"provider": "openai", "model_env": "OPENAI_SALES_MODEL", "default_model": "gpt-4o"},
    # Creative agents → Gemma (strong at creative writing, free and local)
    "creative": {"provider": "gemma", "model_env": "GEMMA_MODEL", "default_model": "gemma3"},
    # Analytics & research agents → Claude (superior at long-context analysis)
    "analytics": {"provider": "anthropic", "model_env": "CLAUDE_MODEL", "default_model": "claude-opus-4-6"},
    # Research category also → Claude
    "research": {"provider": "anthropic", "model_env": "CLAUDE_MODEL", "default_model": "claude-opus-4-6"},
    # Reasoning tasks → NVIDIA Nemotron (deep logic, complex analysis, free-tier)
    "reasoning": {
        "provider": "nvidia_nim",
        "model_env": "NIM_REASONING_MODEL",
        "default_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
    },
    # Orchestrator / multi-agent planning → NVIDIA Nemotron (synthesis, planning)
    "orchestrator": {
        "provider": "nvidia_nim",
        "model_env": "NIM_REASONING_MODEL",
        "default_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
    },
    # Coding tasks → NVIDIA Qwen Coder (code generation, review, debugging)
    "coding": {
        "provider": "nvidia_nim",
        "model_env": "NIM_CODING_MODEL",
        "default_model": "qwen/qwen2.5-coder-32b-instruct",
    },
    # Bulk/simple tasks → NVIDIA Llama 8B (fast, low-latency, high-volume)
    "bulk": {
        "provider": "nvidia_nim",
        "model_env": "NIM_BULK_MODEL",
        "default_model": "meta/llama-3.1-8b-instruct",
    },
    # General / all others → Ollama (local, free, private)
    "general": {"provider": "ollama", "model_env": "OLLAMA_MODEL", "default_model": "llama3.2"},
}

# Explicit per-agent-ID overrides (take priority over category routing)
_AGENT_ID_ROUTING: dict = {
    # ── Lead intelligence pipeline ─────────────────────────────────────────
    "lead-hunter":          "sales",       # outbound prospect hunting
    "lead-hunter-agent":    "reasoning",   # ICP reasoning & vector dedup
    "lead-scoring-agent":   "reasoning",   # embed + rerank scoring
    "outreach-agent":       "sales",       # Nemotron-personalized messages
    "deal-matching-agent":  "reasoning",   # compatibility + clustering
    # ── Sales & persuasion ────────────────────────────────────────────────
    "email-ninja":              "sales",
    "web-sales":                "sales",
    "email-marketer":           "sales",
    "cold-outreach-assassin":   "sales",   # cold-email copy
    "sales-closer-pro":         "sales",   # closing scripts
    "lead-hunter-elite":        "sales",   # hunter outreach copy
    "appointment-setter":       "sales",   # booking / scheduling
    "offer-agent":              "sales",   # offer creation
    "referral-rocket":          "sales",   # referral campaign copy
    "qualification-agent":      "sales",   # lead qualification dialogue
    "signal-community":         "sales",   # community-based outreach
    "linkedin-growth-hacker":   "sales",   # LinkedIn outreach
    "follow-up-agent":          "sales",   # follow-up sequences
    # ── Creative content ──────────────────────────────────────────────────
    "ad-campaign-wizard":   "creative",    # ad creative & copy
    "brand-strategist":     "creative",    # brand identity & narrative
    "social-media-manager": "creative",    # social posts & campaigns
    "newsletter-bot":       "creative",    # newsletter content
    "course-creator":       "creative",    # educational content
    "creator-agency":       "creative",    # content creation
    "faceless-video":       "creative",    # video scripts
    "print-on-demand":      "creative",    # product design concepts
    "memecoin-creator":     "creative",    # meme & viral content
    "ui-designer":          "creative",    # UI/UX concepts & copy
    # ── Analytics & data ──────────────────────────────────────────────────
    "finance-wizard":           "analytics",   # financial modelling
    "conversion-rate-optimizer":"analytics",   # CRO data analysis
    "skills-manager":           "analytics",   # skills gap analysis
    "growth-hacker":            "analytics",   # growth metrics
    "ecom-agent":               "analytics",   # ecommerce analytics
    "arbitrage-bot":            "analytics",   # market data analysis
    "hr-manager":               "analytics",   # HR metrics & decisions
    "paid-media-specialist":    "analytics",   # media-spend analysis
    "ecom-dashboard":           "analytics",
    "data-analyst":             "analytics",
    "intel-agent":              "analytics",
    # ── Research ──────────────────────────────────────────────────────────
    "discovery":              "research",   # skill / agent gap research
    "partnership-matchmaker": "research",   # partner & market research
    "financial-deepsearch":   "research",   # Dexter AI financial deep-search
    # ── Reasoning / planning ──────────────────────────────────────────────
    "company-builder":  "reasoning",   # business strategy
    "project-manager":  "reasoning",   # project planning
    # ── Orchestrator ─────────────────────────────────────────────────────
    "task-orchestrator": "orchestrator",  # multi-agent synthesis
    "orchestrator":      "orchestrator",
    # ── Problem-solving UI ────────────────────────────────────────────────
    "problem-solver-ui": "reasoning",     # catch-all assistant queries
    # ── Coding ────────────────────────────────────────────────────────────
    "engineering-assistant": "coding",    # engineering / code tasks
    "qa-tester":             "coding",    # QA & test generation
    "chatbot-builder":       "coding",    # chatbot logic & code
    "obsidian-memory":       "coding",    # Obsidian vault knowledge base
    # ── Hermes autonomous agent ───────────────────────────────────────────
    "hermes-agent":  "reasoning",   # autonomous pipeline orchestrator
    "hermes":        "reasoning",
    # ── General / local ───────────────────────────────────────────────────
    "recruiter": "general",   # HR recruiting (broad, free)
    # ── BLACKLIGHT autonomous agent ───────────────────────────────────────
    "blacklight": "orchestrator",  # autonomous loop — planning + reasoning
}


def _route_for_agent(agent_id: Optional[str], category: Optional[str]) -> dict:
    """Return the routing config for the given agent_id or category."""
    if agent_id and agent_id in _AGENT_ID_ROUTING:
        key = _AGENT_ID_ROUTING[agent_id]
        return _AGENT_ROUTING.get(key, _AGENT_ROUTING["general"])
    if category and category in _AGENT_ROUTING:
        return _AGENT_ROUTING[category]
    return _AGENT_ROUTING["general"]

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


def _try_ollama(prompt: str, system_prompt: str, history: list, model: Optional[str] = None) -> Optional[dict]:
    """Attempt to get a response from the local Ollama instance."""
    try:
        import requests  # lightweight stdlib-like dep already used by ollama-agent

        use_model = model or OLLAMA_MODEL
        messages = _build_messages(prompt, system_prompt, history)
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": use_model, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("message", {}).get("content", "").strip()
        if answer:
            logger.debug("ai_router: used Ollama (%s)", use_model)
            return {
                "answer": answer,
                "provider": "ollama",
                "model": use_model,
                "error": None,
            }
    except Exception as exc:
        logger.debug("ai_router: Ollama unavailable — %s", exc)
    return None


def _try_gemma(
    prompt: str,
    system_prompt: str,
    history: list,
    model: Optional[str] = None,
) -> Optional[dict]:
    """Attempt to get a response from a Google Gemma model.

    Two backends are tried in order:
      1. Ollama local (GEMMA_VIA_OLLAMA=1, default) — uses GEMMA_MODEL via the
         already-running Ollama server.  Run: ``ollama pull gemma3``
      2. Google AI Studio REST API (free tier) — requires GOOGLE_API_KEY from
         https://aistudio.google.com/app/apikey
    """
    use_model = model or GEMMA_MODEL

    # ── 1. Gemma via local Ollama ──────────────────────────────────────────────
    if GEMMA_VIA_OLLAMA:
        result = _try_ollama(prompt, system_prompt, history, model=use_model)
        if result:
            # Re-label provider so callers can distinguish Gemma from generic Ollama
            result["provider"] = "gemma"
            logger.debug("ai_router: used Gemma/%s (via Ollama)", use_model)
            return result

    # ── 2. Google AI Studio (free-tier REST API) ────────────────────────────────
    if not GOOGLE_API_KEY:
        return None
    try:
        cloud_model = GEMMA_CLOUD_MODEL
        messages = _build_messages(prompt, system_prompt, history)
        # Convert OpenAI-style messages to Gemini content format
        contents = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                # Google AI Studio doesn't have a system role in basic REST —
                # prepend as first user turn with a model ack.
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
                contents.append({"role": "model", "parts": [{"text": "Understood."}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg["content"]}]})
            else:
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})

        payload = json.dumps({"contents": contents}).encode("utf-8")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cloud_model}:generateContent?key={GOOGLE_API_KEY}"
        )
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "AI-Employee/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=GEMMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))

        answer = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        if answer:
            logger.debug("ai_router: used Gemma/%s (Google AI Studio)", cloud_model)
            return {
                "answer": answer,
                "provider": "gemma",
                "model": cloud_model,
                "error": None,
                "usage": None,
            }
    except Exception as exc:
        logger.debug("ai_router: Gemma (Google AI Studio) unavailable — %s", exc)
    return None


def _try_nvidia_nim(
    prompt: str,
    system_prompt: str,
    history: list,
    model: Optional[str] = None,
) -> Optional[dict]:
    """Attempt to get a response from NVIDIA NIM (free-tier cloud models).

    Uses the NIM client from runtime/agents/nvidia-nim/nim_client.py when
    available; falls back to a direct urllib call so the router never requires
    nim_client to be installed.

    Model selection (if model is None):
      - Defaults to NIM_REASONING_MODEL (Nemotron) for general queries.
      - Callers can pass NIM_CODING_MODEL or NIM_BULK_MODEL explicitly.

    Skipped entirely when the system is in offline mode.
    """
    if not NVIDIA_API_KEY:
        return None
    if not _is_online():
        logger.debug("ai_router: offline — skipping NVIDIA NIM")
        return None

    use_model = model or NIM_REASONING_MODEL

    # Try nim_client (preferred — handles rate-limit retries)
    _nim_dir = Path(__file__).parent.parent / "nvidia-nim"
    if str(_nim_dir) not in sys.path:
        sys.path.insert(0, str(_nim_dir))
    try:
        from nim_client import NIMClient  # type: ignore
        client = NIMClient(api_key=NVIDIA_API_KEY)
        result = client.chat(
            prompt,
            system_prompt=system_prompt,
            history=history,
            model=use_model,
        )
        if result.get("answer"):
            logger.debug("ai_router: used NVIDIA NIM/%s (via nim_client)", use_model)
            return result
        return None
    except ImportError:
        pass  # nim_client not yet in path — fall through to direct call
    except Exception as exc:
        logger.debug("ai_router: nim_client failed — %s", exc)
        return None

    # Direct urllib fallback (no external deps)
    try:
        messages = _build_messages(prompt, system_prompt, history)
        payload = json.dumps({
            "model": use_model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.7,
            "stream": False,
        }).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AI-Employee/1.0",
        }
        req = urllib.request.Request(
            f"{NIM_BASE_URL}/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=CLOUD_AI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        answer = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        logger.debug("ai_router: used NVIDIA NIM/%s (direct)", use_model)
        return {
            "answer": answer,
            "provider": "nvidia_nim",
            "model": use_model,
            "error": None,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
        }
    except Exception as exc:
        logger.debug("ai_router: NVIDIA NIM unavailable — %s", exc)
        _record_cloud_failure("nvidia_nim")
    return None


def _try_anthropic(prompt: str, system_prompt: str, history: list, model: Optional[str] = None) -> Optional[dict]:
    """Attempt to get a response from Anthropic Claude (cloud fallback).

    Skipped entirely when the system is in offline mode.
    """
    if not ANTHROPIC_API_KEY:
        return None
    if not _is_online():
        logger.debug("ai_router: offline — skipping Anthropic")
        return None
    try:
        import anthropic

        use_model = model or CLAUDE_MODEL
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        messages = list(history) if history else []
        messages.append({"role": "user", "content": prompt})
        response = client.messages.create(
            model=use_model,
            max_tokens=4096,
            system=system_prompt or "You are a helpful AI assistant.",
            messages=messages,
        )
        answer = response.content[0].text.strip()
        logger.debug("ai_router: used Anthropic Claude (%s)", use_model)
        return {
            "answer": answer,
            "provider": "anthropic",
            "model": use_model,
            "error": None,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }
    except Exception as exc:
        logger.debug("ai_router: Anthropic unavailable — %s", exc)
        _record_cloud_failure("anthropic")
    return None


def _try_openai(prompt: str, system_prompt: str, history: list, model: Optional[str] = None) -> Optional[dict]:
    """Attempt to get a response from OpenAI (last-resort cloud fallback).

    Skipped entirely when the system is in offline mode.
    """
    if not OPENAI_API_KEY:
        return None
    if not _is_online():
        logger.debug("ai_router: offline — skipping OpenAI")
        return None
    try:
        import openai

        use_model = model or OPENAI_MODEL
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        messages = _build_messages(prompt, system_prompt, history)
        response = client.chat.completions.create(
            model=use_model,
            messages=messages,
            max_tokens=4096,
            timeout=CLOUD_AI_TIMEOUT,
        )
        answer = response.choices[0].message.content.strip()
        logger.debug("ai_router: used OpenAI (%s)", use_model)
        return {
            "answer": answer,
            "provider": "openai",
            "model": use_model,
            "error": None,
            "usage": {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
        }
    except Exception as exc:
        logger.debug("ai_router: OpenAI unavailable — %s", exc)
        _record_cloud_failure("openai")
    return None


def _try_forced_provider(
    provider: str,
    prompt: str,
    system_prompt: str,
    history: list,
) -> dict:
    """Try only the specified provider (used for sub-agent inheritance).

    When ACTIVE_AI_PROVIDER is set, every call in the system — including
    sub-agents — will be routed through this single provider.  If it fails,
    the standard fallback chain is used so the system never goes silent.
    """
    provider = provider.strip().lower()
    result: Optional[dict] = None
    if provider == "ollama":
        result = _try_ollama(prompt, system_prompt, history)
    elif provider == "gemma":
        result = _try_gemma(prompt, system_prompt, history)
    elif provider == "nvidia_nim":
        result = _try_nvidia_nim(prompt, system_prompt, history)
    elif provider == "anthropic":
        result = _try_anthropic(prompt, system_prompt, history)
    elif provider == "openai":
        result = _try_openai(prompt, system_prompt, history)
    if result:
        return result
    # Forced provider unavailable — fall through to standard chain without
    # ACTIVE_AI_PROVIDER so we don't recurse infinitely.
    logger.debug("ai_router: forced provider=%s unavailable, using standard fallback", provider)
    for fn in (_try_ollama, _try_gemma, _try_nvidia_nim, _try_anthropic, _try_openai):
        r = fn(prompt, system_prompt, history)
        if r:
            return r
    return _error_response()


# ── Task classifier — auto-select the best provider ──────────────────────────

_TASK_KEYWORDS: dict = {
    "coding": [
        "code", "function", "script", "program", "debug", "bug", "error", "fix",
        "python", "javascript", "java", "typescript", "golang", "rust", "sql",
        "api", "class", "module", "import", "compile", "test", "unit test",
        "refactor", "algorithm", "data structure", "regex",
    ],
    "creative": [
        "write", "story", "poem", "creative", "novel", "fiction", "blog post",
        "article", "essay", "lyrics", "script", "narrative", "character",
        "caption", "slogan", "tagline", "ad copy", "social media post",
    ],
    "analytics": [
        "analyse", "analyze", "data", "statistics", "metrics", "chart", "graph",
        "trend", "forecast", "model", "predict", "correlation", "regression",
        "dashboard", "report", "kpi", "benchmark", "compare",
    ],
    "reasoning": [
        "reason", "logic", "explain why", "evaluate", "assess", "strategy",
        "plan", "decide", "trade-off", "pros and cons", "complex", "scenario",
        "hypothesis", "argue", "debate", "critique",
    ],
    "research": [
        "research", "find", "search", "summarise", "summarize", "overview",
        "what is", "who is", "history of", "define", "news", "latest",
        "information about", "tell me about",
    ],
    "sales": [
        "sell", "sales", "cold email", "outreach", "pitch", "proposal",
        "persuade", "convince", "customer", "lead", "prospect", "conversion",
        "follow up", "close", "deal", "offer",
    ],
}


def classify_task(prompt: str) -> str:
    """Classify a prompt into a task category for optimal model routing.

    Uses keyword heuristics to categorise the prompt.  Returns one of:
      "coding" | "creative" | "analytics" | "reasoning" | "research" |
      "sales" | "general"

    This is intentionally lightweight — no external calls, runs in microseconds.
    """
    text = prompt.lower()
    scores: dict[str, int] = {category: 0 for category in _TASK_KEYWORDS}
    for category, keywords in _TASK_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[category] += 1
    best = max(scores, key=lambda category: scores[category])
    if scores[best] == 0:
        return "general"
    return best


def query_ai_auto(
    prompt: str,
    system_prompt: str = "",
    history: Optional[list] = None,
) -> dict:
    """Auto-classify the prompt and route to the best available provider.

    Calls ``classify_task()`` to determine the task type, then delegates to
    ``query_ai_for_agent()`` with that type so the best model is selected
    automatically.

    Returns the standard query_ai() dict plus an extra ``task_type`` key
    indicating the detected category.
    """
    task_type = classify_task(prompt)
    logger.debug("ai_router: query_ai_auto classified task as '%s'", task_type)
    result = query_ai_for_agent(task_type, prompt, system_prompt=system_prompt, history=history)
    result["task_type"] = task_type
    return result


def _turbo_log(result: dict, cfg, prompt: str) -> None:
    """Log one inference event to TurboQuant when the module is available.

    Silently skips when turbo_quant is not loaded or logging fails.
    """
    if _turbo_quant is None:
        return
    try:
        provider = result.get("provider", "")
        model    = result.get("model", "")
        error    = result.get("error") or ""
        quant    = cfg.quant    if cfg is not None else ""
        category = cfg.category if cfg is not None else "general"
        mode     = cfg.mode     if cfg is not None else ""
        # Rough token estimate when usage dict is not available
        usage    = result.get("usage") or {}
        prompt_tokens   = usage.get("prompt_tokens",     max(1, len(prompt.split())))
        response_tokens = usage.get("completion_tokens", max(1, len(result.get("answer", "").split())))
        _turbo_quant.log_inference(
            agent_id        = "ai_router",
            task_category   = category,
            mode            = mode,
            model           = model,
            quant           = quant,
            provider        = provider,
            prompt_tokens   = prompt_tokens,
            response_tokens = response_tokens,
            error           = error,
        )
        logger.debug(
            "ai_router: TurboQuant logged inference provider=%s model=%s quant=%s",
            provider, model, quant,
        )
    except Exception as exc:
        logger.debug("ai_router: turbo_quant.log_inference failed — %s", exc)


def query_ai(
    prompt: str,
    system_prompt: str = "",
    history: Optional[list] = None,
) -> dict:
    """Route an AI query through providers in two-layer priority order.

    LAYER 1 — Free / Local (always tried first):
        1a. Ollama  (local model, completely free, privacy-preserving)
        1b. Gemma   (Google open-source — via Ollama or Google AI Studio free)
        1c. NVIDIA NIM  (free-tier cloud — Nemotron reasoning model)

    LAYER 2 — Paid Cloud (only if Layer 1 fully unavailable):
        2a. Anthropic Claude  (cloud, costs tokens)
        2b. OpenAI GPT  (cloud, costs tokens — last resort)

    If ACTIVE_AI_PROVIDER is set, only that provider is tried (sub-agent
    inheritance: all agents follow the same provider as the main AI).

    TurboQuant integration: when turbo_quant is available, selects the optimal
    quantized Ollama model for the task and logs each inference event.

    Args:
        prompt: The user message or question.
        system_prompt: Optional system/role instructions for the AI.
        history: Optional list of previous messages in OpenAI chat format,
                 e.g. [{"role": "user", "content": "..."}, {"role": "assistant", ...}]

    Returns:
        dict with keys:
            answer   (str)  — AI response text, empty string on failure
            provider (str)  — "ollama" | "gemma" | "nvidia_nim" | "anthropic" | "openai" | "error"
            model    (str)  — model identifier used
            error    (str|None) — error description if all providers failed
            usage    (dict|None) — token usage for cloud providers
    """
    history = history or []

    # ── TurboQuant: select optimal model config for this query ────────────────
    _tq_cfg = None
    if _turbo_quant is not None:
        try:
            _tq_cfg = _turbo_quant.select_model(task=prompt, category="general")
            logger.debug(
                "ai_router: TurboQuant selected model=%s quant=%s provider=%s",
                _tq_cfg.model, _tq_cfg.quant, _tq_cfg.provider,
            )
        except Exception as exc:
            logger.debug("ai_router: turbo_quant.select_model failed — %s", exc)
            _tq_cfg = None

    # ── Provider inheritance: force a single provider for all sub-agents ─────
    if ACTIVE_AI_PROVIDER:
        result = _try_forced_provider(ACTIVE_AI_PROVIDER, prompt, system_prompt, history)
        _turbo_log(result, _tq_cfg, prompt)
        return result

    # ── Layer 1: Free / Local ─────────────────────────────────────────────────
    # 1a. Ollama — use TurboQuant model when available and provider is ollama
    _tq_ollama_model = (
        _tq_cfg.model
        if (_tq_cfg is not None and _tq_cfg.provider == "ollama")
        else None
    )
    result = _try_ollama(prompt, system_prompt, history, model=_tq_ollama_model)
    if result:
        _turbo_log(result, _tq_cfg, prompt)
        return result

    # 1b. Gemma (local via Ollama or Google AI Studio free tier)
    result = _try_gemma(prompt, system_prompt, history)
    if result:
        _turbo_log(result, _tq_cfg, prompt)
        return result

    # 1c. NVIDIA NIM (free-tier cloud — Nemotron reasoning model)
    result = _try_nvidia_nim(prompt, system_prompt, history)
    if result:
        _turbo_log(result, _tq_cfg, prompt)
        return result

    # ── Layer 2: Paid Cloud ───────────────────────────────────────────────────
    logger.debug("ai_router: Layer 1 (free/local) unavailable — trying paid cloud providers")

    # 2a. Anthropic Claude
    result = _try_anthropic(prompt, system_prompt, history)
    if result:
        _turbo_log(result, _tq_cfg, prompt)
        return result

    # 2b. OpenAI (last resort)
    result = _try_openai(prompt, system_prompt, history)
    if result:
        _turbo_log(result, _tq_cfg, prompt)
        return result

    # All providers failed
    error_result = {
        "answer": "",
        "provider": "error",
        "model": "",
        "error": (
            "No AI provider available. "
            "Start Ollama (`ollama serve` then `ollama pull gemma3`), "
            "set GOOGLE_API_KEY, NVIDIA_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY "
            "in ~/.ai-employee/.env and restart."
        ),
        "usage": None,
    }
    _turbo_log(error_result, _tq_cfg, prompt)
    return error_result


def is_ollama_available() -> bool:
    """Quick check whether the local Ollama instance is reachable."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def query_ai_batch(
    prompts: list,
    system_prompt: str = "",
    history: Optional[list] = None,
    max_workers: Optional[int] = None,
) -> list:
    """Process a list of prompts concurrently using local AI (Ollama) first.

    Sends all prompts to Ollama in parallel via a thread pool, maximising
    throughput and local AI utilisation.  Any prompt for which Ollama is
    unavailable or returns an empty answer falls back individually through
    the standard cloud provider chain (Anthropic → OpenAI), keeping external
    API usage to the minimum necessary.

    Args:
        prompts:      List of prompt strings to process.
        system_prompt: Optional system instructions applied to every prompt.
        history:      Optional conversation history applied to every prompt.
        max_workers:  Max concurrent Ollama workers.  Defaults to the
                      OLLAMA_BATCH_MAX_WORKERS env var (default: 4).

    Returns:
        List of result dicts (same structure as query_ai()), one per input
        prompt, in the same order as the input list.
    """
    if not prompts:
        return []

    workers = max_workers if max_workers and max_workers > 0 else OLLAMA_BATCH_MAX_WORKERS
    hist = history or []

    def _process_one(prompt: str) -> dict:
        # Honour ACTIVE_AI_PROVIDER for batch items too
        if ACTIVE_AI_PROVIDER:
            return _try_forced_provider(ACTIVE_AI_PROVIDER, prompt, system_prompt, hist)
        # Always try local free providers first for every item in the batch
        result = _try_ollama(prompt, system_prompt, hist)
        if result:
            return result
        result = _try_gemma(prompt, system_prompt, hist)
        if result:
            return result
        # Per-item cloud fallback: Anthropic → OpenAI
        result = _try_anthropic(prompt, system_prompt, hist)
        if result:
            return result
        result = _try_openai(prompt, system_prompt, hist)
        if result:
            return result
        return {
            "answer": "",
            "provider": "error",
            "model": "",
            "error": (
                "No AI provider available. "
                "Start Ollama (`ollama serve`) or set GOOGLE_API_KEY, "
                "ANTHROPIC_API_KEY / OPENAI_API_KEY "
                "in ~/.ai-employee/.env and restart."
            ),
            "usage": None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(_process_one, prompts))

    return results


def query_ai_for_agent(
    agent_type: str,
    prompt: str,
    system_prompt: str = "",
    history: Optional[list] = None,
) -> dict:
    """Route an AI query to the best model for a specific agent type.

    Two-Layer Routing (LOCAL_AI_FIRST=1, default):
    ──────────────────────────────────────────────
    LAYER 1 — Free / Local (always run first, regardless of agent preference):
      1a. Ollama  (local model — truly free and private)
      1b. Gemma   (Google open-source — via Ollama or Google AI Studio free)
      1c. NVIDIA NIM  (free-tier cloud — uses agent-specific model when applicable)

    LAYER 2 — Paid Cloud (only if Layer 1 fully unavailable):
      Uses the agent's preferred paid provider with its specialist model, then
      falls back to the remaining cloud provider.

    Agent → preferred provider mapping:
      creative           → Gemma (strong creative writing, free/local)
      coding             → NVIDIA Qwen Coder
      reasoning/orchestrator → NVIDIA Nemotron
      bulk               → NVIDIA Llama 8B
      sales / persuasive → OpenAI GPT-4o   (best persuasive copy)
      analytics / data   → Anthropic Claude  (superior long-context analysis)
      general / other    → Ollama → Gemma → NIM → cloud

    Sub-agent inheritance: if ACTIVE_AI_PROVIDER is set, all agents use that
    provider regardless of their category routing.

    Turbo Mode integration (when turbo_quant is available):
      MONEY  → forces Ollama local-only routing for cost efficiency
      POWER  → skips Ollama and goes straight to the agent's preferred provider
      AUTO   → standard two-layer routing (default)

    Legacy Mode (LOCAL_AI_FIRST=0):
      Tries the preferred provider first, then falls back via query_ai().

    Args:
        agent_type:    Agent category key (e.g. "sales", "coding", "reasoning").
                       Case-insensitive. Falls back to general routing if unknown.
        prompt:        The user message or question.
        system_prompt: Optional system/role instructions.
        history:       Optional conversation history.

    Returns:
        Same dict structure as query_ai():
            answer, provider, model, error, usage
    """
    history = history or []
    agent_key = agent_type.lower()

    # ── TurboQuant: select optimal model config for this agent/task ───────────
    _tq_cfg = None
    if _turbo_quant is not None:
        try:
            _tq_cfg = _turbo_quant.select_model(
                agent_id = agent_key,
                task     = prompt,
                category = agent_key,
            )
            logger.debug(
                "ai_router: TurboQuant selected model=%s quant=%s provider=%s for agent=%s",
                _tq_cfg.model, _tq_cfg.quant, _tq_cfg.provider, agent_type,
            )
        except Exception as exc:
            logger.debug("ai_router: turbo_quant.select_model failed for agent=%s — %s", agent_type, exc)
            _tq_cfg = None

    # ── Provider inheritance: honour ACTIVE_AI_PROVIDER for sub-agents ────────
    if ACTIVE_AI_PROVIDER:
        result = _try_forced_provider(ACTIVE_AI_PROVIDER, prompt, system_prompt, history)
        _turbo_log(result, _tq_cfg, prompt)
        return result

    routing = _route_for_agent(None, agent_key)
    preferred_provider = routing["provider"]
    preferred_model = os.environ.get(routing["model_env"], routing["default_model"])

    # ── Turbo Mode override ───────────────────────────────────────────────────
    turbo_mode = _turbo_mode()
    if turbo_mode == "MONEY":
        # MONEY mode: local Ollama only — use TurboQuant's quantized model
        logger.debug("ai_router: TURBO MONEY mode — forcing Ollama-only for agent=%s", agent_type)
        _tq_ollama_model = (
            _tq_cfg.model if (_tq_cfg is not None and _tq_cfg.provider == "ollama") else None
        )
        result = _try_ollama(prompt, system_prompt, history, model=_tq_ollama_model)
        result = result or _error_response()
        _turbo_log(result, _tq_cfg, prompt)
        return result

    if turbo_mode == "POWER":
        # POWER mode: skip Layer 1, go straight to the best provider for this agent
        logger.debug(
            "ai_router: TURBO POWER mode — skipping Layer 1 for agent=%s, using %s/%s",
            agent_type, preferred_provider, preferred_model,
        )
        if preferred_provider == "nvidia_nim":
            result = _try_nvidia_nim(prompt, system_prompt, history, model=preferred_model)
            if result:
                _turbo_log(result, _tq_cfg, prompt)
                return result
        elif preferred_provider == "openai":
            result = _try_openai(prompt, system_prompt, history, model=preferred_model)
            if result:
                _turbo_log(result, _tq_cfg, prompt)
                return result
            result = _try_anthropic(prompt, system_prompt, history)
            result = result or _error_response()
            _turbo_log(result, _tq_cfg, prompt)
            return result
        elif preferred_provider == "anthropic":
            result = _try_anthropic(prompt, system_prompt, history, model=preferred_model)
            if result:
                _turbo_log(result, _tq_cfg, prompt)
                return result
            result = _try_openai(prompt, system_prompt, history)
            result = result or _error_response()
            _turbo_log(result, _tq_cfg, prompt)
            return result
        # nvidia_nim fallback → cloud
        result = _try_anthropic(prompt, system_prompt, history) or _try_openai(prompt, system_prompt, history)
        result = result or _error_response()
        _turbo_log(result, _tq_cfg, prompt)
        return result

    logger.debug(
        "ai_router: agent_type=%s → preferred_provider=%s model=%s LOCAL_AI_FIRST=%s turbo=%s",
        agent_type, preferred_provider, preferred_model, LOCAL_AI_FIRST, turbo_mode,
    )

    if LOCAL_AI_FIRST:
        # ── Layer 1: Free / Local ─────────────────────────────────────────────
        # 1a. Ollama — use TurboQuant model when available and provider is ollama
        _tq_ollama_model = (
            _tq_cfg.model if (_tq_cfg is not None and _tq_cfg.provider == "ollama") else None
        )
        result = _try_ollama(prompt, system_prompt, history, model=_tq_ollama_model)
        if result:
            _turbo_log(result, _tq_cfg, prompt)
            return result

        # 1b. Gemma — Google open-source, free and local.
        #   Use Gemma as preferred model for creative tasks; others get default.
        gemma_model = preferred_model if preferred_provider == "gemma" else None
        result = _try_gemma(prompt, system_prompt, history, model=gemma_model)
        if result:
            _turbo_log(result, _tq_cfg, prompt)
            return result

        # 1c. NVIDIA NIM — free-tier cloud.
        #   Use the agent's specific NIM model when the agent prefers NIM;
        #   otherwise use the default NIM reasoning model.
        nim_model = preferred_model if preferred_provider == "nvidia_nim" else None
        result = _try_nvidia_nim(prompt, system_prompt, history, model=nim_model)
        if result:
            _turbo_log(result, _tq_cfg, prompt)
            return result

        # ── Layer 2: Paid Cloud ───────────────────────────────────────────────
        logger.debug(
            "ai_router: Layer 1 exhausted for agent=%s — falling back to paid cloud",
            agent_type,
        )

        # Try the agent's preferred paid provider with its specialist model first.
        if preferred_provider == "openai":
            result = _try_openai(prompt, system_prompt, history, model=preferred_model)
            if result:
                _turbo_log(result, _tq_cfg, prompt)
                return result
            # Remaining cloud fallback
            result = _try_anthropic(prompt, system_prompt, history) or _error_response()
            _turbo_log(result, _tq_cfg, prompt)
            return result

        if preferred_provider == "anthropic":
            result = _try_anthropic(prompt, system_prompt, history, model=preferred_model)
            if result:
                _turbo_log(result, _tq_cfg, prompt)
                return result
            # Remaining cloud fallback
            result = _try_openai(prompt, system_prompt, history) or _error_response()
            _turbo_log(result, _tq_cfg, prompt)
            return result

        # Gemma / NIM / Ollama preferred (all already exhausted in Layer 1): try cloud
        result = _try_anthropic(prompt, system_prompt, history)
        if result:
            _turbo_log(result, _tq_cfg, prompt)
            return result
        result = _try_openai(prompt, system_prompt, history) or _error_response()
        _turbo_log(result, _tq_cfg, prompt)
        return result

    # ── Legacy mode: preferred-provider-first ────────────────────────────────
    result = None

    if preferred_provider == "gemma":
        result = _try_gemma(prompt, system_prompt, history, model=preferred_model)
        if result:
            logger.debug("ai_router: agent=%s used Gemma/%s", agent_type, preferred_model)

    elif preferred_provider == "nvidia_nim":
        result = _try_nvidia_nim(prompt, system_prompt, history, model=preferred_model)
        if result:
            logger.debug("ai_router: agent=%s used NVIDIA NIM/%s", agent_type, preferred_model)

    elif preferred_provider == "openai" and OPENAI_API_KEY:
        result = _try_openai(prompt, system_prompt, history, model=preferred_model)
        if result:
            logger.debug("ai_router: agent=%s used OpenAI/%s", agent_type, preferred_model)

    elif preferred_provider == "anthropic" and ANTHROPIC_API_KEY:
        result = _try_anthropic(prompt, system_prompt, history, model=preferred_model)
        if result:
            logger.debug("ai_router: agent=%s used Anthropic/%s", agent_type, preferred_model)

    elif preferred_provider == "ollama":
        _tq_ollama_model = (
            _tq_cfg.model if (_tq_cfg is not None and _tq_cfg.provider == "ollama") else None
        )
        result = _try_ollama(prompt, system_prompt, history, model=_tq_ollama_model)

    if result:
        _turbo_log(result, _tq_cfg, prompt)
        return result

    logger.debug(
        "ai_router: preferred provider for agent=%s unavailable, falling back to standard chain",
        agent_type,
    )
    return query_ai(prompt, system_prompt=system_prompt, history=history)


def _error_response() -> dict:
    """Return a standard all-providers-failed response."""
    return {
        "answer": "",
        "provider": "error",
        "model": "",
        "error": (
            "No AI provider available. "
            "Start Ollama (`ollama serve` then `ollama pull gemma3`), "
            "set GOOGLE_API_KEY, NVIDIA_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY "
            "in ~/.ai-employee/.env and restart."
        ),
        "usage": None,
    }


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

    When the system is in offline mode, all providers are skipped and an
    offline notice is returned so callers receive a graceful degradation
    instead of a timeout or empty result.

    Args:
        query:        Search query string.
        max_results:  Maximum number of results to return.
        include_news: Also include NewsAPI results when key is available.

    Returns:
        List of dicts with keys: title, url, snippet, source.
        Empty list if all providers fail.
    """
    # ── Offline mode: skip all network calls ─────────────────────────────────
    if not _is_online():
        logger.debug("ai_router: offline — returning offline notice for search_web('%s')", query)
        if _hybrid_mode is not None:
            try:
                return _hybrid_mode.offline_search_notice(query)
            except Exception:
                pass
        return [
            {
                "title": "[OFFLINE MODE] Web search unavailable",
                "url": "",
                "snippet": (
                    f"Web search for '{query}' could not be performed — "
                    "the system is currently in offline mode."
                ),
                "source": "hybrid_mode",
            }
        ]

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
    from multiple web sources — useful when agents need up-to-date information.

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


# ── Hybrid Mode convenience re-exports ───────────────────────────────────────
# Allow callers to access hybrid mode controls via the router:
#   from ai_router import get_hybrid_mode, set_hybrid_mode, hybrid_status

def get_hybrid_mode() -> str:
    """Return the currently configured hybrid mode ("auto" | "online" | "offline").

    Delegates to hybrid_mode module when available; returns "auto" otherwise.
    """
    if _hybrid_mode is not None:
        try:
            return _hybrid_mode.get_hybrid_mode()
        except Exception:
            pass
    return "auto"


def set_hybrid_mode(mode: str) -> None:
    """Set the hybrid mode at runtime.

    Args:
        mode: One of "auto", "online", or "offline".

    When set to "offline", all cloud AI providers (NVIDIA NIM, Anthropic,
    OpenAI) are skipped and only local models (Ollama, Gemma-via-Ollama) are
    used.  Web search is replaced with an offline notice.

    When set to "online", connectivity checks are bypassed and all providers
    are available as normal.

    When set to "auto" (default), connectivity is probed before each cloud
    call and the system switches modes automatically.
    """
    if _hybrid_mode is not None:
        try:
            _hybrid_mode.set_hybrid_mode(mode)
            return
        except Exception as exc:
            logger.warning("ai_router: set_hybrid_mode failed — %s", exc)
    logger.debug("ai_router: hybrid_mode module not loaded; ignoring set_hybrid_mode('%s')", mode)


def hybrid_status() -> dict:
    """Return a dict describing the current hybrid mode state.

    Keys (all present even when hybrid_mode module is absent):
        configured_mode  (str)  — "auto" | "online" | "offline"
        effective_online (bool) — True if currently acting as online
        failsafe_active  (bool) — True if failsafe is forcing offline
        failsafe_remaining_s (int|None)
        cache_age_s      (float|None)
        probe_result     (bool|None)
        hybrid_module    (bool) — True if hybrid_mode module is loaded
    """
    base: dict = {
        "configured_mode": "auto",
        "effective_online": True,
        "failsafe_active": False,
        "failsafe_remaining_s": None,
        "cache_age_s": None,
        "probe_result": None,
        "hybrid_module": _hybrid_mode is not None,
    }
    if _hybrid_mode is not None:
        try:
            status = _hybrid_mode.get_status()
            base.update(status)
        except Exception:
            pass
    base["hybrid_module"] = _hybrid_mode is not None
    return base
