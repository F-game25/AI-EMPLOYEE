"""Prompt injection guard — scan, sanitize, and block malicious prompts."""
from __future__ import annotations
import re

PromptThreatLevel = type("PromptThreatLevel", (), {
    "SAFE":    "SAFE",
    "WARN":    "WARN",
    "BLOCKED": "BLOCKED",
})()

class PromptInjectionError(ValueError):
    pass

_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+all\s+previous\s+instructions", re.I), "ignore_previous"),
    (re.compile(r"you\s+are\s+now\s+\w+", re.I), "persona_override"),
    (re.compile(r"disregard\s+(all\s+)?(prior|previous)\s+", re.I), "disregard_prior"),
    (re.compile(r"system\s*prompt\s*[:=]", re.I), "system_prompt_leak"),
    (re.compile(r"jailbreak", re.I), "jailbreak"),
    (re.compile(r"do\s+anything\s+now", re.I), "dan"),
    (re.compile(r"act\s+as\s+if\s+(you\s+have\s+no\s+restrictions|you\s+are)", re.I), "act_as"),
]

_DANGEROUS_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f"       # control chars except \t\n\r
    r"​-‏‪-‮⁠-⁩"  # zero-width + direction overrides
    r"﻿]"                                   # BOM
)


def scan_prompt(text: str) -> tuple[str, list[str]]:
    matches = [name for pat, name in _INJECTION_PATTERNS if pat.search(text)]
    level = PromptThreatLevel.BLOCKED if matches else PromptThreatLevel.SAFE
    return level, matches


def sanitize_prompt(text: str) -> str:
    return _DANGEROUS_CHARS.sub("", text)


def check_and_sanitize(text: str) -> tuple[str, str, list[str]]:
    clean = sanitize_prompt(text)
    level, patterns = scan_prompt(clean)
    if level == PromptThreatLevel.BLOCKED:
        raise PromptInjectionError(f"Prompt injection detected: {patterns}")
    return clean, level, patterns
