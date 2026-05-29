#!/usr/bin/env python3
"""One-shot migration: knowledge_store.json {topics: {...}} → {entries: [...]}"""
import json, time, uuid, shutil
from pathlib import Path

STORE = Path('/home/lf/AI-EMPLOYEE/state/knowledge_store.json')

def main():
    if not STORE.exists():
        print(f"No store at {STORE}, nothing to migrate")
        return

    backup = STORE.with_suffix('.json.bak')
    shutil.copy(STORE, backup)
    print(f"Backed up to {backup}")

    old = json.loads(STORE.read_text())
    if 'entries' in old and isinstance(old['entries'], list):
        print(f"Already migrated ({len(old['entries'])} entries) — skip")
        return

    entries = []
    topics = old.get('topics', {}) if isinstance(old.get('topics'), dict) else {}
    for topic, items in topics.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            content = item.get('content') or item.get('description') or item.get('summary') or item.get('text', '')
            if isinstance(content, (dict, list)):
                content = json.dumps(content)[:2000]
            entries.append({
                'id': item.get('id') or item.get('term') or uuid.uuid4().hex[:12],
                'topic': topic,
                'content': content,
                'source': item.get('source', 'migrated'),
                'url': item.get('url', ''),
                'importance': float(item.get('importance', 0.5)),
                'ts': float(item.get('ts', time.time())),
            })

    # Preserve insights array if present
    insights = old.get('insights', [])
    out = {'entries': entries, 'insights': insights, '_schema_version': 2, '_migrated_at': time.time()}
    STORE.write_text(json.dumps(out, indent=2))
    print(f"Migrated {len(entries)} entries → {STORE}")

if __name__ == '__main__':
    main()
