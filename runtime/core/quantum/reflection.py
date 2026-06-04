"""Universal feedback loop — all subsystem outcomes flow through here."""
from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from core.quantum.candidate import Candidate

log = logging.getLogger(__name__)

FEEDBACK_FILE = 'state/quantum_feedback.jsonl'
_CACHE: dict[str, tuple[float, float]] = {}   # id → (timestamp, rate)
_CACHE_TTL = 60.0


class ReflectionEngine:
    def __init__(self, state_dir: str | None = None):
        self._dir = Path(state_dir or os.environ.get('STATE_DIR', 'state'))
        self._file = self._dir / 'quantum_feedback.jsonl'

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def reflect(
        self,
        task_id: str,
        outcome: str,
        context_pack=None,
        scope: str = 'task',
        step_action: str = '',
        tool_id: str = '',
        agent_id: str = '',
        extra: dict | None = None,
    ) -> None:
        try:
            self._ensure_dir()
            top = []
            confidence = 0.0
            search_id = ''
            if context_pack is not None:
                search_id = getattr(context_pack, 'search_id', '')
                confidence = getattr(context_pack, 'confidence', 0.0)
                candidates = getattr(context_pack, 'candidates', [])
                top = [c.result.id for c in candidates[:5] if isinstance(c, Candidate)]

                # Update in-memory candidate rates
                for c in candidates:
                    if isinstance(c, Candidate):
                        old = c.result.past_success_rate
                        if outcome == 'success':
                            c.result.past_success_rate = old * 0.9 + 0.1
                        elif outcome == 'failure':
                            c.result.past_success_rate = old * 0.9

            record = {
                'ts':            datetime.now(tz=timezone.utc).isoformat(),
                'task_id':       task_id,
                'scope':         scope,
                'outcome':       outcome,
                'agent_id':      agent_id,
                'tool_id':       tool_id,
                'step_action':   step_action,
                'search_id':     search_id,
                'confidence':    confidence,
                'top_candidates': top,
                'extra':         extra or {},
            }

            with self._file.open('a') as fh:
                fh.write(json.dumps(record) + '\n')

            try:
                from core.agent_learning_profile import AgentLearningProfile  # type: ignore
                if agent_id:
                    AgentLearningProfile.record_outcome(agent_id, outcome)
            except Exception:
                pass

        except Exception as exc:
            log.error('ReflectionEngine.reflect failed: %s', exc)

    def _read_rates(self, key_field: str, key_val: str) -> float:
        cache_key = f'{key_field}:{key_val}'
        now = time.time()
        if cache_key in _CACHE:
            ts, rate = _CACHE[cache_key]
            if now - ts < _CACHE_TTL:
                return rate

        if not self._file.exists():
            return 0.5

        total = success = 0
        try:
            with self._file.open() as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get(key_field) == key_val:
                        total += 1
                        if rec.get('outcome') == 'success':
                            success += 1
        except Exception:
            return 0.5

        rate = (success / total) if total else 0.5
        _CACHE[cache_key] = (now, rate)
        return rate

    def get_agent_success_rate(self, agent_id: str) -> float:
        return self._read_rates('agent_id', agent_id)

    def get_tool_success_rate(self, tool_id: str) -> float:
        return self._read_rates('tool_id', tool_id)
