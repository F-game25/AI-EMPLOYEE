"""model.py — PyTorch neural network for the AI Employee decision agent.

Architecture: fully-connected feed-forward network with configurable hidden
layers, BatchNorm, Dropout, and a final linear head (logits over actions).
"""
from __future__ import annotations

from typing import List

import torch
import torch.nn as nn


class AIEmployeeNet(nn.Module):
    """Feed-forward decision network.

    Args:
        input_size:   Dimensionality of the state vector.
        hidden_sizes: List of hidden-layer widths.
        output_size:  Number of action classes / prediction targets.
        dropout:      Dropout probability applied after each hidden layer.
    """

    def __init__(
        self,
        input_size: int,
        hidden_sizes: List[int],
        output_size: int,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()

        layers: list[nn.Module] = []
        prev = input_size
        for hidden in hidden_sizes:
            layers += [
                nn.Linear(prev, hidden),
                nn.BatchNorm1d(hidden),
                nn.ReLU(inplace=True),
                nn.Dropout(p=dropout),
            ]
            prev = hidden

        layers.append(nn.Linear(prev, output_size))
        self.net = nn.Sequential(*layers)

        self._init_weights()

    # ── weight initialisation ─────────────────────────────────────────────────
    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    # ── forward pass ──────────────────────────────────────────────────────────
    def forward(self, x: torch.Tensor) -> torch.Tensor:  # (B, input_size) → (B, output_size)
        return self.net(x)

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Return (action_index, confidence) for a single state tensor.

        Puts the model in eval mode, runs inference, then restores the
        previous training/eval state.
        """
        was_training = self.training
        self.eval()
        logits = self(x)                             # (B, output_size)
        probs = torch.softmax(logits, dim=-1)        # (B, output_size)
        action = probs.argmax(dim=-1)                # (B,)
        confidence = probs.max(dim=-1).values        # (B,)
        if was_training:
            self.train()
        return action, confidence
