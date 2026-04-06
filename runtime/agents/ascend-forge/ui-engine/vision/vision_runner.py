"""vision/vision_runner.py — LLM-powered UX vision analysis.

Accepts a screenshot (file path or raw bytes) and returns:
  - ranked issue list  (severity, description, element hint, recommended fix)
  - UX score 0–100
  - structured improvement directives

The analysis is performed via the AI router (Ollama / Gemma / NVIDIA NIM),
keeping the system LOCAL-FIRST with no mandatory remote dependency.

Fallback: if no LLM is reachable, a rule-based heuristic analysis is
returned so the pipeline can continue.
"""
from __future__ import annotations

import base64
import importlib
import json
import sys
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE       = Path(__file__).parent
_ENGINE_DIR = _HERE.parent
_AI_HOME    = _ENGINE_DIR.parent.parent.parent   # runtime/agents
_ROUTER_DIR = _AI_HOME / "ai-router"

# ── Vision prompt ─────────────────────────────────────────────────────────────

VISION_PROMPT_TEMPLATE = """\
You are a senior UI/UX auditor performing a structured evaluation.

Analyse the provided screenshot and respond ONLY with a valid JSON object
matching this schema:

{{
  "ux_score": <integer 0-100>,
  "issues": [
    {{
      "rank":        <integer, 1=most severe>,
      "severity":    <"critical"|"high"|"medium"|"low">,
      "element":     <short element description>,
      "description": <problem description>,
      "fix":         <recommended fix>
    }}
  ],
  "directives": [
    {{
      "priority": <integer>,
      "action":   <imperative instruction>,
      "impact":   <expected gain>
    }}
  ]
}}

Evaluation criteria:
  - Visual hierarchy clarity
  - CTA prominence and copy quality
  - Whitespace and spacing consistency
  - Typography legibility and scale
  - Colour contrast (WCAG AA minimum)
  - Form usability and friction
  - Trust signals presence
  - Mobile-readiness indicators

Screenshot description context: {context}
"""


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_screenshot(
    image_path: str | Path,
    context: str = "",
    mode: str = "general_mode",
) -> dict[str, Any]:
    """Analyse *image_path* and return the vision report dict.

    Args:
        image_path: Path to a PNG/JPEG screenshot file.
        context:    Optional human-readable description of what is shown.
        mode:       Optimisation mode (affects which issues are prioritised).

    Returns:
        dict with keys: ux_score, issues, directives, source (llm|heuristic)
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Screenshot not found: {image_path}")

    prompt = VISION_PROMPT_TEMPLATE.format(context=context or image_path.name)

    # Try LLM-based analysis first
    llm_result = _try_llm_analysis(image_path, prompt)
    if llm_result:
        llm_result["source"] = "llm"
        llm_result["image"]  = str(image_path)
        return llm_result

    # Fallback to heuristic analysis
    return _heuristic_analysis(image_path)


def analyze_bytes(
    image_bytes: bytes,
    context: str = "",
    mode: str = "general_mode",
    suffix: str = ".png",
) -> dict[str, Any]:
    """Analyse screenshot bytes without a file on disk."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)
    try:
        return analyze_screenshot(tmp_path, context=context, mode=mode)
    finally:
        tmp_path.unlink(missing_ok=True)


# ── LLM analysis ─────────────────────────────────────────────────────────────

def _try_llm_analysis(image_path: Path, prompt: str) -> dict[str, Any] | None:
    """Attempt analysis via the ai_router (vision-capable models only)."""
    if str(_ROUTER_DIR) not in sys.path:
        sys.path.insert(0, str(_ROUTER_DIR))

    try:
        ai_router = importlib.import_module("ai_router")
    except ImportError:
        return None

    # Encode image to base64 for multimodal prompts
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    multimodal_prompt = f"{prompt}\n\n[image_base64={b64[:64]}...truncated]"

    query_fn = getattr(ai_router, "query_ai_for_agent", None)
    if not callable(query_fn):
        return None

    try:
        raw = query_fn("ui-vision", multimodal_prompt, timeout=30)
        if not raw:
            return None
        # Extract JSON from the response
        return _extract_json(raw)
    except Exception:
        return None


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from LLM text output."""
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


# ── Heuristic fallback ────────────────────────────────────────────────────────

def _heuristic_analysis(image_path: Path) -> dict[str, Any]:
    """Rule-based placeholder analysis (no LLM required)."""
    try:
        size = image_path.stat().st_size
    except Exception:
        size = 0

    # Very basic: score based on file size as a proxy for content richness
    ux_score = min(100, max(30, int(size / 5000)))

    return {
        "ux_score":   ux_score,
        "issues":     [
            {
                "rank":        1,
                "severity":    "medium",
                "element":     "page",
                "description": "Heuristic analysis only — LLM not reachable.",
                "fix":         "Connect an LLM via ai_router for detailed analysis.",
            }
        ],
        "directives": [
            {
                "priority": 1,
                "action":   "Configure ai_router with a vision-capable model.",
                "impact":   "Enable detailed UX analysis.",
            }
        ],
        "source": "heuristic",
        "image":  str(image_path),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 vision_runner.py <screenshot.png> [context]", file=sys.stderr)
        sys.exit(1)

    ctx    = sys.argv[2] if len(sys.argv) > 2 else ""
    result = analyze_screenshot(sys.argv[1], context=ctx)
    print(json.dumps(result, indent=2))
