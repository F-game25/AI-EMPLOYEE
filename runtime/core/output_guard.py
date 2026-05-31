"""Output guard — detect PII echo and harmful content in LLM responses."""
from __future__ import annotations
import re

OutputViolation = type("OutputViolation", (), {
    "PII_ECHO":        "PII_ECHO",
    "HARMFUL_CONTENT": "HARMFUL_CONTENT",
    "SECRET_LEAK":     "SECRET_LEAK",
})()

class OutputGuardError(ValueError):
    pass

_PII_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),          # email
    re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),                                    # credit card
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                                          # SSN
    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),         # phone
]

_HARMFUL_PATTERNS = [
    re.compile(r"\bexploit\s+payload\b", re.I),
    re.compile(r"\bworking\s+exploit\b", re.I),
    re.compile(r"\bstep[s\s]+to\s+(hack|exploit|attack)\b", re.I),
    re.compile(r"\bhow\s+to\s+make\s+(a\s+)?(bomb|weapon|explosiv)\b", re.I),
    re.compile(r"\bsynthes[ie]s\s+of\s+\w+(ine|meth|fentanyl)\b", re.I),
]

_PII_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PII_CARD  = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
_PII_SSN   = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def scan_output(text: str) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for pat in _PII_PATTERNS:
        m = pat.search(text)
        if m:
            violations.append((OutputViolation.PII_ECHO, m.group(0)))
    for pat in _HARMFUL_PATTERNS:
        m = pat.search(text)
        if m:
            violations.append((OutputViolation.HARMFUL_CONTENT, m.group(0)))
    return violations


def redact_pii_echo(text: str) -> str:
    for pat in (_PII_EMAIL, _PII_CARD, _PII_SSN):
        text = pat.sub("[REDACTED]", text)
    return text


def guard_output(text: str, redact_pii: bool = True) -> tuple[str, list[tuple[str, str]]]:
    violations = scan_output(text)
    harmful = [v for v in violations if v[0] == OutputViolation.HARMFUL_CONTENT]
    if harmful:
        raise OutputGuardError(f"Harmful content detected: {harmful[0][1]}")
    out = redact_pii_echo(text) if redact_pii else text
    return out, violations
