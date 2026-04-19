"""replay_buffer.py — Prioritized Experience Replay (PER) buffer.

Implements a sum-tree based PER buffer as described in:
    Schaul et al. (2015) "Prioritized Experience Replay".

Falls back gracefully to uniform sampling when all priorities are equal.

Thread-safe: all public methods acquire an internal lock.
"""
from __future__ import annotations

import random
import threading
from typing import List, NamedTuple, Tuple

import torch


# ── Data types ────────────────────────────────────────────────────────────────

class Experience(NamedTuple):
    state:      torch.Tensor  # (input_size,)
    action:     int
    reward:     float
    next_state: torch.Tensor  # (input_size,)


Batch = Tuple[
    torch.Tensor,  # states     (B, input_size)
    torch.Tensor,  # actions    (B,)  long
    torch.Tensor,  # rewards    (B,)  float
    torch.Tensor,  # next_states (B, input_size)
    List[int],     # indices — for priority updates
    torch.Tensor,  # importance-sampling weights (B,)
]


# ── Sum-tree ──────────────────────────────────────────────────────────────────

class _SumTree:
    """Binary sum-tree for O(log n) priority sampling and update."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._tree = [0.0] * (2 * capacity)
        self._data: list[Experience | None] = [None] * capacity
        self._write_idx = 0
        self._size = 0

    def _propagate(self, idx: int, delta: float) -> None:
        parent = idx // 2
        while parent >= 1:
            self._tree[parent] += delta
            parent //= 2

    def update(self, idx: int, priority: float) -> None:
        tree_idx = idx + self.capacity
        delta = priority - self._tree[tree_idx]
        self._tree[tree_idx] = priority
        self._propagate(tree_idx, delta)

    def add(self, priority: float, data: Experience) -> None:
        idx = self._write_idx
        self._data[idx] = data
        self.update(idx, priority)
        self._write_idx = (self._write_idx + 1) % self.capacity
        self._size = min(self._size + 1, self.capacity)

    def get(self, cumsum: float) -> Tuple[int, float, Experience]:
        """Return (data_index, priority, experience) for cumulative sum *cumsum*."""
        idx = 1
        while idx < self.capacity:
            left = 2 * idx
            if left >= len(self._tree):
                break
            if cumsum <= self._tree[left]:
                idx = left
            else:
                cumsum -= self._tree[left]
                idx = left + 1
        data_idx = idx - self.capacity
        data_idx = max(0, min(data_idx, self._size - 1))
        exp = self._data[data_idx]
        if exp is None:
            # Fallback: return first valid experience
            for i in range(self._size):
                if self._data[i] is not None:
                    exp = self._data[i]
                    data_idx = i
                    break
        return data_idx, self._tree[idx], exp  # type: ignore[return-value]

    @property
    def total(self) -> float:
        return self._tree[1]

    def __len__(self) -> int:
        return self._size


# ═════════════════════════════════════════════════════════════════════════════
class PrioritizedReplayBuffer:
    """Prioritized Experience Replay buffer.

    Args:
        capacity: Maximum number of experiences to store.
        alpha:    Priority exponent (0 = uniform, 1 = full prioritisation).
        beta:     IS-weight exponent (0 = no correction, 1 = full correction).
        beta_increment: Beta is annealed toward 1.0 by this amount each sample.
        epsilon:  Small constant added to priorities to prevent zero probability.
    """

    def __init__(
        self,
        capacity: int,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 0.001,
        epsilon: float = 1e-5,
    ) -> None:
        self._tree = _SumTree(capacity)
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.epsilon = epsilon
        self._max_priority = 1.0
        self._lock = threading.Lock()

    # ── public interface ──────────────────────────────────────────────────────

    def push(
        self,
        state: torch.Tensor,
        action: int,
        reward: float,
        next_state: torch.Tensor,
    ) -> None:
        """Store one experience with maximum current priority."""
        exp = Experience(
            state=state.detach().cpu().float(),
            action=action,
            reward=float(reward),
            next_state=next_state.detach().cpu().float(),
        )
        with self._lock:
            self._tree.add(self._max_priority ** self.alpha, exp)

    def sample(self, batch_size: int) -> Batch:
        """Sample *batch_size* experiences proportional to priority.

        Raises:
            ValueError: if the buffer has fewer entries than *batch_size*.
        """
        with self._lock:
            n = len(self._tree)
            if n < batch_size:
                raise ValueError(f"Buffer has {n} experiences, need {batch_size}.")

            self.beta = min(1.0, self.beta + self.beta_increment)

            segment = self._tree.total / batch_size
            indices: List[int] = []
            priorities: List[float] = []
            exps: List[Experience] = []

            for i in range(batch_size):
                lo, hi = segment * i, segment * (i + 1)
                cumsum = random.uniform(lo, hi)
                idx, priority, exp = self._tree.get(cumsum)
                indices.append(idx)
                priorities.append(priority)
                exps.append(exp)

            # Importance-sampling weights
            total = self._tree.total
            min_prob = min(p / total for p in priorities) if total > 0 else 1.0
            weights = torch.tensor(
                [((p / total) / min_prob) ** (-self.beta) if total > 0 else 1.0
                 for p in priorities],
                dtype=torch.float32,
            )
            weights /= weights.max()  # normalise to [0, 1]

        states      = torch.stack([e.state      for e in exps])
        actions     = torch.tensor([e.action    for e in exps], dtype=torch.long)
        rewards     = torch.tensor([e.reward    for e in exps], dtype=torch.float32)
        next_states = torch.stack([e.next_state for e in exps])

        return states, actions, rewards, next_states, indices, weights

    def update_priorities(self, indices: List[int], td_errors: torch.Tensor) -> None:
        """Update priorities for a previously sampled batch."""
        with self._lock:
            for idx, err in zip(indices, td_errors.tolist()):
                priority = (abs(err) + self.epsilon) ** self.alpha
                self._max_priority = max(self._max_priority, priority)
                self._tree.update(idx, priority)

    def clear(self) -> None:
        """Remove all stored experiences."""
        with self._lock:
            self._tree = _SumTree(self._tree.capacity)
            self._max_priority = 1.0

    def __len__(self) -> int:
        with self._lock:
            return len(self._tree)

    @property
    def capacity(self) -> int:
        return self._tree.capacity
