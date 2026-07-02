"""Executable content skills — upgrade the highest-value prompt skills into real
executable skills (the C2 bar): they REUSE the curated library system_prompt but add
the executable layer that makes them products instead of templates:

  brief -> local Qwythos -> QUALITY GATE (validate structure/length/no-refusal,
  retry once on failure) -> structured result + confidence + saved artifact.

A single tested engine drives many skills via per-skill QualityGate config (DRY,
config-driven). The gate is the quality differentiator vs the prompt-only version.
All generation is on local Qwythos (no data egress).
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from skills.base import SkillBase
from skills._local_llm import local_chat, model_name

_LIB_PATH = Path(__file__).resolve().parents[1] / "config" / "skills_library.json"
_REFUSAL = re.compile(r"\b(i (cannot|can't|am unable|do not have)|as an ai|i'm sorry|please provide the)\b", re.I)


def _library() -> dict[str, dict]:
    try:
        data = json.loads(_LIB_PATH.read_text(encoding="utf-8"))
        return {e["id"]: e for e in data.get("skills", []) if isinstance(e, dict) and e.get("id")}
    except Exception:
        return {}


def _artifacts_dir() -> Path:
    base = os.getenv("STATE_DIR") or os.path.join(os.path.expanduser("~"), ".ai-employee", "state")
    d = Path(base) / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class QualityGate:
    """Deterministic, skill-specific output validation. The thing that makes a
    prompt skill a *product*: the output must actually meet the bar or it's flagged."""
    min_chars: int = 80
    must_match: list[str] = field(default_factory=list)   # regexes that MUST appear
    must_match_desc: list[str] = field(default_factory=list)  # human label per regex
    forbid_refusal: bool = True

    def check(self, text: str) -> tuple[bool, list[str]]:
        failed: list[str] = []
        t = text or ""
        if len(t.strip()) < self.min_chars:
            failed.append(f"too_short(<{self.min_chars})")
        if self.forbid_refusal and _REFUSAL.search(t):
            failed.append("refusal_or_input_request")
        for rx, label in zip(self.must_match, self.must_match_desc or self.must_match):
            if not re.search(rx, t, re.I | re.M):
                failed.append(f"missing:{label}")
        return (not failed), failed


class ExecutableContentSkill(SkillBase):
    """One executable skill, driven by a library prompt + a QualityGate."""

    def __init__(self, skill_id: str, gate: QualityGate, *, num_predict: int = 900,
                 required: tuple[str, ...] = ("brief",), lib_def: dict | None = None):
        lib = lib_def if lib_def is not None else _library().get(skill_id, {})
        self.skill_id = skill_id
        self.name = lib.get("id", skill_id)
        self.description = (lib.get("description") or skill_id) + " [executable: validated output + artifact]"
        self.version = "2.0"
        self.capability_tags = list(lib.get("tags", [])) + ["executable", "validated"]
        self._system = lib.get("system_prompt") or f"You are an expert at {skill_id.replace('_',' ')}."
        self._hint = lib.get("prompt_hint") or ""
        self._gate = gate
        self._num_predict = num_predict
        self._required = required
        # Preserve approval/safety metadata so the dispatcher can honor the HITL
        # contract for this skill (surface flags + route approval-gated skills).
        self.requires_human_approval = bool(lib.get("requires_human_approval"))
        self.safety_level = lib.get("safety_level")
        self.risk_level = lib.get("risk_level")
        self.input_schema = {
            "type": "object",
            "properties": {"brief": {"type": "string"}, "constraints": {"type": "string"},
                           "save_artifact": {"type": "boolean"}},
            "required": list(required),
        }
        self.output_schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}, "output": {"type": "string"},
                           "quality": {"type": "object"}, "confidence": {"type": "number"},
                           "artifact": {"type": "string"}},
            "required": ["status"],
        }
        self.allowed_actions = ["skill_dispatch", "llm:local"]

    def _compose(self, brief: str, constraints: str, strict: bool) -> "str | None":
        guidance = self._hint
        extra = ("\n\nIMPORTANT: produce the COMPLETE deliverable now — no preamble, no "
                 "questions, no requests for more input. Use sensible defaults for anything "
                 "unspecified.") if strict else ""
        prompt = f"Task hint: {guidance}\n\nBrief: {brief}" + (f"\nConstraints: {constraints}" if constraints else "") + extra
        return local_chat(prompt, system=self._system, num_predict=self._num_predict)

    def execute(self, input_data: dict[str, Any],
                action_runner: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        missing = [f for f in self._required if not str(input_data.get(f) or "").strip()]
        if missing:
            return {"status": "error", "error": f"missing required: {', '.join(missing)}"}
        brief = str(input_data["brief"]).strip()
        constraints = str(input_data.get("constraints") or "").strip()

        output = self._compose(brief, constraints, strict=False)
        if not output:
            return {"status": "degraded", "error": "local model unavailable",
                    "note": "start Ollama (qwythos:q4)"}

        passed, failed = self._gate.check(output)
        retried = False
        if not passed:
            # One stricter retry — the quality gate, not just a single shot.
            retried = True
            second = self._compose(brief, constraints, strict=True)
            if second:
                p2, f2 = self._gate.check(second)
                if p2 or len(f2) < len(failed):
                    output, passed, failed = second, p2, f2

        artifact = None
        if passed and input_data.get("save_artifact", True):
            try:
                name = f"{self.skill_id}-{uuid.uuid4().hex[:8]}.md"
                (_artifacts_dir() / name).write_text(output, encoding="utf-8")
                artifact = name
            except Exception:
                artifact = None

        return {
            "status": "success" if passed else "low_quality",
            "output": output,
            "quality": {"passed": passed, "failed_checks": failed, "retried": retried,
                        "gate": {"min_chars": self._gate.min_chars, "checks": self._gate.must_match_desc}},
            "confidence": 0.85 if passed else 0.4,
            "artifact": artifact,
            "model": model_name(),
            "skill": self.skill_id,
        }


# ── Top high-value skills, each with a skill-specific quality gate ──────────────
# (Reuses the curated library system_prompt for each id; adds the executable gate.)
TOP_SKILLS: dict[str, QualityGate] = {
    "blog_writing": QualityGate(min_chars=600, must_match=[r"^#{1,3}\s"], must_match_desc=["heading"]),
    "email_copywriting": QualityGate(min_chars=120, must_match=[r"subject\s*:", r"\b(cta|click|reply|book|buy|learn more)\b"],
                                     must_match_desc=["subject line", "call-to-action"]),
    "cold_email_outreach": QualityGate(min_chars=120, must_match=[r"subject\s*:"], must_match_desc=["subject line"]),
    "product_descriptions": QualityGate(min_chars=120),
    "social_captions": QualityGate(min_chars=40, must_match=[r"#\w+"], must_match_desc=["hashtag"]),
    "youtube_scripts": QualityGate(min_chars=300, must_match=[r"\b(hook|intro)\b", r"\b(cta|subscribe|call to action)\b"],
                                   must_match_desc=["hook", "CTA"]),
    "ad_copywriting": QualityGate(min_chars=80, must_match=[r"\b(headline|cta)\b|\n"], must_match_desc=["headline/structure"]),
    "landing_page_copy": QualityGate(min_chars=250, must_match=[r"\b(cta|sign up|get started|buy|try)\b"], must_match_desc=["CTA"]),
    "linkedin_post": QualityGate(min_chars=200),
    "newsletter_writing": QualityGate(min_chars=300),
    "case_study_writing": QualityGate(min_chars=400, must_match=[r"\b(result|outcome|impact)\b"], must_match_desc=["results"]),
    "press_releases": QualityGate(min_chars=300, must_match=[r"\b(FOR IMMEDIATE RELEASE|contact)\b"], must_match_desc=["PR structure"]),
    "headline_generation": QualityGate(min_chars=40),
    "video_script_writer": QualityGate(min_chars=250, must_match=[r"\b(hook|cta)\b"], must_match_desc=["hook/CTA"]),
    "meeting_notes": QualityGate(min_chars=120, must_match=[r"\b(action|next step|decision)\b"], must_match_desc=["action items"]),
}


def build_executable_skills() -> dict[str, ExecutableContentSkill]:
    """Instantiate every configured TOP skill whose id exists in the library."""
    lib = _library()
    out: dict[str, ExecutableContentSkill] = {}
    for sid, gate in TOP_SKILLS.items():
        if sid in lib:
            try:
                out[sid] = ExecutableContentSkill(sid, gate)
            except Exception:
                continue
    return out


# ── Category-derived quality gates: every skill gets a sensible gate without 570
# hand-written ones. Lenient by design (min length + no-refusal) so the long tail
# isn't falsely flagged; the 15 TOP_SKILLS keep their stricter structural gates. ──
_CATEGORY_GATE_RULES: list[tuple[tuple[str, ...], QualityGate]] = [
    (("content", "writing", "social", "branding", "communication"), QualityGate(min_chars=150)),
    (("lead", "sales", "support", "commerce", "money mode"), QualityGate(min_chars=120)),
    (("research", "analysis", "data", "finance", "trading"), QualityGate(min_chars=150)),
    (("development", "engineering", "technical", "integration", "runtime"), QualityGate(min_chars=100)),
    (("project", "strategy", "automation", "productivity", "company"), QualityGate(min_chars=150)),
    (("security", "governance", "autonomy"), QualityGate(min_chars=120)),
    (("crypto", "wallet", "compute", "growth", "marketing", "seo"), QualityGate(min_chars=120)),
]
_DEFAULT_GATE = QualityGate(min_chars=100)


def gate_for(skill_def: dict) -> QualityGate:
    """The gold hand-tuned gate for a TOP skill, else a category-derived gate."""
    sid = skill_def.get("id")
    if sid in TOP_SKILLS:
        return TOP_SKILLS[sid]
    cat = str(skill_def.get("category") or "").lower()
    for subs, gate in _CATEGORY_GATE_RULES:
        if any(s in cat for s in subs):
            return gate
    return _DEFAULT_GATE


def build_all_executable_skills(extra_library: dict[str, dict] | None = None) -> dict[str, ExecutableContentSkill]:
    """Make EVERY library skill executable + validated (full-quality upgrade), each
    with its category-derived (or gold) quality gate. Optionally include extra defs
    (e.g. generated definitions for previously-undefined skills)."""
    defs = dict(_library())
    if extra_library:
        for sid, sdef in extra_library.items():
            defs.setdefault(sid, sdef)
    out: dict[str, ExecutableContentSkill] = {}
    for sid, sdef in defs.items():
        try:
            out[sid] = ExecutableContentSkill(sid, gate_for(sdef), lib_def=sdef)
        except Exception:
            continue
    return out
