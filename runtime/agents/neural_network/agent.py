"""agent.py — NeuralNetworkAgent: the self-learning brain of AI Employee.

Usage (from any other module):
    from agents.neural_network.agent import NeuralNetworkAgent

    nn_agent = NeuralNetworkAgent()
    action, confidence = nn_agent.get_action(state_vector)
    nn_agent.store_experience(state_vector, action, reward, next_state_vector)
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim

# ── Local imports ─────────────────────────────────────────────────────────────
from .model import AIEmployeeNet
from .replay_buffer import ReplayBuffer

# ── Config loader (pure-stdlib so no extra deps) ──────────────────────────────
try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# ── Logger setup (mirrors auto_updater.py style) ──────────────────────────────
_AI_HOME = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))
_LOG_DIR = _AI_HOME / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "neural_network.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [neural_network] %(levelname)s %(message)s",
    handlers=[logging.FileHandler(_LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger("neural_network")

# ── Default hyperparameters (used when YAML is missing/invalid) ───────────────
_DEFAULTS: Dict[str, Any] = {
    "model": {
        "model_path":   "runtime/models/ai_employee_nn.pth",
        "input_size":   64,
        "hidden_sizes": [128, 64],
        "output_size":  8,
        "dropout":      0.2,
    },
    "training": {
        "learning_rate":     3e-4,
        "batch_size":        32,
        "replay_buffer_size": 10_000,
        "update_frequency":  10,
        "gamma":             0.99,
        "min_buffer_size":   64,
        "max_grad_norm":     1.0,
    },
    "device": "auto",
    "ui": {
        "reward_window": 50,
    },
}

# ── Resolved project root (so relative paths in config work) ──────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # …/runtime/agents/neural_network → repo root


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    return _PROJECT_ROOT / p


def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load nn_config.yaml; fall back to _DEFAULTS on any error."""
    cfg_path = Path(config_path) if config_path else _PROJECT_ROOT / "runtime" / "config" / "nn_config.yaml"
    if not cfg_path.exists():
        logger.warning("nn_config.yaml not found at %s — using defaults.", cfg_path)
        return _DEFAULTS

    if not _HAS_YAML:
        logger.warning("PyYAML not installed — using default config.")
        return _DEFAULTS

    try:
        with cfg_path.open("r") as fh:
            raw = yaml.safe_load(fh) or {}
        # Merge with defaults (shallow merge per top-level section)
        cfg: Dict[str, Any] = {}
        for section, default_val in _DEFAULTS.items():
            if isinstance(default_val, dict):
                merged = dict(default_val)
                merged.update(raw.get(section, {}))
                cfg[section] = merged
            else:
                cfg[section] = raw.get(section, default_val)
        return cfg
    except Exception as exc:
        logger.error("Failed to parse nn_config.yaml: %s — using defaults.", exc)
        return _DEFAULTS


def _select_device(preference: str) -> torch.device:
    if preference == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(preference)


# ═════════════════════════════════════════════════════════════════════════════
class NeuralNetworkAgent:
    """Self-learning decision agent for AI Employee.

    The agent wraps an ``AIEmployeeNet`` model and a ``ReplayBuffer``.  Every
    ``update_frequency`` calls to :meth:`store_experience` it automatically
    runs an online fine-tuning step (:meth:`learn`).

    Args:
        config_path: Optional path to ``nn_config.yaml``.  If *None* the file
                     is looked up at ``runtime/config/nn_config.yaml`` relative
                     to the project root.
    """

    # ── construction ─────────────────────────────────────────────────────────
    def __init__(self, config_path: Optional[str] = None) -> None:
        self.cfg = _load_config(config_path)
        mcfg = self.cfg["model"]
        tcfg = self.cfg["training"]
        ucfg = self.cfg["ui"]

        self.device = _select_device(self.cfg["device"])
        logger.info("NeuralNetworkAgent using device: %s", self.device)

        # Model
        self.model = AIEmployeeNet(
            input_size=mcfg["input_size"],
            hidden_sizes=mcfg["hidden_sizes"],
            output_size=mcfg["output_size"],
            dropout=mcfg["dropout"],
        ).to(self.device)

        # Optimiser
        self.optimizer = optim.Adam(self.model.parameters(), lr=tcfg["learning_rate"])
        self.loss_fn = nn.CrossEntropyLoss()

        # Replay buffer
        self.replay_buffer = ReplayBuffer(capacity=tcfg["replay_buffer_size"])

        # Hyperparams
        self.batch_size: int = tcfg["batch_size"]
        self.update_frequency: int = tcfg["update_frequency"]
        self.min_buffer_size: int = tcfg["min_buffer_size"]
        self.max_grad_norm: float = tcfg["max_grad_norm"]
        self.gamma: float = tcfg["gamma"]

        # Stats
        self.experience_count: int = 0
        self.learn_step: int = 0
        self.reward_window: Deque[float] = deque(maxlen=ucfg["reward_window"])
        self.last_loss: float = 0.0
        self.last_reward: float = 0.0

        # Model path
        self._model_path = _resolve(mcfg["model_path"])
        self._model_path.parent.mkdir(parents=True, exist_ok=True)

        # Load checkpoint if it exists
        self.load()

    # ── public API ────────────────────────────────────────────────────────────

    def get_action(self, state: torch.Tensor) -> Tuple[int, float]:
        """Return the best action index and its confidence score.

        Args:
            state: 1-D tensor of shape ``(input_size,)`` or a batch
                   ``(B, input_size)``.

        Returns:
            ``(action_index, confidence)`` for the first element of the batch.
        """
        if state.dim() == 1:
            state = state.unsqueeze(0)
        state = state.float().to(self.device)

        action_t, conf_t = self.model.predict(state)
        action = int(action_t[0].item())
        confidence = float(conf_t[0].item())

        logger.debug("get_action → action=%d  confidence=%.4f", action, confidence)
        return action, confidence

    def store_experience(
        self,
        state: torch.Tensor,
        action: int,
        reward: float,
        next_state: torch.Tensor,
    ) -> None:
        """Push one experience into the replay buffer and trigger learning.

        Learning is triggered automatically every ``update_frequency``
        experiences once the buffer reaches ``min_buffer_size``.

        Args:
            state:      State vector at time *t*.
            action:     Action index chosen at time *t*.
            reward:     Scalar reward received (e.g. +1, 0, −1).
            next_state: State vector at time *t+1*.
        """
        # Flatten to 1-D before storing so torch.stack in sample() gives (B, input_size)
        if state.dim() > 1:
            state = state.squeeze(0)
        if next_state.dim() > 1:
            next_state = next_state.squeeze(0)

        self.replay_buffer.push(state.float(), action, float(reward), next_state.float())
        self.reward_window.append(float(reward))
        self.last_reward = float(reward)
        self.experience_count += 1

        if (
            self.experience_count % self.update_frequency == 0
            and len(self.replay_buffer) >= self.min_buffer_size
        ):
            self.learn()

    def learn(self) -> float:
        """Run one online mini-batch update.

        Returns:
            The cross-entropy loss value for this update step.
        """
        if len(self.replay_buffer) < self.batch_size:
            logger.debug("Skipping learn: buffer too small (%d < %d).", len(self.replay_buffer), self.batch_size)
            return 0.0

        states, actions, rewards, next_states = self.replay_buffer.sample(self.batch_size)
        states = states.to(self.device)               # (B, input_size)
        actions = actions.to(self.device)             # (B,)
        rewards = rewards.to(self.device)             # (B,)
        next_states = next_states.to(self.device)     # (B, input_size)

        # --- Cross-entropy supervised signal: predict the taken action -------
        # We weight the loss by the reward so positive outcomes are reinforced
        # and negative outcomes are penalised.
        self.model.train()
        logits = self.model(states)                      # (B, output_size)
        ce_loss = nn.functional.cross_entropy(logits, actions, reduction="none")  # (B,)

        # Shift rewards to [0, 1] for a stable weighting signal
        reward_weights = (rewards + 1.0) / 2.0                  # −1→0, 0→0.5, +1→1
        loss = (ce_loss * reward_weights).mean()

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
        self.optimizer.step()

        loss_val = float(loss.item())
        self.last_loss = loss_val
        self.learn_step += 1

        avg_reward = sum(self.reward_window) / max(len(self.reward_window), 1)
        logger.info(
            "learn step=%d  loss=%.6f  avg_reward(last %d)=%.4f  buffer=%d",
            self.learn_step,
            loss_val,
            len(self.reward_window),
            avg_reward,
            len(self.replay_buffer),
        )

        # Auto-save every 100 learn steps
        if self.learn_step % 100 == 0:
            self.save()

        return loss_val

    def save(self) -> None:
        """Persist model weights + optimiser state to disk."""
        checkpoint = {
            "model_state_dict":     self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "learn_step":           self.learn_step,
            "experience_count":     self.experience_count,
        }
        torch.save(checkpoint, self._model_path)
        logger.info("Model saved → %s  (learn_step=%d)", self._model_path, self.learn_step)

    def load(self) -> None:
        """Load model weights from disk (no-op if the file does not exist)."""
        if not self._model_path.exists():
            logger.info("No checkpoint found at %s — starting from scratch.", self._model_path)
            return

        try:
            checkpoint = torch.load(self._model_path, map_location=self.device, weights_only=True)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
            self.learn_step = checkpoint.get("learn_step", 0)
            self.experience_count = checkpoint.get("experience_count", 0)
            logger.info(
                "Checkpoint loaded ← %s  (learn_step=%d  experiences=%d)",
                self._model_path,
                self.learn_step,
                self.experience_count,
            )
        except Exception as exc:
            logger.error("Failed to load checkpoint: %s — starting from scratch.", exc)

    # ── convenience / introspection ───────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return a snapshot of the agent's current stats."""
        avg_reward = (
            sum(self.reward_window) / len(self.reward_window)
            if self.reward_window
            else 0.0
        )
        return {
            "learn_step":       self.learn_step,
            "experience_count": self.experience_count,
            "buffer_size":      len(self.replay_buffer),
            "buffer_capacity":  self.replay_buffer.capacity,
            "last_loss":        self.last_loss,
            "last_reward":      self.last_reward,
            "avg_reward":       avg_reward,
            "device":           str(self.device),
            "model_path":       str(self._model_path),
        }
