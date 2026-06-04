from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))


def _state_dir() -> str:
    return os.environ.get('STATE_DIR', os.path.join(_REPO_ROOT, 'state'))


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


def _success_rate(status: str) -> float:
    return {'completed': 1.0, 'done': 1.0, 'failed': 0.0, 'error': 0.0}.get(status.lower(), 0.5)


class TaskHistoryEngine:
    name = 'tasks'
    source_type = 'task_log'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('TaskHistoryEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        results: list[NormalizedSearchResult] = []
        sd = _state_dir()

        # tasks.json
        tasks_path = os.path.join(sd, 'tasks.json')
        if os.path.exists(tasks_path):
            try:
                with open(tasks_path) as f:
                    data = json.load(f)
                task_list = data.get('tasks', data) if isinstance(data, dict) else data
                if isinstance(task_list, dict):
                    task_list = list(task_list.values())
                for task in task_list:
                    if not isinstance(task, dict):
                        continue
                    if request.tenant_id and task.get('tenant_id', '') not in ('', request.tenant_id):
                        continue
                    goal = task.get('goal', task.get('name', task.get('id', '')))
                    output = str(task.get('output', task.get('result', '')))
                    combined = f"{goal} {output}"
                    score = _keyword_score(tokens, combined)
                    if score == 0.0:
                        continue
                    uid = hashlib.md5(f"task:{task.get('id', goal)}".encode()).hexdigest()[:12]
                    status = task.get('status', '')
                    results.append(NormalizedSearchResult(
                        id=uid, title=str(goal), content=(goal + ' ' + output)[:500],
                        url='state/tasks.json',
                        source_type='task_log', engine=self.name, score=score,
                        past_success_rate=_success_rate(status),
                        metadata={'status': status, 'task_id': task.get('id', '')},
                        tenant_id=task.get('tenant_id', ''),
                    ))
            except Exception as exc:
                log.debug('tasks.json read error: %s', exc)

        # bus.jsonl task events (last 100 lines)
        bus_path = os.path.join(sd, 'bus.jsonl')
        if os.path.exists(bus_path):
            try:
                with open(bus_path) as f:
                    lines = f.readlines()
                for line in lines[-100:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    ch = ev.get('channel', '')
                    if ch not in ('tasks', 'results'):
                        continue
                    msg = ev.get('message', {})
                    content = json.dumps(msg)[:500]
                    score = _keyword_score(tokens, content)
                    if score == 0.0:
                        continue
                    ts = ev.get('timestamp', '')
                    uid = hashlib.md5(f"bus-task:{ts}:{content[:30]}".encode()).hexdigest()[:12]
                    results.append(NormalizedSearchResult(
                        id=uid, title=f'[{ch}] {msg.get("event", "task")}',
                        content=content, url='state/bus.jsonl',
                        source_type='task_log', engine=self.name, score=score,
                        metadata={'timestamp': ts, 'channel': ch},
                    ))
            except Exception as exc:
                log.debug('bus.jsonl task scan error: %s', exc)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]
