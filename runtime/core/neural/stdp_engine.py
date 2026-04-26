"""STDP (Spike-Timing-Dependent Plasticity) synaptic learning engine.

Weights are stored in a square matrix of shape (N_NEURONS, N_NEURONS).
Persisted to ~/.ai-employee/state/stdp_weights.npy (numpy binary, fast load).
"""
import hashlib, json, os, time, threading
from pathlib import Path

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

N_NEURONS = 128          # fixed vocabulary size
TAU_PLUS  = 20.0         # LTP time constant (ms)
TAU_MINUS = 20.0         # LTD time constant
A_PLUS    = 0.005        # LTP amplitude
A_MINUS   = 0.005        # LTD amplitude
W_MAX     = 1.0
W_MIN     = 0.0

def _state_path() -> Path:
    base = Path(os.getenv('AI_HOME', Path(__file__).parents[3]))
    return base / 'state' / 'stdp_weights.npy'

class STDPEngine:
    def __init__(self):
        self._lock = threading.RLock()
        if HAS_NUMPY:
            p = _state_path()
            if p.exists():
                self._W = np.load(str(p))
            else:
                self._W = np.full((N_NEURONS, N_NEURONS), 0.1)
                np.fill_diagonal(self._W, 0.0)
        else:
            # Fallback: use dict instead of numpy array
            self._W = {}
        self._spike_times: dict[int, float] = {}

    def neuron_for(self, text: str) -> int:
        """Hash any string to a neuron index 0..N_NEURONS-1."""
        return int(hashlib.md5(text.encode()).hexdigest(), 16) % N_NEURONS

    def fire(self, neuron_id: int) -> None:
        """Record a spike for neuron_id at current time."""
        with self._lock:
            self._spike_times[neuron_id] = time.monotonic() * 1000  # ms

    def learn_pair(self, pre_text: str, post_text: str, success: bool) -> float:
        """Apply STDP rule between pre and post neurons.

        Returns the weight delta applied.
        """
        pre  = self.neuron_for(pre_text)
        post = self.neuron_for(post_text)
        with self._lock:
            t_pre  = self._spike_times.get(pre,  0.0)
            t_post = self._spike_times.get(post, 0.0)
            delta_t = t_post - t_pre  # positive = causal (pre before post)

            if HAS_NUMPY:
                if delta_t >= 0:
                    dw = A_PLUS * np.exp(-delta_t / TAU_PLUS) * (1 if success else -0.5)
                else:
                    dw = -A_MINUS * np.exp(delta_t / TAU_MINUS) * (1 if success else 0.5)
                self._W[pre][post] = np.clip(self._W[pre][post] + dw, W_MIN, W_MAX)
                return float(dw)
            else:
                # Fallback: use dict
                key = (pre, post)
                old_w = self._W.get(key, 0.1)
                if delta_t >= 0:
                    dw = A_PLUS * (1.0 if success else -0.5)
                else:
                    dw = -A_MINUS * (1.0 if success else 0.5)
                new_w = max(W_MIN, min(W_MAX, old_w + dw))
                self._W[key] = new_w
                return dw

    def association_strength(self, a_text: str, b_text: str) -> float:
        """Get the weight between two text-encoded neurons."""
        a = self.neuron_for(a_text)
        b = self.neuron_for(b_text)
        with self._lock:
            if HAS_NUMPY:
                return float(self._W[a][b])
            else:
                return float(self._W.get((a, b), 0.0))

    def save(self) -> None:
        """Save weights to disk."""
        with self._lock:
            if HAS_NUMPY:
                np.save(str(_state_path()), self._W)

    def top_associations(self, text: str, n: int = 5) -> list[dict]:
        """Return top n neurons associated with text."""
        nid = self.neuron_for(text)
        with self._lock:
            if HAS_NUMPY:
                row = self._W[nid].copy()
                idxs = np.argsort(row)[::-1][:n]
                return [{'neuron': int(i), 'weight': float(row[i])} for i in idxs]
            else:
                # Fallback: return empty list
                return []

_ENGINE: STDPEngine | None = None
_ENG_LOCK = threading.Lock()

def get_stdp_engine() -> STDPEngine:
    """Get or create the process-wide STDP engine."""
    global _ENGINE
    with _ENG_LOCK:
        if _ENGINE is None:
            _ENGINE = STDPEngine()
    return _ENGINE
