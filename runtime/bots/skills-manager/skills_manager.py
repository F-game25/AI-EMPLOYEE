"""Skills Manager — 100+ Skills Library & Custom Agent Builder.

Provides a 111-skill library organised across 11 categories.
Custom agents can be built from any combination of skills and are stored in
~/.ai-employee/config/custom_agents.json.

The manager polls the chat log for commands from the UI or WhatsApp and
processes them in real-time.

WhatsApp / Chat commands
─────────────────────────
  skills                       — show library summary (count + categories)
  skills list [<category>]     — list skills (optionally filtered by category)
  skills search <query>        — search skills by name/description/tag
  skills categories            — list all categories
  agents                       — list all custom agents
  agent <name>                 — show a specific agent's skills
  create agent <name> with <skill1>, <skill2>, ...
                               — create a new custom agent with skills
  add skill <skill-id> to <agent-name>
                               — add a skill to an existing agent
  remove skill <skill-id> from <agent-name>
                               — remove a skill from an agent
  delete agent <name>          — delete a custom agent

State files
────────────
  ~/.ai-employee/state/skills-manager.state.json  — current state
  ~/.ai-employee/config/custom_agents.json        — custom agent definitions
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "skills-manager.state.json"
CUSTOM_AGENTS_FILE = AI_HOME / "config" / "custom_agents.json"
SKILLS_LIBRARY_FILE = AI_HOME / "config" / "skills_library.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"

POLL_INTERVAL = int(os.environ.get("SKILLS_MANAGER_POLL_INTERVAL", "5"))
MAX_SKILLS_PER_AGENT = int(os.environ.get("SKILLS_MANAGER_MAX_SKILLS", "20"))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    entries = []
    try:
        for line in CHATLOG.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except Exception:
        pass
    return entries


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Skills Library ─────────────────────────────────────────────────────────────

def load_skills_library() -> dict:
    """Load the skills library from file; returns empty structure on error."""
    if not SKILLS_LIBRARY_FILE.exists():
        return {"skills": [], "categories": []}
    try:
        return json.loads(SKILLS_LIBRARY_FILE.read_text())
    except Exception:
        return {"skills": [], "categories": []}


def get_skill_by_id(library: dict, skill_id: str) -> dict | None:
    for s in library.get("skills", []):
        if s["id"] == skill_id:
            return s
    return None


def search_skills(library: dict, query: str) -> list:
    q = query.lower()
    return [
        s for s in library.get("skills", [])
        if (q in s["id"].lower()
            or q in s["name"].lower()
            or q in s["description"].lower()
            or any(q in t.lower() for t in s.get("tags", []))
            or q in s["category"].lower())
    ]


def skills_by_category(library: dict, category: str) -> list:
    cat_lower = category.lower()
    return [
        s for s in library.get("skills", [])
        if cat_lower in s["category"].lower()
    ]


# ── Custom Agents ──────────────────────────────────────────────────────────────

def load_custom_agents() -> dict:
    if not CUSTOM_AGENTS_FILE.exists():
        return {}
    try:
        return json.loads(CUSTOM_AGENTS_FILE.read_text())
    except Exception:
        return {}


def save_custom_agents(agents: dict) -> None:
    CUSTOM_AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_AGENTS_FILE.write_text(json.dumps(agents, indent=2))


def build_system_prompt(agent_name: str, skill_ids: list, library: dict) -> str:
    """Build a system prompt for an agent from its assigned skills."""
    lines = [
        f"You are {agent_name}, a specialised AI assistant with the following expertise:",
        "",
    ]
    for sid in skill_ids:
        skill = get_skill_by_id(library, sid)
        if skill:
            lines.append(f"- **{skill['name']}** ({skill['category']}): {skill['description']}")
        else:
            lines.append(f"- {sid}")
    lines += [
        "",
        "Apply your full expertise when responding. Be precise, actionable, and thorough.",
    ]
    return "\n".join(lines)


def _normalise_name(name: str) -> str:
    """Normalise agent name to a filesystem-safe identifier."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower().strip()).strip("-")


def create_or_update_agent(
    agents: dict,
    library: dict,
    raw_name: str,
    skill_ids: list,
    description: str = "",
) -> tuple[dict, list]:
    """Create or update a custom agent. Returns (agent_dict, list_of_unknown_skill_ids)."""
    agent_id = _normalise_name(raw_name)
    unknown = [sid for sid in skill_ids if get_skill_by_id(library, sid) is None]
    valid_ids = [sid for sid in skill_ids if sid not in unknown]
    valid_ids = valid_ids[:MAX_SKILLS_PER_AGENT]

    now = now_iso()
    existing = agents.get(agent_id, {})
    agent = {
        "id": agent_id,
        "name": raw_name,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
        "description": description or existing.get("description", ""),
        "skills": valid_ids,
        "system_prompt": build_system_prompt(raw_name, valid_ids, library),
    }
    agents[agent_id] = agent
    return agent, unknown


# ── Command Processing ─────────────────────────────────────────────────────────

def handle_skills_command(message: str, library: dict, agents: dict) -> str | None:
    """Process a skills-related command. Returns a response string or None if not handled."""
    msg = message.strip()
    msg_lower = msg.lower()

    # ── skills (summary) ──────────────────────────────────────────────────────
    if msg_lower == "skills":
        cats = {}
        for s in library.get("skills", []):
            cats[s["category"]] = cats.get(s["category"], 0) + 1
        total = sum(cats.values())
        lines = [f"📚 *Skills Library* — {total} skills in {len(cats)} categories:"]
        for cat, count in sorted(cats.items()):
            lines.append(f"  • {cat}: {count}")
        lines.append("\nCommands: *skills list [category]*, *skills search <query>*, *create agent <name> with <skill1>, <skill2>*")
        return "\n".join(lines)

    # ── skills categories ─────────────────────────────────────────────────────
    if msg_lower in ("skills categories", "skill categories"):
        cats = sorted({s["category"] for s in library.get("skills", [])})
        return "📂 *Skill Categories:*\n" + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(cats))

    # ── skills list [<category>] ──────────────────────────────────────────────
    m = re.match(r"skills list\s*(.*)$", msg_lower)
    if m:
        cat_filter = m.group(1).strip()
        skills = skills_by_category(library, cat_filter) if cat_filter else library.get("skills", [])
        if not skills:
            return f"No skills found for category '{cat_filter}'."
        lines = [f"📋 *Skills{' — ' + cat_filter.title() if cat_filter else ''}* ({len(skills)} total):"]
        for s in skills[:30]:
            lines.append(f"  `{s['id']}` — {s['name']} ({s['category']})")
        if len(skills) > 30:
            lines.append(f"  … and {len(skills) - 30} more. Use *skills search <query>* to narrow down.")
        return "\n".join(lines)

    # ── skills search <query> ─────────────────────────────────────────────────
    m = re.match(r"skills search\s+(.+)$", msg_lower)
    if m:
        query = m.group(1).strip()
        results = search_skills(library, query)
        if not results:
            return f"No skills found matching '{query}'."
        lines = [f"🔍 *Skills matching '{query}'* ({len(results)} found):"]
        for s in results[:15]:
            lines.append(f"  `{s['id']}` — {s['name']} ({s['category']})")
            lines.append(f"    {s['description'][:80]}...")
        if len(results) > 15:
            lines.append(f"  … and {len(results) - 15} more.")
        return "\n".join(lines)

    # ── agents ────────────────────────────────────────────────────────────────
    if msg_lower in ("agents", "agents list", "custom agents"):
        if not agents:
            return "No custom agents yet.\nCreate one: *create agent <name> with <skill1>, <skill2>*"
        lines = [f"🤖 *Custom Agents* ({len(agents)}):"]
        for a in agents.values():
            skill_count = len(a.get("skills", []))
            lines.append(f"  • *{a['name']}* — {skill_count} skills")
        lines.append("\nUse *agent <name>* to see details.")
        return "\n".join(lines)

    # ── agent <name> ──────────────────────────────────────────────────────────
    m = re.match(r"agent\s+(.+)$", msg_lower)
    if m and not msg_lower.startswith(("agents", "create agent", "delete agent")):
        name = m.group(1).strip()
        agent_id = _normalise_name(name)
        agent = agents.get(agent_id)
        if not agent:
            return f"Agent '{name}' not found. Use *agents* to list all agents."
        skill_ids = agent.get("skills", [])
        skill_list = []
        for sid in skill_ids:
            skill = get_skill_by_id(library, sid)
            skill_list.append(f"  • `{sid}` — {skill['name']}" if skill else f"  • `{sid}`")
        lines = [
            f"🤖 *Agent: {agent['name']}*",
            f"Created: {agent.get('created_at', '?')} | Updated: {agent.get('updated_at', '?')}",
            f"Skills ({len(skill_ids)}):",
        ] + skill_list
        return "\n".join(lines)

    # ── create agent <name> with <s1>, <s2>, ... ─────────────────────────────
    m = re.match(r"create agent\s+(.+?)\s+with\s+(.+)$", msg_lower)
    if m:
        raw_name = msg[m.start(1):m.start(1) + len(m.group(1))]  # preserve original case
        raw_skills = m.group(2).strip()
        skill_ids = [s.strip() for s in re.split(r"[,\s]+", raw_skills) if s.strip()]
        agent, unknown = create_or_update_agent(agents, library, raw_name, skill_ids)
        save_custom_agents(agents)
        lines = [
            f"✅ Agent *{agent['name']}* created with {len(agent['skills'])} skills:",
        ] + [f"  • `{sid}`" for sid in agent["skills"]]
        if unknown:
            lines.append(f"\n⚠️ Unknown skill IDs (ignored): {', '.join(unknown)}")
            lines.append("Use *skills search <query>* to find valid skill IDs.")
        return "\n".join(lines)

    # ── add skill <skill-id> to <agent-name> ──────────────────────────────────
    m = re.match(r"add skill\s+(\S+)\s+to\s+(.+)$", msg_lower)
    if m:
        skill_id = m.group(1).strip()
        agent_name = m.group(2).strip()
        agent_id = _normalise_name(agent_name)
        if agent_id not in agents:
            return f"Agent '{agent_name}' not found. Use *agents* to list agents."
        if get_skill_by_id(library, skill_id) is None:
            return f"Skill `{skill_id}` not found. Use *skills search <query>* to find valid IDs."
        current = agents[agent_id].get("skills", [])
        if skill_id in current:
            return f"Skill `{skill_id}` is already assigned to *{agents[agent_id]['name']}*."
        if len(current) >= MAX_SKILLS_PER_AGENT:
            return f"Agent already has the maximum of {MAX_SKILLS_PER_AGENT} skills."
        current.append(skill_id)
        agents[agent_id]["skills"] = current
        agents[agent_id]["updated_at"] = now_iso()
        agents[agent_id]["system_prompt"] = build_system_prompt(
            agents[agent_id]["name"], current, library
        )
        save_custom_agents(agents)
        skill = get_skill_by_id(library, skill_id)
        return f"✅ Added skill *{skill['name']}* to agent *{agents[agent_id]['name']}* ({len(current)} total skills)."

    # ── remove skill <skill-id> from <agent-name> ─────────────────────────────
    m = re.match(r"remove skill\s+(\S+)\s+from\s+(.+)$", msg_lower)
    if m:
        skill_id = m.group(1).strip()
        agent_name = m.group(2).strip()
        agent_id = _normalise_name(agent_name)
        if agent_id not in agents:
            return f"Agent '{agent_name}' not found."
        current = agents[agent_id].get("skills", [])
        if skill_id not in current:
            return f"Skill `{skill_id}` is not assigned to *{agents[agent_id]['name']}*."
        current.remove(skill_id)
        agents[agent_id]["skills"] = current
        agents[agent_id]["updated_at"] = now_iso()
        agents[agent_id]["system_prompt"] = build_system_prompt(
            agents[agent_id]["name"], current, library
        )
        save_custom_agents(agents)
        return f"✅ Removed skill `{skill_id}` from *{agents[agent_id]['name']}* ({len(current)} skills remaining)."

    # ── delete agent <name> ────────────────────────────────────────────────────
    m = re.match(r"delete agent\s+(.+)$", msg_lower)
    if m:
        agent_name = m.group(1).strip()
        agent_id = _normalise_name(agent_name)
        if agent_id not in agents:
            return f"Agent '{agent_name}' not found."
        deleted_name = agents[agent_id]["name"]
        del agents[agent_id]
        save_custom_agents(agents)
        return f"🗑 Agent *{deleted_name}* deleted."

    return None  # command not recognised as a skills command


# ── Main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] skills-manager started; poll_interval={POLL_INTERVAL}s")

    last_processed_idx = len(load_chatlog())

    while True:
        library = load_skills_library()
        agents = load_custom_agents()

        # Process new chatlog entries since last poll
        chatlog = load_chatlog()
        new_entries = chatlog[last_processed_idx:]
        last_processed_idx = len(chatlog)

        for entry in new_entries:
            if entry.get("type") != "user":
                continue
            message = entry.get("message", "").strip()
            if not message:
                continue
            response = handle_skills_command(message, library, agents)
            if response:
                append_chatlog({"ts": now_iso(), "type": "bot", "message": response})
                print(f"[{now_iso()}] skills-manager: handled command: {message[:60]!r}")

        # Update state
        skill_count = len(library.get("skills", []))
        agent_count = len(agents)
        categories = sorted({s["category"] for s in library.get("skills", [])})
        write_state({
            "bot": "skills-manager",
            "ts": now_iso(),
            "status": "running",
            "skills_total": skill_count,
            "categories": categories,
            "custom_agents": agent_count,
            "agents": [
                {"id": a["id"], "name": a["name"], "skill_count": len(a.get("skills", []))}
                for a in agents.values()
            ],
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
