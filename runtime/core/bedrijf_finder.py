"""Bedrijf Finder — genereer lokale bedrijfskandidaten via Ollama.

Geen externe scraping. Ollama genereert een lijst van realistische
lokale bedrijfsnamen zonder website voor een gegeven stad + branche.
Lars selecteert wat hij wil toevoegen.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:latest")

# Validate at import time — only http/https to localhost/LAN allowed.
# urlopen target is fully determined by this env var, never by user input.
if not _OLLAMA_HOST.startswith(("http://", "https://")):
    raise ValueError(f"OLLAMA_HOST must start with http:// or https://, got: {_OLLAMA_HOST!r}")


def _llm(prompt: str, max_tokens: int = 600) -> str:
    payload = {
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "system": (
            "Je bent een assistent die lokale Nederlandse bedrijven kent. "
            "Geef altijd valide JSON terug, niets anders."
        ),
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    req = urllib.request.Request(
        f"{_OLLAMA_HOST}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:  # nosec B310 — scheme validated above
        body = json.loads(resp.read())
    return body.get("response", "").strip()


def zoek_bedrijven(stad: str, branche: str, aantal: int = 8) -> dict:
    """Genereer een lijst van lokale bedrijfskandidaten.

    Returns:
        {"ok": True, "kandidaten": [{"bedrijfsnaam": ..., "plaats": ..., "branche": ..., "contact": ""}]}
    """
    prompt = (
        f"Geef een JSON-array met {aantal} fictieve maar realistische lokale {branche}bedrijven "
        f"in {stad} die waarschijnlijk geen eigen website hebben. "
        f"Elk object heeft alleen de velden: bedrijfsnaam, contact (leeg string). "
        f"Geen uitleg. Alleen de JSON-array."
    )
    raw = _llm(prompt)

    # Extract JSON array from response
    start = raw.find("[")
    end   = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return {"ok": False, "error": f"Geen JSON-array in antwoord: {raw[:200]}"}

    try:
        items = json.loads(raw[start:end])
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"JSON parse fout: {exc} — {raw[start:start+200]}"}

    kandidaten = []
    for item in items:
        naam = item.get("bedrijfsnaam") or item.get("naam") or item.get("name", "")
        if not naam:
            continue
        kandidaten.append({
            "bedrijfsnaam": naam.strip(),
            "plaats": stad.strip(),
            "branche": branche.strip(),
            "contact": item.get("contact", ""),
        })

    return {"ok": True, "kandidaten": kandidaten}
