"""pageindex — atomic tool: vectorless, reasoning-based retrieval.

Inspired by PageIndex (https://github.com/VectifyAI/PageIndex). Instead of
embedding + similarity search, it builds a hierarchical table-of-contents tree from
a document and LETS AN LLM REASON to the relevant section — so retrieval is
traceable/explainable (you get the exact section + why), with no vector DB and no
chunking. Complements the vector memory_router (vector = broad recall; this =
precise document QA).

Input::

    {"document": "# Title\\n...", "query": "can I bring my dog?", "max_sections": 3}

Output::

    {"status", "method": "reasoning|keyword", "sections": [{path,title,snippet,why}], "traceable": true}

PRIVACY: the reasoning step runs on LOCAL Qwythos only (localhost Ollama) — the
document NEVER leaves the box. If the local model is unavailable it falls back to a
deterministic keyword overlap, so retrieval always returns (never fails). The
document is untrusted data: size-capped, never executed.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from .registry import register_tool

_MAX_DOC_BYTES = int(os.getenv("PAGEINDEX_MAX_DOC_BYTES", "1500000"))  # 1.5MB
_OLLAMA_HOST = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
_LOCAL_MODEL = os.getenv("PAGEINDEX_MODEL") or os.getenv("OLLAMA_MODEL") or "qwythos:q4"
_LLM_TIMEOUT_S = int(os.getenv("PAGEINDEX_LLM_TIMEOUT_S", "60"))
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is",
         "are", "be", "can", "i", "my", "this", "that", "it", "as", "at", "by"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", str(s).lower()) if len(t) > 2 and t not in _STOP}


def _build_tree(document: str) -> list[dict]:
    """Split a markdown/structured doc into a flat list of sections with a heading
    PATH (the ToC). Falls back to a single section for unstructured text."""
    lines = document.splitlines()
    sections: list[dict] = []
    stack: list[str] = []  # heading path by level
    cur: dict | None = None
    head_re = re.compile(r"^(#{1,6})\s+(.*)$")
    for line in lines:
        m = head_re.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            stack = stack[: level - 1] + [title]
            cur = {"path": " > ".join(stack), "title": title, "content": ""}
            sections.append(cur)
        elif cur is not None:
            cur["content"] += line + "\n"
        else:
            # Preamble before the first heading.
            if not sections:
                cur = {"path": "(intro)", "title": "(intro)", "content": ""}
                sections.append(cur)
            cur["content"] += line + "\n"
    if not sections:
        sections.append({"path": "(document)", "title": "(document)", "content": document})
    return sections


def _local_llm_select(query: str, sections: list[dict], k: int) -> list[int] | None:
    """Ask LOCAL Qwythos which section numbers are most relevant. Returns a list of
    0-based indices, or None if the local model is unavailable / unparriable."""
    toc = "\n".join(f"{i}. {s['title']}" for i, s in enumerate(sections))
    prompt = (
        "You are a retrieval router. Given this document table-of-contents and a "
        "question, reply with ONLY the section numbers (comma-separated) most likely "
        f"to contain the answer — at most {k}.\n\nTABLE OF CONTENTS:\n{toc}\n\n"
        f"QUESTION: {query}\n\nSection numbers:"
    )
    body = json.dumps({
        "model": _LOCAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        # think:false → reasoning models (Qwythos/qwen3.5) answer directly instead
        # of spending the budget in a hidden thinking channel (empty content).
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 64},
    }).encode("utf-8")
    try:
        # Hard local-only: never anything but the loopback Ollama host. Exact
        # hostname match (a prefix check would accept http://localhost.evil.com).
        from urllib.parse import urlparse
        if (urlparse(_OLLAMA_HOST).hostname or "").lower() not in ("localhost", "127.0.0.1", "::1"):
            return None
        req = urllib.request.Request(f"{_OLLAMA_HOST}/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_LLM_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("message") or {}).get("content") or ""
        idxs = [int(n) for n in re.findall(r"\d+", text)]
        picked = [i for i in idxs if 0 <= i < len(sections)][:k]
        return picked or None
    except Exception:
        return None


def _keyword_select(query: str, sections: list[dict], k: int) -> list[int]:
    q = _tokens(query)
    scored = []
    for i, s in enumerate(sections):
        text = (s["title"] + " " + s["content"][:2000]).lower()
        # Substring match so a query token finds inflections (dog -> dogs).
        score = sum(1 for t in q if t in text)
        if score:
            scored.append((score, i))
    scored.sort(reverse=True)
    return [i for _, i in scored[:k]] or ([0] if sections else [])


def _call(input_data: dict[str, Any]) -> dict[str, Any]:
    document = input_data.get("document")
    query = str(input_data.get("query") or "").strip()
    if not isinstance(document, str) or not document.strip():
        return {"status": "error", "error": "document is required"}
    if not query:
        return {"status": "error", "error": "query is required"}
    if len(document.encode("utf-8", "ignore")) > _MAX_DOC_BYTES:
        return {"status": "error", "error": f"document exceeds {_MAX_DOC_BYTES} bytes"}

    k = max(1, min(10, int(input_data.get("max_sections", 3) or 3)))
    sections = _build_tree(document)

    method = "reasoning"
    picked = None if input_data.get("force_keyword") else _local_llm_select(query, sections, k)
    if picked is None:
        method = "keyword"
        picked = _keyword_select(query, sections, k)

    out = [{
        "path": sections[i]["path"],
        "title": sections[i]["title"],
        "snippet": sections[i]["content"].strip()[:600],
        "section_index": i,
    } for i in picked]

    return {"status": "success", "method": method, "traceable": True,
            "model": _LOCAL_MODEL if method == "reasoning" else None,
            "total_sections": len(sections), "sections": out}


register_tool(
    name="pageindex",
    description="Vectorless, reasoning-based retrieval: build a doc ToC tree and let LOCAL Qwythos reason "
                "to the exact relevant section(s) — traceable, no vectors, no data egress. Keyword fallback.",
    call=_call,
    input_schema={
        "type": "object",
        "properties": {
            "document": {"type": "string", "description": "The full document text (markdown/structured)"},
            "query": {"type": "string", "description": "The question to retrieve for"},
            "max_sections": {"type": "integer", "description": "Max sections to return (1-10, default 3)"},
            "force_keyword": {"type": "boolean", "description": "Skip the LLM and use keyword ranking only"},
        },
        "required": ["document", "query"],
    },
    output_schema={"type": "object"},
    tags=["retrieval", "rag", "vectorless", "document", "local"],
)
