"""Learning orchestrator — runs wizard-driven or chat-triggered research sessions."""
import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

LEGACY_SESSIONS_PATH = Path('/home/lf/AI-EMPLOYEE/state/learning_sessions.json')

DEPTH_CONFIG = {
    'shallow':    {'max_hops': 1, 'max_pages': 3,  'sources_per_hop': 3},
    'normal':     {'max_hops': 2, 'max_pages': 6,  'sources_per_hop': 6},
    'deep':       {'max_hops': 3, 'max_pages': 10, 'sources_per_hop': 10},
    'continuous': {'max_hops': 2, 'max_pages': 6,  'sources_per_hop': 6},
}


def _current_tenant_id() -> str:
    try:
        from core.tenancy import _current_tenant
        ctx = _current_tenant.get()
        if ctx and ctx.tenant_id:
            return ctx.tenant_id
    except Exception:
        pass
    return "default"


def _sessions_path() -> Path:
    import os
    tid = _current_tenant_id()
    p = Path(os.path.expanduser(f"~/.ai-employee/tenants/{tid}/state/learning_sessions.json"))
    if tid == "default" and LEGACY_SESSIONS_PATH.exists() and not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(LEGACY_SESSIONS_PATH), str(p))
    return p


# Backward-compat
SESSIONS_PATH = _sessions_path()


def _read_sessions() -> dict:
    p = _sessions_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {'sessions': []}


def _write_sessions(data: dict):
    p = _sessions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def _store_session(session: dict):
    data = _read_sessions()
    # Upsert by id
    sessions = data.get('sessions', [])
    sessions = [s for s in sessions if s.get('id') != session.get('id')]
    sessions.insert(0, session)
    data['sessions'] = sessions[:50]
    _write_sessions(data)


def get_session(session_id: str) -> Optional[Dict]:
    for s in _read_sessions().get('sessions', []):
        if s.get('id') == session_id:
            return s
    return None


def list_sessions(limit: int = 20) -> List[Dict]:
    return _read_sessions().get('sessions', [])[:limit]


def _broadcast(event: str, payload: dict):
    """Broadcast a WS event via the existing event bus."""
    try:
        from core.bus import get_bus
        get_bus().publish('ws_broadcast', {'event': event, 'data': payload})
        return
    except Exception:
        pass
    try:
        from core.observability.event_stream import get_event_stream
        get_event_stream().emit(event, payload)
    except Exception as e:
        log.debug(f"broadcast {event} fell through: {e}")


async def execute_learning(
    topic: str,
    scope: str = '',
    depth: str = 'normal',
    selected_urls: Optional[List[str]] = None,
    verification_level: str = 'normal',
    schedule_recurring: bool = False,
) -> Dict:
    """Kick off a learning session asynchronously."""
    from memory.topic_intelligence import ensure_topic, pin_topic

    session_id = uuid.uuid4().hex[:12]
    cfg = DEPTH_CONFIG.get(depth, DEPTH_CONFIG['normal'])

    topic_rec = ensure_topic(topic, scope=scope)
    if schedule_recurring:
        pin_topic(topic_rec['id'], pinned=True, schedule='every_6h')

    initial = {
        'id': session_id,
        'topic': topic,
        'topic_id': topic_rec['id'],
        'depth': depth,
        'verification_level': verification_level,
        'status': 'running',
        'started_at': time.time(),
        'progress': 0.0,
        'log': [],
        'result': None,
    }
    _store_session(initial)

    _broadcast('learning:started', {
        'session_id': session_id,
        'topic': topic,
        'topic_id': topic_rec['id'],
        'depth': depth,
        'started_at': time.time(),
    })

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_run_session(session_id, topic, topic_rec['id'], cfg, selected_urls, verification_level))
    except RuntimeError:
        # No running loop (sync caller) — run in thread
        import threading
        threading.Thread(
            target=lambda: asyncio.run(_run_session(session_id, topic, topic_rec['id'], cfg, selected_urls, verification_level)),
            daemon=True,
        ).start()

    return {
        'session_id': session_id,
        'topic': topic,
        'topic_id': topic_rec['id'],
        'depth': depth,
        'status': 'started',
        'started_at': initial['started_at'],
    }


async def _run_session(session_id: str, topic: str, topic_id: str, cfg: Dict,
                       selected_urls: Optional[List[str]], verification_level: str):
    if selected_urls:
        from core.url_guard import validate_url as _gu  # type: ignore
        selected_urls = [u for u in selected_urls if not _gu(u)]
    new_memories = 0
    sources_used = 0
    confidences: List[float] = []
    error: Optional[str] = None

    try:
        try:
            from core.auto_research_agent import get_auto_researcher
            researcher = get_auto_researcher()

            if selected_urls and hasattr(researcher, 'research_selected'):
                result = await researcher.research_selected(topic, selected_urls, depth='normal')
            else:
                # Most AutoResearchAgent implementations have research(goal=..., max_hops=...)
                if hasattr(researcher, 'research'):
                    try:
                        result = await researcher.research(
                            gaps=[topic], goal=topic,
                            max_hops=cfg['max_hops'], max_pages=cfg['max_pages'],
                        )
                    except TypeError:
                        # signature variant
                        try:
                            result = await researcher.research(topic, max_hops=cfg['max_hops'])
                        except Exception as e2:
                            log.warning(f"researcher.research signature mismatch: {e2}")
                            result = {}
                else:
                    result = {}

            if isinstance(result, dict):
                new_memories = int(result.get('memories_added') or result.get('findings_count') or 0)
                sources_used = int(result.get('sources_consulted') or len(result.get('urls_visited') or []))
                if 'avg_confidence' in result:
                    confidences.append(float(result['avg_confidence']))
        except Exception as e:
            log.warning(f"AutoResearchAgent unavailable: {e}")
            error = f"researcher_unavailable: {e}"

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.65

        from memory.topic_intelligence import add_memories_to_topic, get_topic
        updated = add_memories_to_topic(topic_id, new_memories, sources_used, avg_conf)
        skill = (updated or {}).get('skill_level', 0)

        session = get_session(session_id) or {'id': session_id}
        session.update({
            'status': 'completed' if not error else 'partial',
            'completed_at': time.time(),
            'progress': 1.0,
            'result': {
                'new_memories': new_memories,
                'sources_consulted': sources_used,
                'avg_confidence': avg_conf,
                'skill_level_after': skill,
                'error': error,
            },
        })
        _store_session(session)

        _broadcast('learning:completed', {
            'session_id': session_id,
            'topic_id': topic_id,
            'result': session['result'],
        })
        _broadcast('topic:skill_updated', {
            'topic_id': topic_id,
            'new_skill_level': skill,
        })
    except Exception as e:
        log.error(f"Learning session {session_id} crashed: {e}")
        session = get_session(session_id) or {'id': session_id}
        session.update({'status': 'failed', 'error': str(e), 'completed_at': time.time()})
        _store_session(session)
        _broadcast('learning:failed', {'session_id': session_id, 'error': str(e)})
