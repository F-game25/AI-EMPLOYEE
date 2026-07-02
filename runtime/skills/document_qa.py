"""DocumentQASkill — precise, cited Q&A over a document via vectorless retrieval.

Composes the `pageindex` tool (reasoning-based, traceable section retrieval on local
Qwythos) with a local-model answer step:
  1. pageindex navigates the document's ToC tree to the relevant section(s)
  2. local Qwythos answers the question USING ONLY those sections, with a citation

Complements vector RAG: vector memory = broad recall; this = exact, explainable
document QA where the answer must trace to a specific section. Fully on-box.
"""
from __future__ import annotations

from typing import Any, Callable

from skills.base import SkillBase
from skills._local_llm import local_chat, model_name

_ANSWER_SYSTEM = (
    "Answer the question using ONLY the provided document sections. If the sections do "
    "not contain the answer, say so. Be concise. Do not invent facts. Cite the section "
    "title you used."
)


class DocumentQASkill(SkillBase):
    name = "document-qa"
    description = "Answer a question over a document using vectorless, reasoning-based retrieval (local Qwythos), with citations."
    version = "1.0"
    capability_tags = ["retrieval", "rag", "vectorless", "document", "qa", "local"]
    input_schema = {
        "type": "object",
        "properties": {
            "document": {"type": "string"},
            "query": {"type": "string"},
            "max_sections": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["document", "query"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "answer": {"type": "string"},
            "citations": {"type": "array"},
            "retrieval_method": {"type": "string"},
            "model": {"type": "string"},
        },
        "required": ["status"],
    }
    allowed_actions = ["skill_dispatch", "tool:pageindex"]

    def execute(self, input_data: dict[str, Any],
                action_runner: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        document = input_data.get("document")
        query = str(input_data.get("query") or "").strip()
        if not isinstance(document, str) or not document.strip():
            return {"status": "error", "error": "document is required"}
        if not query:
            return {"status": "error", "error": "query is required"}

        # 1) Vectorless retrieval — traceable section(s).
        from tools.registry import call_tool
        retrieved = call_tool("pageindex", {
            "document": document, "query": query,
            "max_sections": int(input_data.get("max_sections", 3) or 3),
        })
        if retrieved.get("status") != "success":
            return {"status": "error", "error": "retrieval failed", "detail": retrieved}

        sections = retrieved.get("sections") or []
        citations = [{"path": s.get("path"), "title": s.get("title")} for s in sections]
        context = "\n\n".join(f"## {s.get('title')}\n{s.get('snippet')}" for s in sections)

        # 2) Answer strictly from the retrieved sections (on local Qwythos).
        answer = local_chat(f"DOCUMENT SECTIONS:\n{context}\n\nQUESTION: {query}\n\nAnswer:",
                            system=_ANSWER_SYSTEM, num_predict=400)
        if not answer:
            # Graceful: still return the cited sections so the caller has the evidence.
            return {"status": "partial", "answer": None, "citations": citations,
                    "retrieval_method": retrieved.get("method"),
                    "note": "local model unavailable; returning retrieved sections only",
                    "sections": sections}

        return {
            "status": "success",
            "answer": answer,
            "citations": citations,
            "retrieval_method": retrieved.get("method"),
            "model": model_name(),
            "confidence": 0.8 if retrieved.get("method") == "reasoning" else 0.6,
        }
