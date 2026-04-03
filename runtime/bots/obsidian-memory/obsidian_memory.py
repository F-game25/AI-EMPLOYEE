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


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        lines = [line for line in CHATLOG.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [json.loads(line) for line in lines]
    except Exception:
        return []


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def ai_query(prompt: str, system_prompt: str = "") -> str:
    if not _AI_AVAILABLE:
        return "AI router not available."
    try:
        result = _query_ai_for_agent("obsidian-memory", prompt, system_prompt=system_prompt)
        return result.get("answer", "No response generated.")
    except Exception as exc:
        return f"AI query failed: {exc}"


# ── Vault helpers ─────────────────────────────────────────────────────────────


def list_vault_notes() -> list[Path]:
    """Return a list of all .md file paths relative to VAULT_PATH."""
    if not VAULT_PATH.exists():
        return []
    try:
        return [p.relative_to(VAULT_PATH) for p in VAULT_PATH.rglob("*.md")]
    except Exception:
        return []


def read_vault_note(rel_path: str | Path) -> str | None:
    """Read the content of a vault note. Returns None if not found."""
    try:
        full_path = VAULT_PATH / rel_path
        if not full_path.exists():
            return None
        return full_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def write_vault_note(rel_path: str, content: str) -> tuple[bool, str]:
    """Write content to a vault note at rel_path (relative to VAULT_PATH).

    Returns (True, note_path_str) on success, (False, error_message) on failure.
    """
    # Validate path is safe
    rel = PurePosixPath(rel_path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        return False, "Invalid path: must be relative and contain no '..' segments."
    if not str(rel_path).endswith(".md"):
        return False, "Invalid path: must end with .md"
    note_path = (VAULT_PATH / rel_path).resolve()
    if not str(note_path).startswith(str(VAULT_PATH.resolve())):
        return False, "Invalid path: resolves outside vault."

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

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
