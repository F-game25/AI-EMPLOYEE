"""NVIDIA NIM API Client — completions, embeddings, and reranking.

Provides a thin, stdlib-friendly wrapper around the NVIDIA NIM (Neural
Inference Microservices) OpenAI-compatible REST API hosted at
https://integrate.api.nvidia.com/v1.

All three capabilities are supported:

  Completions (chat)
  ------------------
  Models (free-tier, select one per task type):
    - nvidia/llama-3.3-nemotron-super-49b-v1   ← reasoning / deep logic
    - meta/llama-3.1-8b-instruct               ← bulk / high-volume tasks
    - qwen/qwen2.5-coder-32b-instruct          ← code generation
    - deepseek-ai/deepseek-r1-0528             ← advanced reasoning fallback

  Embeddings
  ----------
    - nvidia/nv-embed-v2  (4096-dim, MTEB SOTA)

  Reranking
  ---------
    - nvidia/nv-rerankqa-mistral-4b-v3  (passage/query relevance scoring)

Usage::

    from nim_client import NIMClient

    client = NIMClient()                     # reads NVIDIA_API_KEY from env
    # Chat completion
    resp = client.chat("Explain Transformers in plain English")
    print(resp["answer"])

    # Embeddings
    vecs = client.embed(["B2B SaaS startup", "fintech company"])
    print(len(vecs[0]))    # 4096

    # Reranking
    ranked = client.rerank(query="AI automation tool",
                           passages=["SaaS platform…", "Physical store…"])
    print(ranked)          # list of {index, score, text}

Environment variables (all optional — system degrades gracefully if absent):
    NVIDIA_API_KEY          — NVIDIA NIM API key (required for cloud models)
    NIM_BASE_URL            — override base URL (default: https://integrate.api.nvidia.com/v1)
    NIM_REASONING_MODEL     — reasoning model (default: nvidia/llama-3.3-nemotron-super-49b-v1)
    NIM_CODING_MODEL        — coding model    (default: qwen/qwen2.5-coder-32b-instruct)
    NIM_BULK_MODEL          — bulk model      (default: meta/llama-3.1-8b-instruct)
    NIM_EMBED_MODEL         — embedding model (default: nvidia/nv-embed-v2)
    NIM_RERANK_MODEL        — rerank model    (default: nvidia/nv-rerankqa-mistral-4b-v3)
    NIM_TIMEOUT             — request timeout seconds (default: 60)
    NIM_MAX_TOKENS          — max tokens per completion (default: 2048)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("nim_client")

# ── Configuration ─────────────────────────────────────────────────────────────

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")

NIM_REASONING_MODEL = os.environ.get(
    "NIM_REASONING_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"
)
NIM_CODING_MODEL = os.environ.get(
    "NIM_CODING_MODEL", "qwen/qwen2.5-coder-32b-instruct"
)
NIM_BULK_MODEL = os.environ.get(
    "NIM_BULK_MODEL", "meta/llama-3.1-8b-instruct"
)
NIM_EMBED_MODEL = os.environ.get(
    "NIM_EMBED_MODEL", "nvidia/nv-embed-v2"
)
NIM_RERANK_MODEL = os.environ.get(
    "NIM_RERANK_MODEL", "nvidia/nv-rerankqa-mistral-4b-v3"
)
NIM_TIMEOUT = int(os.environ.get("NIM_TIMEOUT", "60"))
NIM_MAX_TOKENS = int(os.environ.get("NIM_MAX_TOKENS", "2048"))

# Rate-limit retry settings (free tier = 10 RPM on most endpoints)
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BACKOFF = 6.0  # seconds between retries


class NIMError(RuntimeError):
    """Raised when a NIM API request fails permanently."""


class NIMClient:
    """Thin wrapper around NVIDIA NIM's OpenAI-compatible REST API.

    All methods fall back gracefully: they return empty results (never raise)
    when the API key is absent or the endpoint is unreachable — so callers can
    degrade gracefully without special error handling.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or NVIDIA_API_KEY
        self.base_url = NIM_BASE_URL

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AI-Employee/1.0",
        }

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON payload to a NIM endpoint with retry on rate-limit (429)."""
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = self._headers()

        for attempt in range(_RATE_LIMIT_RETRIES):
            try:
                req = urllib.request.Request(
                    url, data=body, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=NIM_TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < _RATE_LIMIT_RETRIES - 1:
                    wait = _RATE_LIMIT_BACKOFF * (attempt + 1)
                    logger.warning(
                        "nim_client: rate-limited (429), retrying in %.0fs…", wait
                    )
                    time.sleep(wait)
                    continue
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = str(exc)
                raise NIMError(f"NIM API error {exc.code}: {err_body}") from exc
            except Exception as exc:
                raise NIMError(f"NIM request failed: {exc}") from exc
        raise NIMError("NIM: max retries exceeded")  # pragma: no cover

    # ── Chat Completions ──────────────────────────────────────────────────────

    def chat(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        history: Optional[list] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> dict:
        """Send a chat completion request to NVIDIA NIM.

        Args:
            prompt:        User message.
            system_prompt: Optional system/role instruction.
            history:       Previous messages in OpenAI format.
            model:         Override model (defaults to NIM_REASONING_MODEL).
            max_tokens:    Override max output tokens.
            temperature:   Sampling temperature (0–1).

        Returns:
            dict with keys:
                answer   (str)   — response text, empty on failure
                provider (str)   — "nvidia_nim"
                model    (str)   — model used
                error    (str|None)
                usage    (dict|None)  — {input_tokens, output_tokens}
        """
        if not self.api_key:
            return _error_result("NVIDIA_API_KEY not set")

        use_model = model or NIM_REASONING_MODEL
        messages: list = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": use_model,
            "messages": messages,
            "max_tokens": max_tokens or NIM_MAX_TOKENS,
            "temperature": temperature,
            "stream": False,
        }

        try:
            data = self._post("/chat/completions", payload)
            answer = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            logger.debug("nim_client: chat completed via %s", use_model)
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
        except NIMError as exc:
            logger.warning("nim_client: chat failed — %s", exc)
            return _error_result(str(exc))

    def chat_coding(self, prompt: str, **kwargs) -> dict:
        """Chat completion optimised for code generation (Qwen coder model)."""
        return self.chat(prompt, model=NIM_CODING_MODEL, **kwargs)

    def chat_bulk(self, prompt: str, **kwargs) -> dict:
        """Chat completion optimised for bulk/simple tasks (Llama 8B model)."""
        return self.chat(prompt, model=NIM_BULK_MODEL, **kwargs)

    # ── Embeddings ────────────────────────────────────────────────────────────

    def embed(
        self,
        texts: list[str],
        *,
        model: Optional[str] = None,
        input_type: str = "query",
        truncate: str = "END",
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts using NVIDIA NV-Embed-v2.

        Args:
            texts:      List of strings to embed (max 256 per batch for free tier).
            model:      Override embedding model.
            input_type: "query" for search queries, "passage" for documents.
            truncate:   Truncation strategy — "END" or "START" (NIM default: END).

        Returns:
            List of float vectors (one per input text).
            Returns empty list on failure.
        """
        if not self.api_key:
            logger.debug("nim_client: embed skipped — NVIDIA_API_KEY not set")
            return []
        if not texts:
            return []

        use_model = model or NIM_EMBED_MODEL
        payload = {
            "model": use_model,
            "input": texts,
            "input_type": input_type,
            "truncate": truncate,
        }

        try:
            data = self._post("/embeddings", payload)
            # Sort by index to preserve input order
            items = sorted(data["data"], key=lambda x: x["index"])
            vectors = [item["embedding"] for item in items]
            logger.debug(
                "nim_client: embedded %d texts via %s (dim=%d)",
                len(texts), use_model, len(vectors[0]) if vectors else 0,
            )
            return vectors
        except NIMError as exc:
            logger.warning("nim_client: embed failed — %s", exc)
            return []

    def embed_one(self, text: str, **kwargs) -> list[float]:
        """Convenience wrapper: embed a single text, return its vector."""
        result = self.embed([text], **kwargs)
        return result[0] if result else []

    # ── Reranking ─────────────────────────────────────────────────────────────

    def rerank(
        self,
        query: str,
        passages: list[str],
        *,
        model: Optional[str] = None,
        top_n: Optional[int] = None,
    ) -> list[dict]:
        """Rerank passages by relevance to the query using NVIDIA NV-Rerank.

        Args:
            query:    The reference query/question.
            passages: List of passage strings to score.
            model:    Override rerank model.
            top_n:    Return only top N results (default: all).

        Returns:
            List of dicts ordered by relevance score (highest first):
                {index: int, score: float, text: str}
            Empty list on failure.
        """
        if not self.api_key:
            logger.debug("nim_client: rerank skipped — NVIDIA_API_KEY not set")
            return []
        if not passages:
            return []

        use_model = model or NIM_RERANK_MODEL
        payload = {
            "model": use_model,
            "query": {"text": query},
            "passages": [{"text": p} for p in passages],
        }
        if top_n is not None:
            payload["top_n"] = top_n

        try:
            data = self._post("/ranking", payload)
            rankings = data.get("rankings", [])
            results = []
            for r in rankings:
                idx = r.get("index", 0)
                results.append({
                    "index": idx,
                    "score": r.get("logit", r.get("score", 0.0)),
                    "text": passages[idx] if idx < len(passages) else "",
                })
            # Sort highest score first
            results.sort(key=lambda x: x["score"], reverse=True)
            if top_n is not None:
                results = results[:top_n]
            logger.debug(
                "nim_client: reranked %d passages via %s", len(passages), use_model
            )
            return results
        except NIMError as exc:
            logger.warning("nim_client: rerank failed — %s", exc)
            return []

    # ── Availability check ────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if NVIDIA_API_KEY is configured."""
        return bool(self.api_key)


# ── Module-level convenience singleton ───────────────────────────────────────

_default_client: Optional[NIMClient] = None


def get_client() -> NIMClient:
    """Return a module-level NIMClient instance (created once, reused)."""
    global _default_client
    if _default_client is None:
        _default_client = NIMClient()
    return _default_client


def _error_result(msg: str) -> dict:
    return {
        "answer": "",
        "provider": "nvidia_nim",
        "model": "",
        "error": msg,
        "usage": None,
    }
