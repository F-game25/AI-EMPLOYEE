"""Topic intelligence — tracks per-topic skill level + standing topics.

Per-tenant namespacing (2026-05-18 security audit CRITICAL #2).
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

LEGACY_STORE = Path('/home/lf/AI-EMPLOYEE/state/topic_intelligence.json')


def _current_tenant_id() -> str:
    try:
        from core.tenancy import _current_tenant
        ctx = _current_tenant.get()
        if ctx and ctx.tenant_id:
            return ctx.tenant_id
    except Exception:
        pass
    return "default"


def _store_path() -> Path:
    tid = _current_tenant_id()
    p = Path(os.path.expanduser(f"~/.ai-employee/tenants/{tid}/state/topic_intelligence.json"))
    if tid == "default" and LEGACY_STORE.exists() and not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(LEGACY_STORE), str(p))
    return p


# Backward-compat alias
STORE = _store_path()


def _now() -> float:
    return time.time()


def _read() -> dict:
    p = _store_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {'topics': {}}


def _write(data: dict):
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def _kebab(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-') or 'untitled'


def list_topics(pinned_only: bool = False) -> List[Dict]:
    data = _read()
    topics = list(data.get('topics', {}).values())
    if pinned_only:
        topics = [t for t in topics if t.get('pinned')]
    topics.sort(key=lambda t: (-1 if t.get('pinned') else 0, -t.get('skill_level', 0)))
    return topics


def get_topic(topic_id: str) -> Optional[Dict]:
    return _read().get('topics', {}).get(topic_id)


def ensure_topic(label: str, scope: str = '', subtopics: Optional[List[str]] = None) -> Dict:
    """Get or create a topic record."""
    topic_id = _kebab(label)
    data = _read()
    if topic_id not in data.setdefault('topics', {}):
        data['topics'][topic_id] = {
            'id': topic_id,
            'label': label,
            'scope': scope,
            'subtopics': subtopics or [],
            'skill_level': 0.0,
            'memory_count': 0,
            'sources_consulted': 0,
            'last_studied': 0,
            'open_questions': [],
            'pinned': False,
            'schedule': 'manual',
            'created_at': _now(),
            'color': None,
        }
        _write(data)
    return data['topics'][topic_id]


def update_topic(topic_id: str, **kwargs) -> Optional[Dict]:
    data = _read()
    t = data.get('topics', {}).get(topic_id)
    if not t:
        return None
    for k, v in kwargs.items():
        t[k] = v
    _write(data)
    return t


def delete_topic(topic_id: str) -> bool:
    data = _read()
    if topic_id in data.get('topics', {}):
        del data['topics'][topic_id]
        _write(data)
        return True
    return False


def pin_topic(topic_id: str, pinned: bool = True, schedule: str = 'every_6h') -> Optional[Dict]:
    return update_topic(topic_id, pinned=pinned, schedule=schedule if pinned else 'manual')


def _compute_skill_level(topic: dict, recent_avg_confidence: float = 0.6) -> float:
    """Skill level 0–1 weighted blend."""
    mem = min(1.0, topic.get('memory_count', 0) / 50)
    conf = min(1.0, max(0.0, recent_avg_confidence))
    src = min(1.0, topic.get('sources_consulted', 0) / 20)
    days_since = (_now() - topic.get('last_studied', _now())) / 86400
    recency = max(0.0, 1.0 - (days_since / 90))
    open_q = len(topic.get('open_questions', []))
    answered = topic.get('memory_count', 0)
    qa_ratio = answered / (open_q + answered) if (open_q + answered) > 0 else 0.5
    score = 0.30 * mem + 0.30 * conf + 0.20 * src + 0.10 * recency + 0.10 * qa_ratio
    return round(min(1.0, max(0.0, score)), 3)


def add_memories_to_topic(topic_id: str, n_new_memories: int, n_sources: int, avg_confidence: float = 0.7):
    data = _read()
    t = data.setdefault('topics', {}).get(topic_id)
    if not t:
        return None
    t['memory_count'] = t.get('memory_count', 0) + n_new_memories
    t['sources_consulted'] = t.get('sources_consulted', 0) + n_sources
    t['last_studied'] = _now()
    t['skill_level'] = _compute_skill_level(t, recent_avg_confidence=avg_confidence)
    _write(data)
    return t


def add_open_question(topic_id: str, question: str):
    data = _read()
    t = data.get('topics', {}).get(topic_id)
    if t:
        if question not in t.setdefault('open_questions', []):
            t['open_questions'].append(question)
            _write(data)
