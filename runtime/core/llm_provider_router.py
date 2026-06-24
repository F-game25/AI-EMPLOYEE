"""
LLM Provider Router — Route API calls across LLM backends.

Reads the primary provider from environment (set by Settings API POST). Supports
Anthropic, OpenAI, OpenRouter, NVIDIA (hosted NIM), and Ollama (local) — used
either as a fallback chain (generate/stream) or ALL AT ONCE, independently, via
generate_concurrent().

Security: every call to an EXTERNAL provider passes through the egress guard
(core/egress_guard) first — secrets never leave the box, PII is redacted, local
providers (Ollama) are untouched. See runtime/config/egress_policy.json.
"""

import os
import json
import time
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, AsyncIterator

# Retry + redacted audit so external-provider calls preserve the orchestrator's
# retry/JSONL-logging guarantees (CLAUDE.md #20: log which model/provider was used;
# #23: never log prompt/response text). The router is the single audited surface in
# front of the leaf provider adapters (openai/nvidia/...).
_PROVIDER_MAX_ATTEMPTS = max(1, min(5, int(os.getenv('LLM_PROVIDER_MAX_ATTEMPTS', '2') or '2')))


def _llm_log_path() -> Path:
    base = os.getenv('STATE_DIR') or os.path.join(os.path.expanduser('~'), '.ai-employee', 'state')
    p = Path(base)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p / 'llm_calls.jsonl'


def _log_llm_call(event: dict) -> None:
    """Append REDACTED call metadata (provider/model/status/latency/attempts) to the
    shared llm_calls.jsonl. Never logs messages or responses. Best-effort: a logging
    failure must never break a generation."""
    try:
        path = _llm_log_path()
        if path.exists() and path.stat().st_size > 50 * 1024 * 1024:  # rotate at 50MB
            path.rename(path.with_suffix('.' + time.strftime('%Y%m%d_%H%M%S') + '.jsonl'))
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    except Exception:
        pass


class LLMProviderRouter:
    def __init__(self):
        self.primary_provider = os.getenv('LLM_PROVIDER', 'anthropic')
        self.anthropic_client = None
        self.ollama_client = None
        self.openrouter_client = None
        self.openai_client = None
        self.nvidia_client = None
        self._init_providers()

    def _init_providers(self):
        """Initialize all provider clients based on available API keys."""
        try:
            from anthropic_client import AnthropicClient
            if os.getenv('ANTHROPIC_API_KEY'):
                self.anthropic_client = AnthropicClient(
                    api_key=os.getenv('ANTHROPIC_API_KEY'),
                    model=os.getenv('LLM_MODEL', 'claude-3-5-sonnet-20241022')
                )
        except Exception as e:
            print(f"Failed to init Anthropic client: {e}")

        try:
            from ollama_client import OllamaClient
            if os.getenv('OLLAMA_ENDPOINT'):
                self.ollama_client = OllamaClient(
                    endpoint=os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434'),
                    model=os.getenv('OLLAMA_MODEL', 'llama2')
                )
        except Exception as e:
            print(f"Failed to init Ollama client: {e}")

        try:
            from openrouter_client import OpenRouterClient
            if os.getenv('OPENROUTER_API_KEY'):
                self.openrouter_client = OpenRouterClient(
                    api_key=os.getenv('OPENROUTER_API_KEY'),
                    model=os.getenv('OPENROUTER_MODEL', 'auto')
                )
        except Exception as e:
            print(f"Failed to init OpenRouter client: {e}")

        try:
            from openai_client import OpenAIClient
            if os.getenv('OPENAI_API_KEY'):
                self.openai_client = OpenAIClient(
                    api_key=os.getenv('OPENAI_API_KEY'),
                    model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
                )
        except Exception as e:
            print(f"Failed to init OpenAI client: {e}")

        try:
            from nvidia_client import NvidiaClient
            if os.getenv('NVIDIA_API_KEY'):
                self.nvidia_client = NvidiaClient(
                    api_key=os.getenv('NVIDIA_API_KEY'),
                    model=os.getenv('NVIDIA_MODEL', 'meta/llama-3.1-70b-instruct')
                )
        except Exception as e:
            print(f"Failed to init NVIDIA client: {e}")

    async def _generate_one(self, provider: str, messages: list, temperature: float, max_tokens: int) -> str:
        """Egress-guard, retry, and audit-log a single provider call. Raises on
        block / final failure. This is the audited chokepoint used by generate()
        and generate_concurrent()."""
        client = self._get_client(provider)
        if not client:
            raise Exception(f"provider {provider} not configured")
        model = getattr(client, 'model', None)
        ok, safe_messages, info = self._guard_messages(messages, provider)
        if not ok:
            _log_llm_call({'ts': time.time(), 'surface': 'provider_router', 'provider': provider,
                           'model': model, 'ok': False, 'egress': 'block', 'reason': info.get('reason')})
            raise Exception(f"egress blocked for {provider}: {info.get('reason')}")
        last_err = None
        for attempt in range(1, _PROVIDER_MAX_ATTEMPTS + 1):
            t0 = time.time()
            try:
                text = await client.generate(messages=safe_messages, temperature=temperature, max_tokens=max_tokens)
                _log_llm_call({'ts': time.time(), 'surface': 'provider_router', 'provider': provider,
                               'model': model, 'ok': True, 'latency_ms': round((time.time() - t0) * 1000),
                               'attempts': attempt, 'egress': info.get('action', 'allow')})
                return text
            except Exception as e:  # noqa: BLE001 — retry transient failures, then surface
                last_err = e
                _log_llm_call({'ts': time.time(), 'surface': 'provider_router', 'provider': provider,
                               'model': model, 'ok': False, 'latency_ms': round((time.time() - t0) * 1000),
                               'attempts': attempt, 'error': type(e).__name__})
                if attempt < _PROVIDER_MAX_ATTEMPTS:
                    await asyncio.sleep(min(2.0, 0.5 * attempt))
        raise last_err if last_err else Exception(f"provider {provider} failed")

    async def generate(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Generate using the selected provider; fall back on failure. Egress-guarded."""
        order = [self.primary_provider] + [p for p in ['anthropic', 'ollama', 'openrouter', 'openai', 'nvidia'] if p != self.primary_provider]
        for provider in order:
            if not self._get_client(provider):
                continue
            try:
                return await self._generate_one(provider, messages, temperature, max_tokens)
            except Exception as e:
                print(f"Provider {provider} unavailable: {e}")
        raise Exception("No LLM provider available")

    async def generate_concurrent(self, messages: list, providers: list | None = None,
                                  temperature: float = 0.7, max_tokens: int = 2048) -> dict:
        """Run MULTIPLE providers in parallel, independently — 'allemaal tegelijk'.

        Each provider gets its own egress-guarded call; one failing/blocked provider
        never affects the others. Returns { provider: {ok, text|error} } for every
        requested provider that is configured. Use this to compare Claude vs OpenAI
        vs OpenRouter at once, or to fan a task out across providers concurrently.
        """
        if providers is None:
            providers = ['anthropic', 'openai', 'openrouter', 'nvidia', 'ollama']
        active = [p for p in providers if self._get_client(p)]
        if not active:
            return {}

        async def _run(provider):
            try:
                text = await self._generate_one(provider, messages, temperature, max_tokens)
                return provider, {'ok': True, 'text': text}
            except Exception as e:  # independent: isolate each provider's failure
                return provider, {'ok': False, 'error': str(e)}

        results = await asyncio.gather(*[_run(p) for p in active], return_exceptions=False)
        return {provider: outcome for provider, outcome in results}

    def _get_client(self, provider: str):
        """Get client for specified provider."""
        if provider == 'anthropic':
            return self.anthropic_client
        elif provider == 'ollama':
            return self.ollama_client
        elif provider == 'openrouter':
            return self.openrouter_client
        elif provider == 'openai':
            return self.openai_client
        elif provider == 'nvidia':
            return self.nvidia_client
        return None

    @staticmethod
    def _egress():
        """Load the egress guard under either import style; None if unavailable."""
        try:
            from core import egress_guard as eg
            return eg
        except Exception:
            try:
                import egress_guard as eg
                return eg
            except Exception:
                return None

    def _guard_messages(self, messages, provider):
        """Run outbound messages through the egress guard for *provider*.

        Returns (ok, safe_messages, info). Local providers (ollama) pass through.
        External providers are BLOCKED on secret leakage and REDACTED on PII —
        fail-closed: if the guard module is unavailable, external sends are blocked.
        """
        eg = self._egress()
        tier = eg.tier_for_provider(provider) if eg else 'external_api'
        if tier == 'local':
            return True, messages, {'action': 'allow', 'tier': 'local'}
        if eg is None:
            return False, None, {'action': 'block', 'reason': 'egress guard unavailable (fail-closed)'}
        decision = eg.guard(messages, tier)
        if decision['action'] == 'block':
            return False, None, {'action': 'block', 'reason': decision['reason'], 'classification': decision.get('classification')}
        # allow or redact → use the (possibly redacted) payload
        return True, decision['payload'], {'action': decision['action'], 'classification': decision.get('classification')}

    async def stream(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Stream using the selected provider; fall back on failure. Egress-guarded."""
        order = [self.primary_provider] + [p for p in ['anthropic', 'ollama', 'openrouter', 'openai', 'nvidia'] if p != self.primary_provider]
        for provider in order:
            client = self._get_client(provider)
            if not client:
                continue
            ok, safe_messages, info = self._guard_messages(messages, provider)
            model = getattr(client, 'model', None)
            if not ok:
                _log_llm_call({'ts': time.time(), 'surface': 'provider_router.stream', 'provider': provider,
                               'model': model, 'ok': False, 'egress': 'block', 'reason': info.get('reason')})
                print(f"Provider {provider} stream egress-blocked: {info.get('reason')}")
                continue
            t0 = time.time()
            try:
                async for chunk in client.stream(messages=safe_messages, temperature=temperature, max_tokens=max_tokens):
                    yield chunk
                _log_llm_call({'ts': time.time(), 'surface': 'provider_router.stream', 'provider': provider,
                               'model': model, 'ok': True, 'latency_ms': round((time.time() - t0) * 1000),
                               'egress': info.get('action', 'allow')})
                return
            except Exception as e:
                _log_llm_call({'ts': time.time(), 'surface': 'provider_router.stream', 'provider': provider,
                               'model': model, 'ok': False, 'latency_ms': round((time.time() - t0) * 1000),
                               'error': type(e).__name__})
                print(f"Provider {provider} stream failed: {e}")

        raise Exception("No LLM provider available for streaming")

def route_model_qce(goal: str = '', complexity: str = 'medium',
                    provider_health: dict | None = None) -> str:
    """Use AmplitudeRouter.route_model() when QCE is available; fall back to env default."""
    try:
        from core.quantum.router import AmplitudeRouter
        router = AmplitudeRouter()
        return router.route_model(complexity=complexity, provider_health=provider_health)
    except Exception:
        pass
    # Fallback: env-configured primary provider model
    provider = os.getenv('LLM_PROVIDER', 'anthropic')
    if provider == 'ollama':
        return os.getenv('OLLAMA_MODEL', 'llama2')
    if provider == 'openrouter':
        return os.getenv('OPENROUTER_MODEL', 'auto')
    return os.getenv('LLM_MODEL', 'claude-3-5-sonnet-20241022')


_router = None

def get_router() -> LLMProviderRouter:
    global _router
    if _router is None:
        _router = LLMProviderRouter()
    return _router

def reset_router():
    """Reset the global router instance (for testing/settings changes)."""
    global _router
    _router = None
