"""ProductVideoSkill — turn a content brief into a rendered MP4.

Composes two atomic tools end-to-end:
  1. local Qwythos writes a self-contained HyperFrames HTML composition for the brief
  2. the `video_render` tool renders it to MP4 (HeyGen HyperFrames)

This is the skill layer for money_mode.content_publish_track: an agent describes a
video, the system produces the artifact. Safe by default — rendering is dry_run unless
explicitly requested AND the render tool's own feature flag is set.
"""
from __future__ import annotations

from typing import Any, Callable

from skills.base import SkillBase
from skills._local_llm import local_chat, model_name

_HTML_SYSTEM = (
    "You are a HyperFrames video author. Output ONE complete, self-contained HTML "
    "document (doctype + <html><head><style>…</style></head><body>…) for a short "
    "promotional video. Use only inline CSS/animation. No external URLs, no scripts "
    "fetching remote data. Return ONLY the HTML inside a single ```html code block."
)


def _extract_html(text: str) -> str:
    import re
    m = re.search(r"```html\s*([\s\S]*?)```", text, re.I)
    if m:
        return m.group(1).strip()
    # Fall back to a raw HTML doc if the model didn't fence it.
    m = re.search(r"(<!doctype html[\s\S]*</html>)", text, re.I)
    return m.group(1).strip() if m else text.strip()


class ProductVideoSkill(SkillBase):
    name = "product-video"
    description = "Compose a promo video as HTML (local Qwythos) and render it to MP4 via HyperFrames."
    version = "1.0"
    capability_tags = ["media", "video", "content", "money_mode", "marketing"]
    input_schema = {
        "type": "object",
        "properties": {
            "brief": {"type": "string", "description": "What the video should say/show"},
            "name": {"type": "string"},
            "render": {"type": "boolean", "description": "Actually render (else dry_run/plan only)"},
        },
        "required": ["brief"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "html_bytes": {"type": "integer"},
            "render": {"type": "object"},
            "model": {"type": "string"},
        },
        "required": ["status"],
    }
    allowed_actions = ["skill_dispatch", "tool:video_render"]

    def execute(self, input_data: dict[str, Any],
                action_runner: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        brief = str(input_data.get("brief") or "").strip()
        if not brief:
            return {"status": "error", "error": "brief is required"}
        name = str(input_data.get("name") or "promo")

        # 1) Local model composes the HTML composition (no data leaves the box).
        reply = local_chat(f"Brief: {brief}\n\nWrite the HyperFrames HTML now.",
                            system=_HTML_SYSTEM, num_predict=1500)
        if not reply:
            return {"status": "degraded", "error": "local model unavailable to compose HTML",
                    "note": "start Ollama (qwythos:q4) or pre-supply html"}
        html = _extract_html(reply)
        if "<" not in html:
            return {"status": "error", "error": "model did not return usable HTML"}

        # 2) Render via the atomic tool. dry_run unless the caller opts into a real render.
        from tools.registry import call_tool
        render = call_tool("video_render", {
            "html": html, "name": name, "dry_run": not bool(input_data.get("render")),
        })

        return {
            "status": "success",
            "model": model_name(),
            "html_bytes": len(html.encode("utf-8", "ignore")),
            "render": render,
            "confidence": 0.7 if render.get("status") in ("rendered", "planned") else 0.4,
        }
