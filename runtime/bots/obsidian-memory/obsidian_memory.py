"""Obsidian Memory Base — zelf-lerende Coding AI met persistente Obsidian vault geheugen.

Een zelf-verbeterende AI die een Obsidian vault gebruikt als extern brein:

  - Kennisophaling: relevante notities ophalen vóór elk antwoord
  - Redeneren: vault-kennis combineren met AI-kennis
  - Kennisupdate: nieuwe Obsidian-notities voorstellen na elke interactie
  - Obsidian-vriendelijk: frontmatter, interne links [[...]], Dataview queries

Commando's (via chatlog / Discord):
  obsidian ask <vraag>           — stel een vraag met vault-context
  obsidian search <query>        — zoek notities in de vault
  obsidian note <pad> <inhoud>   — maak of update een notitie in de vault
  obsidian index                 — herbouw de vault-index
  obsidian status                — toon vault-statistieken

Configuratie:
    OBSIDIAN_VAULT_PATH          — pad naar de Obsidian vault (vereist)
    OBSIDIAN_POLL_INTERVAL       — poll-interval in seconden (standaard: 5)
    OBSIDIAN_MAX_CONTEXT_NOTES   — max notities in context (standaard: 5)
    OBSIDIAN_LANGUAGE            — taal voor antwoorden: nl of en (standaard: nl)

Statusbestand:
  ~/.ai-employee/state/obsidian-memory.state.json
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "obsidian-memory.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
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


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
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
    if not _AI_AVAILABLE:
        return "AI router niet beschikbaar." if LANGUAGE != "en" else "AI router not available."
    try:
        result = _query_ai_for_agent(
            "obsidian-memory", prompt,
            system_prompt=system_prompt or _system_prompt(),
        )
        return result.get("answer", "Geen antwoord gegenereerd.")
    except Exception as exc:
        return f"AI-query mislukt: {exc}"


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
    """Write or overwrite a note in the vault.

    Returns (success, message).
    """
    if not vault_available():
        return False, (
            "Vault niet geconfigureerd. Stel OBSIDIAN_VAULT_PATH in."
            if LANGUAGE != "en" else
            "Vault not configured. Set OBSIDIAN_VAULT_PATH."
        )
    note_path = VAULT_PATH / rel_path
    try:
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        logger.info("obsidian-memory: wrote note %s", rel_path)
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

    # Suggest a session note
    note_path = f"AI/Sessies/{now_iso()[:10]}_vraag.md"
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
    """Rebuild the vault index and update the Master Index note."""
    if not vault_available():
        return (
            "⚠️ Vault niet geconfigureerd. Stel `OBSIDIAN_VAULT_PATH` in."
            if LANGUAGE != "en" else
            "⚠️ Vault not configured. Set `OBSIDIAN_VAULT_PATH`."
        )

    notes = list_vault_notes()
    note_count = len(notes)

    # Build or update master index note
    session_entries: list[str] = []
    state = _load_state()
    session_entries = state.get("session_log", [])

    master_content = _build_master_index_content(session_entries, note_count)
    write_vault_note("AI/AI-Memory-Log.md", master_content)

    return (
        f"✅ Vault-index herbouwd: **{note_count}** notities geïndexeerd. "
        f"Master index bijgewerkt: `AI/AI-Memory-Log.md`"
        if LANGUAGE != "en" else
        f"✅ Vault index rebuilt: **{note_count}** notes indexed. "
        f"Master index updated: `AI/AI-Memory-Log.md`"
    )


def cmd_status() -> str:
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


def run_once() -> int:
    """Process all pending chatlog entries. Returns number of commands handled."""
    entries = load_chatlog()
    if not entries:
        return 0

    handled = 0
    for entry in entries:
        text = entry.get("message", "") or entry.get("text", "")
        if not text:
            continue
        response = dispatch(text)
        if response is None:
            continue
        reply = {
            "ts": now_iso(),
            "from": "obsidian-memory",
            "message": response,
            "in_reply_to": entry.get("ts", ""),
        }
        append_chatlog(reply)
        handled += 1

    return handled


def main() -> None:
    print(SESSION_GREETING)

    state = _load_state()
    state["last_run"] = now_iso()
    write_state(state)

    vault_status = str(VAULT_PATH) if vault_available() else (
        "NIET geconfigureerd — stel OBSIDIAN_VAULT_PATH in" if LANGUAGE != "en"
        else "NOT configured — set OBSIDIAN_VAULT_PATH"
    )
    print(f"[{now_iso()}] obsidian-memory gestart; vault={vault_status}")

    # Process any pending agent tasks on start
    if AGENT_TASKS_DIR.exists():
        for task_file in sorted(AGENT_TASKS_DIR.glob("obsidian-memory_*.json")):
            try:
                task = json.loads(task_file.read_text())
                handle_agent_task(task)
                task_file.unlink()
            except Exception as exc:
                logger.warning("obsidian-memory: task error %s — %s", task_file.name, exc)

    while True:
        try:
            count = run_once()
            if count:
                print(f"[{now_iso()}] verwerkt {count} commando(s)")

            # Also check for orchestrator agent tasks
            if AGENT_TASKS_DIR.exists():
                for task_file in sorted(AGENT_TASKS_DIR.glob("obsidian-memory_*.json")):
                    try:
                        task = json.loads(task_file.read_text())
                        handle_agent_task(task)
                        task_file.unlink()
                    except Exception as exc:
                        logger.warning("obsidian-memory: task error %s — %s", task_file.name, exc)
        except Exception as exc:
            logger.error("obsidian-memory: loop error — %s", exc)

        state = _load_state()
        state["last_run"] = now_iso()
        write_state(state)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
