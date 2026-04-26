"""Sliding-window pattern memory with cosine similarity matching.

Stores (input_embedding, label, outcome) tuples.
Persisted to ~/.ai-employee/state/pattern_memory.json.
"""
import json, os, threading
from pathlib import Path

try:
    from core.memory_index import embed_text, cosine_similarity
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False

MAX_PATTERNS = 2000

def _path() -> Path:
    base = Path(os.getenv('AI_HOME', Path(__file__).parents[3]))
    return base / 'state' / 'pattern_memory.json'

class PatternMemory:
    def __init__(self):
        self._lock = threading.RLock()
        self._patterns: list[dict] = self._load()

    def _load(self) -> list:
        """Load pattern memory from disk."""
        try:
            return json.loads(_path().read_text())
        except Exception:
            return []

    def store(self, text: str, label: str, outcome: float) -> None:
        """Store a pattern with its outcome."""
        if not HAS_EMBEDDINGS:
            # Fallback: store just text and label
            pattern = {'text': text[:200], 'label': label, 'outcome': outcome}
        else:
            try:
                emb = embed_text(text)
                pattern = {'emb': emb, 'label': label, 'outcome': outcome}
            except Exception:
                pattern = {'text': text[:200], 'label': label, 'outcome': outcome}

        with self._lock:
            self._patterns.append(pattern)
            if len(self._patterns) > MAX_PATTERNS:
                self._patterns = self._patterns[-MAX_PATTERNS:]
            _path().parent.mkdir(parents=True, exist_ok=True)
            _path().write_text(json.dumps(self._patterns))

    def recognize(self, text: str, threshold: float = 0.7) -> dict | None:
        """Find a similar pattern in memory."""
        if not HAS_EMBEDDINGS:
            # Fallback: simple text matching
            text_lower = text.lower()[:100]
            best_match = None
            for p in self._patterns[-500:]:
                if 'text' in p and text_lower in p['text'].lower():
                    best_match = p
                    break
            if best_match:
                return {'label': best_match['label'], 'similarity': 0.8, 'outcome': best_match['outcome']}
            return None

        try:
            emb = embed_text(text)
            best_sim, best = 0.0, None
            with self._lock:
                for p in self._patterns[-500:]:  # scan recent window
                    if 'emb' not in p:
                        continue
                    sim = cosine_similarity(emb, p['emb'])
                    if sim > best_sim:
                        best_sim, best = sim, p
            if best_sim >= threshold:
                return {'label': best['label'], 'similarity': best_sim, 'outcome': best['outcome']}
        except Exception:
            pass
        return None

_INST: PatternMemory | None = None
_PM_LOCK = threading.Lock()

def get_pattern_memory() -> PatternMemory:
    """Get or create the process-wide PatternMemory."""
    global _INST
    with _PM_LOCK:
        if _INST is None:
            _INST = PatternMemory()
    return _INST
