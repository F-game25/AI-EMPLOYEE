"""model.py — PyTorch neural network for the AI Employee Central Brain.

Architecture: fully-connected feed-forward network with configurable hidden
layers, LayerNorm (works with batch-size 1), Dropout, and a linear head.

LayerNorm is used instead of BatchNorm so single-sample inference always works
without switching eval/train mode.
"""
from __future__ import annotations

from typing import List, Tuple

import torch
import torch.nn as nn


class BrainNet(nn.Module):
    """Feed-forward decision network — the central intelligence of AI Employee.

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
                nn.LayerNorm(hidden),       # works with batch-size 1
                nn.GELU(),                  # smooth activation
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
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(B, input_size) → (B, output_size) logits."""
        return self.net(x)

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Return (action_index, confidence) without gradient tracking.

        Works in both train and eval mode; does not change the model's mode.

        Args:
            x: State tensor of shape (B, input_size) or (input_size,).

        Returns:
            action:     Long tensor of shape (B,).
            confidence: Float tensor of shape (B,) — softmax probability of
                        the chosen action.
        """
        if x.dim() == 1:
            x = x.unsqueeze(0)
        logits = self(x)
        probs = torch.softmax(logits, dim=-1)
        action = probs.argmax(dim=-1)
        confidence = probs.max(dim=-1).values
        return action, confidence
