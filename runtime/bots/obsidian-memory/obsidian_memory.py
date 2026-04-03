"""Obsidian Memory Bot — AI knowledge-base integration for the AI Employee system.

Bridges the AI Employee with an Obsidian vault: allows asking questions that are
logged as notes, full-text keyword search across vault notes, writing new notes,
rebuilding the vault index, and reporting vault status.

Commands (via chatlog / WhatsApp / Dashboard):
  obsidian ask <question>     — ask a question and save it as a vault note
  obsidian search <query>     — full-text keyword search across vault notes
  obsidian note <title>|<body>— create a new vault note (pipe-separated)
  obsidian index              — rebuild the vault index
  obsidian status             — show vault stats and bot status

Configuration (env vars):
    OBSIDIAN_VAULT_PATH        — absolute path to the Obsidian vault (REQUIRED)
    OBSIDIAN_MEMORY_POLL       — poll interval in seconds (default: 5)

State files:
  ~/.ai-employee/state/obsidian-memory.state.json
"""
import json
import logging
import os
import re as _re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "obsidian-memory.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"

VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(AI_HOME / "vault")))
POLL_INTERVAL = int(os.environ.get("OBSIDIAN_MEMORY_POLL", "5"))

# ── Logging ───────────────────────────────────────────────────────────────────
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", ""))
POLL_INTERVAL = int(os.environ.get("OBSIDIAN_POLL_INTERVAL", "5"))
MAX_CONTEXT_NOTES = int(os.environ.get("OBSIDIAN_MAX_CONTEXT_NOTES", "5"))
LANGUAGE = os.environ.get("OBSIDIAN_LANGUAGE", "nl").lower()

# Number of characters used for index snippets
_INDEX_SNIPPET_LENGTH = 200

# Stopwords filtered out during keyword search, keyed by language
_STOPWORDS: dict = {
    "nl": {"", "de", "het", "een", "en", "van", "in", "is", "op", "dat", "er", "te", "voor", "met"},
    "en": {"", "the", "a", "an", "and", "of", "in", "is", "to", "for", "with", "that", "on", "it"},
}

# ── Vault helpers ─────────────────────────────────────────────────────────────


def vault_available() -> bool:
    """Return True when the configured vault path exists and is a directory."""
    raw = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    return bool(raw) and VAULT_PATH.is_dir()

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("obsidian-memory")

# ── AI router ─────────────────────────────────────────────────────────────────

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

# ── Session greeting ──────────────────────────────────────────────────────────

SESSION_GREETING = (
    "✅ Obsidian Memory Base actief. Vault geladen. "
    "Wat gaan we vandaag bouwen of verbeteren?"
)

# ── System prompts ────────────────────────────────────────────────────────────

_SYSTEM_NL = (
    "Je bent een extreem slimme, zelf-verbeterende Coding AI met een persistente "
    "kennisbank en long-term memory in een Obsidian vault.\n\n"
    "Je hebt twee doelen:\n"
    "1. Altijd slimmer worden door actief de Obsidian vault te gebruiken als extern brein.\n"
    "2. Code schrijven, problemen oplossen en kennis opbouwen zodat alles automatisch "
    "bijdraagt aan een steeds betere kennisgrafiek in Obsidian.\n\n"
    "Werkwijze (volg dit altijd):\n"
    "1. Retrieval: haal relevante kennis op uit de vault vóór je antwoord geeft.\n"
    "2. Reasoning: combineer vault-kennis met je eigen kennis.\n"
    "3. Knowledge update: stel aan het einde 1-3 concrete Obsidian-notities voor "
    "(exacte bestandsnaam + map + volledige Markdown-inhoud).\n"
    "4. Gebruik altijd [[interne Obsidian links]], frontmatter, Dataview queries.\n\n"
    "Antwoord altijd in het Nederlands tenzij de gebruiker expliciet Engels vraagt.\n"
    "Wees behulpzaam, precies en proactief over het bouwen van ons gezamenlijke tweede brein."
)

_SYSTEM_EN = (
    "You are an extremely smart, self-improving Coding AI with persistent knowledge "
    "and long-term memory stored in an Obsidian vault.\n\n"
    "Your two goals:\n"
    "1. Always become smarter by actively using the Obsidian vault as your external brain.\n"
    "2. Write code, solve problems and build knowledge so that everything contributes "
    "to an ever-better knowledge graph in Obsidian.\n\n"
    "Workflow (always follow this):\n"
    "1. Retrieval: fetch relevant knowledge from the vault before answering.\n"
    "2. Reasoning: combine vault knowledge with your own expertise.\n"
    "3. Knowledge update: at the end suggest 1-3 concrete Obsidian notes "
    "(exact filename + folder + full Markdown content).\n"
    "4. Always use [[internal Obsidian links]], frontmatter, and Dataview queries.\n\n"
    "Answer in Dutch unless the user explicitly asks for English."
)


def _system_prompt() -> str:
    return _SYSTEM_EN if LANGUAGE == "en" else _SYSTEM_NL


# ── Helpers ───────────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        lines = [line for line in CHATLOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        lines = [line for line in CHATLOG.read_text().splitlines() if line.strip()]
        return [json.loads(line) for line in lines]
    except Exception:
        return []


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def write_orchestrator_result(subtask_id: str, result_text: str, status: str = "done") -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{subtask_id}.json"
    result_file.write_text(json.dumps({
        "subtask_id": subtask_id,
        "status": status,
        "result": result_text,
        "completed_at": now_iso(),
    }))


def ai_query(prompt: str, system_prompt: str = "") -> str:
    router_unavailable = "AI router not available." if LANGUAGE == "en" else "AI router niet beschikbaar."
    missing_answer = "No answer generated." if LANGUAGE == "en" else "Geen antwoord gegenereerd."
    query_failed = "AI query failed" if LANGUAGE == "en" else "AI-query mislukt"
    if not _AI_AVAILABLE:
        return router_unavailable
    try:
        result = _query_ai_for_agent(
            "obsidian-memory", prompt,
            system_prompt=system_prompt or _system_prompt(),
        )
        return result.get("answer", missing_answer)
    except Exception as exc:
        return f"{query_failed}: {exc}"


# ── Vault helpers ─────────────────────────────────────────────────────────────


def list_vault_notes() -> list[Path]:
    """Return all .md files in the vault."""
    if not vault_available():
        return []
    return sorted(VAULT_PATH.rglob("*.md"))


def read_note(path: Path) -> str:
    """Read the text content of a vault note."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("obsidian-memory: could not read %s — %s", path, exc)
        return ""


def _note_relative(path: Path) -> str:
    """Return the note's path relative to the vault root."""
    try:
        return str(path.relative_to(VAULT_PATH))
    except ValueError:
        return str(path)


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block from note text."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip()
    return text


def build_vault_index() -> dict:
    """Build a lightweight index: {relative_path: first snippet of body}."""
    index: dict = {}
    for note in list_vault_notes():
        rel = _note_relative(note)
        body = _strip_frontmatter(read_note(note))
        index[rel] = body[:_INDEX_SNIPPET_LENGTH].replace("\n", " ").strip()
    return index


def search_vault(query: str, *, top_k: int = MAX_CONTEXT_NOTES) -> list[dict]:
    """Keyword search across all vault notes.

    Returns top_k matches as list of {path, snippet, score}.
    """
    if not vault_available():
        return []

    query_lower = query.lower()
    stopwords = _STOPWORDS.get(LANGUAGE, _STOPWORDS["nl"])
    keywords = set(re.split(r"\W+", query_lower)) - stopwords
    if not keywords:
        return []

    scored: list[dict] = []
    for note in list_vault_notes():
        content = read_note(note)
        text_lower = content.lower()
        matches = sum(1 for kw in keywords if kw in text_lower)
        if matches > 0:
            # Grab a snippet around the first keyword hit
            first_kw = next((kw for kw in keywords if kw in text_lower), "")
            pos = text_lower.find(first_kw) if first_kw else 0
            snippet = content[max(0, pos - 80): pos + 200].strip()
            scored.append({
                "path": _note_relative(note),
                "snippet": snippet,
                "score": matches / len(keywords),
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def write_vault_note(rel_path: str, content: str) -> tuple[bool, str]:
    """Write or overwrite a note in the vault at the given relative path.

    The path is validated: it must be a relative path that stays within the
    vault root (no ``..`` traversal, no absolute paths).

    Returns (success, message).
    """
    if not vault_available():
        return False, (
            "Vault not configured. Set OBSIDIAN_VAULT_PATH."
            if LANGUAGE == "en" else
            "Vault niet geconfigureerd. Stel OBSIDIAN_VAULT_PATH in."
        )

    # Security: reject absolute paths and prevent path-traversal
    raw = rel_path.strip()
    if not raw:
        err = "Path may not be empty." if LANGUAGE == "en" else "Pad mag niet leeg zijn."
        return False, err
    if raw.startswith("/") or raw.startswith("\\"):
        err = "Absolute paths are not allowed." if LANGUAGE == "en" else "Absolute paden zijn niet toegestaan."
        return False, err

    note_path = (VAULT_PATH / raw).resolve()
    vault_resolved = VAULT_PATH.resolve()
    if not note_path.is_relative_to(vault_resolved):
        err = (
            "Path traversal detected: target is outside the vault."
            if LANGUAGE == "en" else
            "Padtraversal gedetecteerd: doel ligt buiten de vault."
        )
        return False, err

    try:
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        return True, str(note_path.relative_to(VAULT_PATH.resolve()))
    except Exception as exc:
        return False, f"Failed to write note: {exc}"


def build_vault_index() -> dict[str, Any]:
    """Build a metadata index of all notes in the vault."""
    index: dict[str, Any] = {}
    for note_rel_path in list_vault_notes():
        try:
            full_path = VAULT_PATH / note_rel_path
            content = full_path.read_text(encoding="utf-8", errors="replace")
            index[str(note_rel_path)] = {
                "size": len(content),
                "lines": content.count("\n"),
                "preview": content[:200],
            }
        except Exception:
            pass
    return index


# ── System prompts ────────────────────────────────────────────────────────────

_SYSTEM_MEMORY = (
    "You are an AI knowledge manager integrated with an Obsidian vault. "
    "Answer questions concisely and accurately, drawing on your knowledge. "
    "Provide well-structured responses suitable for saving as Obsidian notes."
)
        logger.info("obsidian-memory: wrote note %s", raw)
        return True, note_path.as_posix()
    except Exception as exc:
        return False, str(exc)


# ── Knowledge-update note builder ─────────────────────────────────────────────

_MASTER_INDEX_TEMPLATE = """\
---
aliases: [AI Memory Log, Master Index]
tags: [obsidian-memory, knowledge-graph, index]
created: {created}
updated: {updated}
---

# 🧠 AI Memory Log — Master Index

Automatisch bijgehouden door de [[Obsidian Memory Base]] bot.

## Recente sessies

{session_entries}

## Statistieken

- Totaal notities in vault: {note_count}
- Laatste update: {updated}

## Dataview query — recente kennis

```dataview
LIST FROM "" WHERE contains(tags, "ai-memory") SORT file.mtime DESC LIMIT 20
```
"""


def _build_master_index_content(session_entries: list[str], note_count: int) -> str:
    ts = now_iso()
    entries = "\n".join(f"- {e}" for e in session_entries[-20:]) if session_entries else "- (geen sessies)"
    return _MASTER_INDEX_TEMPLATE.format(
        created=ts,
        updated=ts,
        session_entries=entries,
        note_count=note_count,
    )


def _build_session_note_content(question: str, answer: str, sources: list[dict]) -> str:
    """Build a ready-to-paste Obsidian session note."""
    ts = now_iso()
    date = ts[:10]
    source_links = "\n".join(
        f"- [[{s['path'].replace('.md', '')}]]" for s in sources
    ) if sources else "- (geen bestaande notities gebruikt)"

    return (
        f"---\n"
        f"aliases: []\n"
        f"tags: [ai-memory, coding-ai, session]\n"
        f"created: {ts}\n"
        f"updated: {ts}\n"
        f"---\n\n"
        f"# 🤖 AI Sessie — {date}\n\n"
        f"## Vraag\n\n"
        f"{question}\n\n"
        f"## Antwoord\n\n"
        f"{answer}\n\n"
        f"## Gebruikte vault-notities\n\n"
        f"{source_links}\n\n"
        f"## Gelinkte notities\n\n"
        f"- [[AI-Memory-Log]]\n"
    )


# ── Command handlers ──────────────────────────────────────────────────────────


def cmd_ask(question: str) -> str:
    """Handle 'obsidian ask <question>': answer and save as vault note."""
    if not question.strip():
        return "Usage: `obsidian ask <question>`"

    answer = ai_query(question, system_prompt=_SYSTEM_MEMORY)

    # Build unique note path: AI/Sessies/<timestamp>_<slug>.md
    _slug = _re.sub(r"[^a-z0-9]+", "-", question.lower().strip())[:40].strip("-")
    _timestamp = now_iso().replace(":", "-").replace(".", "-")[:19]
    note_path = f"AI/Sessies/{_timestamp}_{_slug}.md"

    frontmatter = (
        "---\n"
        f"date: {now_iso()}\n"
        f"question: {question[:120]}\n"
        "tags: [ai-session, vraag]\n"
        "---\n\n"
    )
    content = frontmatter + f"## Vraag\n{question}\n\n## Antwoord\n{answer}\n"

    ok, detail = write_vault_note(note_path, content)
    if ok:
        return f"🧠 Antwoord opgeslagen in vault: `{note_path}`\n\n{answer}"
    return f"🧠 {answer}\n\n_(Notitie opslaan mislukt: {detail})_"


def cmd_search(query: str) -> str:
    """Handle 'obsidian search <query>': keyword search across vault notes."""
    if not query.strip():
        return "Usage: `obsidian search <query>`"

    notes = list_vault_notes()
    if not notes:
        return "❌ Geen notities gevonden in de vault (of vault niet geconfigureerd)."

    query_lower = query.lower()
    matches: list[dict[str, Any]] = []

    for note_rel in notes:
        content = read_vault_note(note_rel)
        if content is None:
            continue
        if query_lower in content.lower():
            # Find a snippet around the first match
            idx = content.lower().find(query_lower)
            start = max(0, idx - 60)
            end = min(len(content), idx + 120)
            snippet = content[start:end].replace("\n", " ").strip()
            matches.append({"path": str(note_rel), "snippet": snippet})
        if len(matches) >= 10:
            break

    if not matches:
        return f"🔍 Geen resultaten gevonden voor: **{query}**"

    lines = [f"🔍 **{len(matches)}** resultaat(en) voor: `{query}`\n"]
    for m in matches:
        lines.append(f"• `{m['path']}`\n  …{m['snippet']}…")
    return "\n".join(lines)


def cmd_note(text: str) -> str:
    """Handle 'obsidian note <title>|<body>': create a new vault note."""
    if not text.strip():
        return "Usage: `obsidian note <title>|<body>`"

    if "|" in text:
        title, body = text.split("|", 1)
        title = title.strip()
        body = body.strip()
    else:
        title = text.strip()[:80]
        body = text.strip()

    if not title:
        return "❌ Geef een titel op: `obsidian note <title>|<body>`"

    _slug = _re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-")
    _timestamp = now_iso().replace(":", "-").replace(".", "-")[:19]
    note_path = f"AI/Notities/{_timestamp}_{_slug}.md"

    frontmatter = (
        "---\n"
        f"date: {now_iso()}\n"
        f"title: {title[:120]}\n"
        "tags: [ai-note]\n"
        "---\n\n"
    )
    content = frontmatter + f"# {title}\n\n{body}\n"

    ok, detail = write_vault_note(note_path, content)
    if ok:
        return f"✅ Notitie aangemaakt: `{note_path}`"
    return f"❌ Notitie aanmaken mislukt: {detail}"


def cmd_index() -> str:
    """Handle 'obsidian index': rebuild the vault index."""
    notes = list_vault_notes()
    note_count = len(notes)

    if note_count == 0:
        return (
            "⚠️ Geen notities gevonden in de vault. "
            "Controleer `OBSIDIAN_VAULT_PATH`."
        )

    # Actually build and persist the index
    index = build_vault_index()

    state = _load_state()
    state["vault_index"] = index
    state["vault_index_built_at"] = now_iso()
    _save_state(state)

    lang = os.environ.get("OBSIDIAN_LANG", "nl").lower()
    if lang == "en":
        return (
            f"✅ Vault index rebuilt and saved: **{note_count}** notes indexed. "
            f"Master index updated: `AI/AI-Memory-Log.md`"
        )
    return (
        f"✅ Vault-index herbouwd en opgeslagen: **{note_count}** notities. "
    """Answer a question using vault context + AI synthesis."""
    if not question.strip():
        return (
            "Gebruik: `obsidian ask <vraag>` — bijv. `obsidian ask Hoe werkt FastAPI?`"
            if LANGUAGE != "en" else
            "Usage: `obsidian ask <question>`"
        )

    sources = search_vault(question)

    context_parts: list[str] = []
    if sources:
        context_parts.append(
            "Relevante kennis uit de Obsidian vault:" if LANGUAGE != "en"
            else "Relevant knowledge from the Obsidian vault:"
        )
        for i, s in enumerate(sources, 1):
            context_parts.append(f"[{i}] **{s['path']}**\n{s['snippet']}")
        context_parts.append("")

    context_parts.append(
        f"Vraag: {question}" if LANGUAGE != "en" else f"Question: {question}"
    )

    full_prompt = "\n\n".join(context_parts)
    answer = ai_query(full_prompt)

    # Suggest a session note with a unique filename (timestamp + question slug)
    _slug = re.sub(r"\W+", "-", question.lower().strip())[:40].strip("-")
    _ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    note_path = f"AI/Sessies/{_ts}_{_slug}.md"
    note_content = _build_session_note_content(question, answer, sources)

    suggestion = (
        f"\n\n---\n📝 **Voorgestelde Obsidian-notitie:** `{note_path}`\n"
        f"```markdown\n{note_content}\n```"
        if LANGUAGE != "en" else
        f"\n\n---\n📝 **Suggested Obsidian note:** `{note_path}`\n"
        f"```markdown\n{note_content}\n```"
    )

    return answer + suggestion


def cmd_search(query: str) -> str:
    """Search vault notes by keyword and return top matches."""
    if not query.strip():
        return (
            "Gebruik: `obsidian search <zoekopdracht>`"
            if LANGUAGE != "en" else
            "Usage: `obsidian search <query>`"
        )

    if not vault_available():
        return (
            "⚠️ Vault niet geconfigureerd. Stel `OBSIDIAN_VAULT_PATH` in in `.env`."
            if LANGUAGE != "en" else
            "⚠️ Vault not configured. Set `OBSIDIAN_VAULT_PATH` in `.env`."
        )

    results = search_vault(query)
    if not results:
        return (
            f"Geen notities gevonden voor: **{query}**"
            if LANGUAGE != "en" else
            f"No notes found for: **{query}**"
        )

    lines = [
        f"🔍 **Vault-zoekresultaten voor '{query}':**" if LANGUAGE != "en"
        else f"🔍 **Vault search results for '{query}':**",
        "",
    ]
    for r in results:
        lines.append(f"**{r['path']}** (score: {r['score']:.2f})")
        lines.append(f"> {r['snippet'][:200]}")
        lines.append("")
    return "\n".join(lines)


def cmd_note(rel_path: str, content: str) -> str:
    """Write a note to the vault at the given relative path."""
    if not rel_path:
        return (
            "Gebruik: `obsidian note <pad> <markdown-inhoud>`"
            if LANGUAGE != "en" else
            "Usage: `obsidian note <path> <markdown content>`"
        )
    ok, msg = write_vault_note(rel_path, content)
    if ok:
        return (
            f"✅ Notitie opgeslagen: `{msg}`"
            if LANGUAGE != "en" else
            f"✅ Note saved: `{msg}`"
        )
    return (
        f"❌ Kon notitie niet opslaan: {msg}"
        if LANGUAGE != "en" else
        f"❌ Could not save note: {msg}"
    )


def cmd_index() -> str:
    """Build and persist a vault index, then update the Master Index note."""
    if not vault_available():
        return (
            "⚠️ Vault not configured. Set `OBSIDIAN_VAULT_PATH`."
            if LANGUAGE == "en" else
            "⚠️ Vault niet geconfigureerd. Stel `OBSIDIAN_VAULT_PATH` in."
        )

    # Build the in-memory index and persist it to state
    index = build_vault_index()
    note_count = len(index)
    index_state_path = STATE_FILE.parent / "obsidian-vault-index.json"
    index_state_path.parent.mkdir(parents=True, exist_ok=True)
    index_state_path.write_text(
        json.dumps({"built_at": now_iso(), "notes": index}, indent=2, ensure_ascii=False)
    )
    logger.info("obsidian-memory: persisted vault index with %d notes to %s", note_count, index_state_path)

    # Update master index note in vault
    state = _load_state()
    session_entries = state.get("session_log", [])
    master_content = _build_master_index_content(session_entries, note_count)
    write_vault_note("AI/AI-Memory-Log.md", master_content)

    return (
        f"✅ Vault index built and saved: **{note_count}** notes indexed. "
        f"Master index updated: `AI/AI-Memory-Log.md`"
        if LANGUAGE == "en" else
        f"✅ Vault-index gebouwd en opgeslagen: **{note_count}** notities geïndexeerd. "
        f"Master index bijgewerkt: `AI/AI-Memory-Log.md`"
    )


def cmd_status() -> str:
    """Handle 'obsidian status': show vault and bot status."""
    notes = list_vault_notes()
    note_count = len(notes)
    vault_exists = VAULT_PATH.exists()
    state = _load_state()
    last_idx = state.get("last_processed_idx", 0)
    index_built_at = state.get("vault_index_built_at", "nooit")
    index_size = len(state.get("vault_index", {}))

    vault_info = f"`{VAULT_PATH}`" if vault_exists else f"`{VAULT_PATH}` *(niet gevonden)*"
    ai_status = "✅ beschikbaar" if _AI_AVAILABLE else "❌ niet beschikbaar"

    return (
        f"🗂️ **Obsidian Memory Status**\n"
        f"• Vault: {vault_info}\n"
        f"• Notities: **{note_count}** .md bestanden\n"
        f"• Index: **{index_size}** entries (bijgewerkt: {index_built_at})\n"
        f"• Chatlog verwerkt t/m index: **{last_idx}**\n"
        f"• AI router: {ai_status}\n"
        f"• Gestart: {now_iso()}"
    )


# ── Command dispatch ──────────────────────────────────────────────────────────


def dispatch(message: str) -> str | None:
    """Dispatch an 'obsidian ...' command. Returns None if message doesn't match."""
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("obsidian ") and msg_lower != "obsidian":
        return None

    rest = msg[9:].strip() if msg_lower.startswith("obsidian ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("ask "):
        return cmd_ask(rest[4:].strip())
    if rest_lower.startswith("search "):
        return cmd_search(rest[7:].strip())
    if rest_lower.startswith("note "):
        return cmd_note(rest[5:].strip())
    if rest_lower == "index":
        return cmd_index()
    if rest_lower == "status":
        return cmd_status()
    if rest_lower in ("help", ""):
        return (
            "🗂️ *Obsidian Memory Commands:*\n"
            "  `obsidian ask <vraag>` — stel een vraag en sla op als notitie\n"
            "  `obsidian search <query>` — zoek in vault-notities\n"
            "  `obsidian note <titel>|<inhoud>` — maak een nieuwe notitie\n"
            "  `obsidian index` — herbouw de vault-index\n"
            "  `obsidian status` — toon vault-statistieken"
        )

    return "Onbekend commando. Probeer `obsidian help`"


# ── Main poll loop ────────────────────────────────────────────────────────────


def run_once() -> int:
    entries = load_chatlog()
    if not entries:
        return 0

    state = _load_state()
    last_idx = state.get("last_processed_idx", 0)
    new_entries = entries[last_idx:]

    handled = 0
    for entry in new_entries:
        # Only process user-originated messages
        if entry.get("type") not in ("user", None) or entry.get("bot") == "obsidian-memory":
    """Return vault statistics and recent session info."""
    state = _load_state()
    note_count = len(list_vault_notes()) if vault_available() else 0
    session_count = len(state.get("session_log", []))
    vault_info = str(VAULT_PATH) if vault_available() else (
        "niet geconfigureerd" if LANGUAGE != "en" else "not configured"
    )

    if LANGUAGE != "en":
        return (
            f"📊 **Obsidian Memory Base — Status**\n\n"
            f"- Vault: `{vault_info}`\n"
            f"- Notities in vault: **{note_count}**\n"
            f"- Sessies bijgehouden: **{session_count}**\n"
            f"- Taal: **{LANGUAGE}**\n"
            f"- Laatste update: {state.get('last_run', 'nooit')}\n"
        )
    return (
        f"📊 **Obsidian Memory Base — Status**\n\n"
        f"- Vault: `{vault_info}`\n"
        f"- Notes in vault: **{note_count}**\n"
        f"- Sessions tracked: **{session_count}**\n"
        f"- Language: **{LANGUAGE}**\n"
        f"- Last update: {state.get('last_run', 'never')}\n"
    )


# ── State helpers ─────────────────────────────────────────────────────────────


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"session_log": [], "last_run": None}


def _save_session(question: str) -> None:
    state = _load_state()
    log: list = state.get("session_log", [])
    log.append(f"{now_iso()[:10]} — {question[:80]}")
    if len(log) > 200:
        log = log[-200:]
    state["session_log"] = log
    state["last_run"] = now_iso()
    write_state(state)


# ── Command dispatcher ────────────────────────────────────────────────────────


def dispatch(text: str) -> Optional[str]:
    """Parse and dispatch an obsidian command from chatlog text.

    Returns the response string, or None if the text is not an obsidian command.
    """
    text = text.strip()
    lower = text.lower()

    if not lower.startswith("obsidian "):
        return None

    rest = text[len("obsidian "):].strip()
    parts = rest.split(None, 1)
    subcmd = parts[0].lower() if parts else ""
    args = parts[1].strip() if len(parts) > 1 else ""

    if subcmd == "ask":
        _save_session(args)
        return cmd_ask(args)
    if subcmd == "search":
        return cmd_search(args)
    if subcmd == "note":
        note_parts = args.split(None, 1)
        note_path = note_parts[0] if note_parts else ""
        note_content = note_parts[1] if len(note_parts) > 1 else ""
        return cmd_note(note_path, note_content)
    if subcmd == "index":
        return cmd_index()
    if subcmd == "status":
        return cmd_status()
    if subcmd in ("help", "hulp", ""):
        return _help_text()

    return (
        f"Onbekend obsidian-commando: `{subcmd}`. Gebruik `obsidian help` voor hulp."
        if LANGUAGE != "en" else
        f"Unknown obsidian command: `{subcmd}`. Use `obsidian help` for usage."
    )


def _help_text() -> str:
    if LANGUAGE != "en":
        return (
            "**Obsidian Memory Base — Commando's**\n\n"
            "`obsidian ask <vraag>` — stel een vraag met vault-context en AI-antwoord\n"
            "`obsidian search <query>` — zoek notities in de vault\n"
            "`obsidian note <pad> <inhoud>` — schrijf een notitie naar de vault\n"
            "`obsidian index` — herbouw de vault-index en master index\n"
            "`obsidian status` — toon vault-statistieken\n"
        )
    return (
        "**Obsidian Memory Base — Commands**\n\n"
        "`obsidian ask <question>` — ask a question with vault context + AI answer\n"
        "`obsidian search <query>` — search notes in the vault\n"
        "`obsidian note <path> <content>` — write a note to the vault\n"
        "`obsidian index` — rebuild the vault index and master index\n"
        "`obsidian status` — show vault statistics\n"
    )


# ── Agent-task handler (for task-orchestrator integration) ────────────────────


def handle_agent_task(task: dict) -> None:
    """Process a task dispatched by the task-orchestrator."""
    subtask_id = task.get("subtask_id", "")
    prompt = task.get("prompt", "")
    result = cmd_ask(prompt) if prompt else cmd_status()
    write_orchestrator_result(subtask_id, result)


# ── Chatlog poll loop ──────────────────────────────────────────────────────────


def process_new_entries(chatlog: list, last_idx: int) -> tuple[int, int]:
    """Process new chatlog entries starting from last_idx.

    Only processes entries with ``type == "user"`` to avoid feedback loops.

    Returns (new_last_idx, handled_count).
    """
    new_entries = chatlog[last_idx:]
    new_last_idx = len(chatlog)
    handled = 0

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        text = entry.get("message", "") or entry.get("text", "")
        if not text:
            continue
        response = dispatch(text)
        if response is None:
            continue
        reply = {
            "ts": now_iso(),
            "type": "bot",
            "bot": "obsidian-memory",
            "message": response,
            "in_reply_to": entry.get("ts", ""),
        }
        append_chatlog(reply)
        handled += 1

    state["last_processed_idx"] = last_idx + len(new_entries)
    _save_state(state)
    return handled


def main() -> None:
    vault_status = "found" if VAULT_PATH.exists() else "NOT FOUND"
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(
        f"[{now_iso()}] obsidian-memory started; "
        f"vault={VAULT_PATH} ({vault_status}); "
        f"poll={POLL_INTERVAL}s; {ai_status}"
    )

    VAULT_PATH.mkdir(parents=True, exist_ok=True)

    _save_state({
        **_load_state(),
        "bot": "obsidian-memory",
        "ts": now_iso(),
        "status": "starting",
        "vault_path": str(VAULT_PATH),
        "ai_available": _AI_AVAILABLE,
    })

    while True:
        try:
            handled = run_once()
            if handled:
                logger.info("obsidian-memory: handled %d message(s)", handled)
        except Exception as exc:
            logger.error("obsidian-memory: run_once error: %s", exc)

        _save_state({
            **_load_state(),
            "bot": "obsidian-memory",
            "ts": now_iso(),
            "status": "running",
        })
        })
        handled += 1

    return new_last_idx, handled


def main() -> None:
    print(SESSION_GREETING)

    # Write initial state
    init_state = _load_state()
    init_state["last_run"] = now_iso()
    write_state(init_state)

    vault_status = str(VAULT_PATH) if vault_available() else (
        "NOT configured — set OBSIDIAN_VAULT_PATH" if LANGUAGE == "en"
        else "NIET geconfigureerd — stel OBSIDIAN_VAULT_PATH in"
    )
    print(f"[{now_iso()}] obsidian-memory gestart; vault={vault_status}")

    # Start tracking from the current end of the chatlog to avoid replaying history
    last_processed_idx = len(load_chatlog())

    while True:
        try:
            # Process agent tasks from the orchestrator
            if AGENT_TASKS_DIR.exists():
                for task_file in sorted(AGENT_TASKS_DIR.glob("obsidian-memory_*.json")):
                    try:
                        task = json.loads(task_file.read_text())
                        handle_agent_task(task)
                        task_file.unlink()
                    except Exception as exc:
                        logger.warning("obsidian-memory: task error %s — %s", task_file.name, exc)

            # Process new chatlog entries (only type=user, from last_processed_idx onwards)
            chatlog = load_chatlog()
            last_processed_idx, count = process_new_entries(chatlog, last_processed_idx)
            if count:
                print(f"[{now_iso()}] verwerkt {count} commando(s)")

        except Exception as exc:
            logger.error("obsidian-memory: loop error — %s", exc)

        # Read-modify-write to avoid clobbering session_log written by _save_session()
        current_state = _load_state()
        current_state["last_run"] = now_iso()
        write_state(current_state)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
