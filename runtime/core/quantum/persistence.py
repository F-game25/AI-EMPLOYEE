"""Amplitude weight store — persists learned weight adjustments."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_WEIGHTS_FILE = 'amplitude_weights.json'


class AmplitudePersistence:
    def __init__(self, state_dir: str | None = None):
        self._dir = Path(state_dir or os.environ.get('STATE_DIR', 'state'))
        self._file = self._dir / _WEIGHTS_FILE
        self._cache: dict[str, float] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self._file.exists():
            try:
                self._cache = json.loads(self._file.read_text())
            except Exception as exc:
                log.warning('AmplitudePersistence load failed: %s', exc)
                self._cache = {}

    def _save(self) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(self._cache, indent=2))
        except Exception as exc:
            log.error('AmplitudePersistence save failed: %s', exc)

    def load_success_rate(self, candidate_id: str) -> float:
        self._load()
        return self._cache.get(candidate_id, 0.5)

    def update(self, candidate_id: str, outcome: str) -> None:
        self._load()
        current = self._cache.get(candidate_id, 0.5)
        if outcome == 'success':
            self._cache[candidate_id] = current * 0.9 + 0.1
        else:
            self._cache[candidate_id] = current * 0.9
        self._save()

    def bulk_update(self, candidate_ids: list[str], outcome: str) -> None:
        self._load()
        for cid in candidate_ids:
            current = self._cache.get(cid, 0.5)
            if outcome == 'success':
                self._cache[cid] = current * 0.9 + 0.1
            else:
                self._cache[cid] = current * 0.9
        self._save()
