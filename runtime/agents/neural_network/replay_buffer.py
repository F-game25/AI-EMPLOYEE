"""replay_buffer.py — Thread-safe experience replay buffer.

Stores (state, action, reward, next_state) tuples and supports uniform
random sampling for online mini-batch updates.
"""
from __future__ import annotations

import random
import threading
from collections import deque
from typing import List, Tuple

import torch


Experience = Tuple[
    torch.Tensor,  # state
    int,           # action index
    float,         # reward
    torch.Tensor,  # next_state
]

Batch = Tuple[
    torch.Tensor,  # states   (B, input_size)
    torch.Tensor,  # actions  (B,)
    torch.Tensor,  # rewards  (B,)
    torch.Tensor,  # next_states (B, input_size)
]


class ReplayBuffer:
    """Fixed-capacity FIFO experience replay buffer.

    Args:
        capacity: Maximum number of (s, a, r, s') tuples to keep.
    """

    def __init__(self, capacity: int) -> None:
        self._buf: deque[Experience] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    # ── public interface ──────────────────────────────────────────────────────

    def push(
        self,
        state: torch.Tensor,
        action: int,
        reward: float,
        next_state: torch.Tensor,
    ) -> None:
        """Add one experience tuple to the buffer."""
        with self._lock:
            self._buf.append((state.detach().cpu(), action, reward, next_state.detach().cpu()))

    def sample(self, batch_size: int) -> Batch:
        """Sample *batch_size* experiences uniformly at random.

        Returns four tensors stacked along the batch dimension.

        Raises:
            ValueError: if the buffer contains fewer entries than *batch_size*.
        """
        with self._lock:
            if len(self._buf) < batch_size:
                raise ValueError(
                    f"Buffer has {len(self._buf)} experiences, need {batch_size}."
                )
            batch: List[Experience] = random.sample(self._buf, batch_size)

        states, actions, rewards, next_states = zip(*batch)
        return (
            torch.stack(states),                            # (B, input_size)
            torch.tensor(actions, dtype=torch.long),        # (B,)
            torch.tensor(rewards, dtype=torch.float32),     # (B,)
            torch.stack(next_states),                       # (B, input_size)
        )

    def clear(self) -> None:
        """Remove all stored experiences."""
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    @property
    def capacity(self) -> int:
        return self._buf.maxlen  # type: ignore[return-value]
