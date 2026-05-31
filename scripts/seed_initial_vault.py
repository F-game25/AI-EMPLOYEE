#!/usr/bin/env python3
"""Seed the Obsidian-compatible vault from state/knowledge_store.json.

Idempotent: pre-existing notes (matched by id) are skipped. Creates one
note per unique topic plus a "Knowledge Index" hub note that wikilinks to
every topic, so backlink resolution can be smoke-tested end to end.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/lf/AI-EMPLOYEE/runtime")

from memory.vault import Vault
from memory.wikilink_resolver import title_to_id

KSTORE = Path("/home/lf/AI-EMPLOYEE/state/knowledge_store.json")


def main() -> int:
    vault = Vault()
    print(f"Vault root: {vault.export_path()}")

    if not KSTORE.exists():
        print(f"knowledge_store missing at {KSTORE}; nothing to seed")
        return 1

    store = json.loads(KSTORE.read_text(encoding="utf-8"))
    entries = store.get("entries", [])
    seen_topics: dict[str, str] = {}  # topic -> title

    existing_ids = {ref.id for ref in vault.list_notes()}

    for entry in entries:
        topic = (entry.get("topic") or "general").strip().lower()
        if topic in seen_topics:
            continue
        title = topic.replace("-", " ").replace("_", " ").title()
        seen_topics[topic] = title
        nid = title_to_id(title)
        if nid in existing_ids:
            print(f"  = {title} (already present)")
            continue
        body = (
            f"# {title}\n\n"
            f"{entry.get('content', '')}\n\n"
            f"## Sources\n- {entry.get('source', 'unknown')}\n\n"
            f"## Related\nLinked from: [[Knowledge Index]]\n"
        )
        vault.create_note(
            title,
            folder="topics",
            body=body,
            frontmatter={
                "importance": entry.get("importance", 0.5),
                "sources": [entry.get("source", "")] if entry.get("source") else [],
                "confidence": 0.7,
                "verified_by": "ai",
                "tags": [topic],
            },
        )
        print(f"  + {title}")

    # hub note linking everything together
    if "knowledge-index" not in existing_ids:
        index_body = "# Knowledge Index\n\nAll topics in the vault:\n\n"
        for title in seen_topics.values():
            index_body += f"- [[{title}]]\n"
        vault.create_note(
            "Knowledge Index",
            folder="concepts",
            body=index_body,
            frontmatter={"importance": 1.0, "verified_by": "ai"},
        )
        print("  + Knowledge Index")

    result = vault.rebuild_indices()
    print(
        f"\nIndices rebuilt: {result.get('note_count', 0)} notes, "
        f"{result.get('backlink_count', 0)} backlinks, "
        f"{result.get('broken_link_count', 0)} broken links"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
