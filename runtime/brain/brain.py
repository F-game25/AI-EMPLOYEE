"""brain.py — Central Neural Brain of AI Employee.

This is the single source of intelligence for the entire AI Employee system.
Every agent, every module, every decision routes through here.

Usage (from any module in the project):

    from brain.brain import get_brain

    brain = get_brain()                              # singleton
    action, confidence = brain.get_action(state)    # decide
    brain.store_experience(s, a, r, s_next)          # feedback
    brain.learn()                                    # manual trigger (optional)

The brain also runs a background thread that:
  1. Periodically collects new experiences (online or offline).
  2. Runs fine-tuning steps whenever enough data is available.
  3. Auto-saves the model every N learn steps.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim

from .model import BrainNet
from .replay_buffer import PrioritizedReplayBuffer
from .experience_collector import ExperienceCollector

# ── Config loader ─────────────────────────────────────────────────────────────
try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# ── Logging ───────────────────────────────────────────────────────────────────
_AI_HOME  = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))
_LOG_DIR  = _AI_HOME / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "brain.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [brain] %(levelname)s %(message)s",
    handlers=[logging.FileHandler(_LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger("brain")

# ── Project root ──────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # runtime/brain → repo root

# ── Default configuration ─────────────────────────────────────────────────────
_DEFAULTS: Dict[str, Any] = {
    "model": {
        "model_path":   "runtime/models/brain.pth",
        "input_size":   64,
        "hidden_sizes": [256, 128, 64],
        "output_size":  8,
        "dropout":      0.15,
    },
    "training": {
        "learning_rate":      2e-4,
        "batch_size":         32,
        "replay_buffer_size": 20_000,
        "update_frequency":   10,
        "min_buffer_size":    64,
        "max_grad_norm":      1.0,
        "per_alpha":          0.6,
        "per_beta":           0.4,
        "per_beta_increment": 0.001,
        "autosave_every":     100,
    },
    "background": {
        "enabled":            True,
        "collect_interval":   120,   # seconds between collection runs
        "learn_interval":     30,    # seconds between learn steps
        "max_collect_items":  30,
    },
    "device": "auto",
    "ui": {
        "update_interval": 3,
        "show_graphs":     True,
        "reward_window":   50,
        "max_log_lines":   200,
    },
}


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    cfg_path = Path(config_path) if config_path else _PROJECT_ROOT / "runtime" / "config" / "nn_config.yaml"
    if not cfg_path.exists() or not _HAS_YAML:
        return _DEFAULTS
    try:
        with cfg_path.open("r") as fh:
            raw = yaml.safe_load(fh) or {}
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
        logger.error("Config load failed: %s — using defaults.", exc)
        return _DEFAULTS


def _select_device(pref: str) -> torch.device:
    if pref == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(pref)


# ═════════════════════════════════════════════════════════════════════════════
class Brain:
    """Central neural brain — the single intelligence core of AI Employee.

    All agents and modules interact through:
        brain.get_action(state)            → (action_index, confidence)
        brain.store_experience(s,a,r,s')   → pushes to buffer, auto-learns
        brain.learn()                      → manual fine-tune step

    A background thread continuously collects experiences and runs learning
    steps without blocking any agent.

    Args:
        config_path: Optional path to nn_config.yaml.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.cfg  = _load_config(config_path)
        mcfg = self.cfg["model"]
        tcfg = self.cfg["training"]
        ucfg = self.cfg["ui"]
        bcfg = self.cfg["background"]

        self.device = _select_device(self.cfg["device"])
        logger.info("Brain initialising on device: %s", self.device)

        # ── Model ─────────────────────────────────────────────────────────────
        self.model = BrainNet(
            input_size=mcfg["input_size"],
            hidden_sizes=mcfg["hidden_sizes"],
            output_size=mcfg["output_size"],
            dropout=mcfg["dropout"],
        ).to(self.device)

        # ── Optimiser ─────────────────────────────────────────────────────────
        self.optimizer = optim.Adam(self.model.parameters(), lr=tcfg["learning_rate"])
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode="min", factor=0.5, patience=50, min_lr=1e-6
        )

        # ── Replay buffer ─────────────────────────────────────────────────────
        self.replay_buffer = PrioritizedReplayBuffer(
            capacity=tcfg["replay_buffer_size"],
            alpha=tcfg["per_alpha"],
            beta=tcfg["per_beta"],
            beta_increment=tcfg["per_beta_increment"],
        )

        # ── Experience collector ───────────────────────────────────────────────
        self.collector = ExperienceCollector(
            input_size=mcfg["input_size"],
            output_size=mcfg["output_size"],
            push_fn=self._push_raw,
        )

        # ── Hyperparams ───────────────────────────────────────────────────────
        self.batch_size:      int   = tcfg["batch_size"]
        self.update_frequency:int   = tcfg["update_frequency"]
        self.min_buffer_size: int   = tcfg["min_buffer_size"]
        self.max_grad_norm:   float = tcfg["max_grad_norm"]
        self.autosave_every:  int   = tcfg["autosave_every"]

        # ── Stats ─────────────────────────────────────────────────────────────
        self.experience_count: int = 0
        self.learn_step:       int = 0
        self.reward_window:    Deque[float] = deque(maxlen=ucfg["reward_window"])
        self.loss_history:     Deque[float] = deque(maxlen=200)
        self.last_loss:        float = 0.0
        self.last_reward:      float = 0.0
        self._prev_avg_reward: float = 0.0

        # ── Model path ────────────────────────────────────────────────────────
        self._model_path = _resolve(mcfg["model_path"])
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

        # ── Background thread ─────────────────────────────────────────────────
        self._stop_event   = threading.Event()
        self._bg_thread: Optional[threading.Thread] = None
        if bcfg.get("enabled", True):
            self._start_background(bcfg)

        logger.info("Brain ready. learn_step=%d  buffer=%d", self.learn_step, len(self.replay_buffer))

    # ── Internal push (used by collector) ────────────────────────────────────

    def _push_raw(
        self,
        state: torch.Tensor,
        action: int,
        reward: float,
        next_state: torch.Tensor,
    ) -> None:
        """Push without triggering auto-learn (used by background collector)."""
        if state.dim() > 1:
            state = state.squeeze(0)
        if next_state.dim() > 1:
            next_state = next_state.squeeze(0)
        self.replay_buffer.push(state.float(), action, reward, next_state.float())

    # ── Public API ────────────────────────────────────────────────────────────

    def get_action(self, state: torch.Tensor) -> Tuple[int, float]:
        """Ask the brain for the best action given a state.

        Args:
            state: 1-D tensor (input_size,) or batch (B, input_size).

        Returns:
            (action_index, confidence) for the first element of the batch.
        """
        if state.dim() == 1:
            state = state.unsqueeze(0)
        state = state.float().to(self.device)
        action_t, conf_t = self.model.predict(state)
        action     = int(action_t[0].item())
        confidence = float(conf_t[0].item())
        logger.debug("get_action → %d (conf=%.4f)", action, confidence)
        return action, confidence

    def store_experience(
        self,
        state:      torch.Tensor,
        action:     int,
        reward:     float,
        next_state: torch.Tensor,
    ) -> None:
        """Record an (s, a, r, s') tuple and trigger learning when appropriate.

        This is the primary feedback channel from every agent in the system.
        Call it after every decision with the actual outcome.

        Args:
            state:      Feature vector at decision time.
            action:     Action index chosen.
            reward:     Outcome signal (+1 success, 0 neutral, -1 failure, etc.).
            next_state: Feature vector after the action.
        """
        if state.dim() > 1:
            state = state.squeeze(0)
        if next_state.dim() > 1:
            next_state = next_state.squeeze(0)

        self.replay_buffer.push(state.float(), action, float(reward), next_state.float())
        self.reward_window.append(float(reward))
        self.last_reward  = float(reward)
        self.experience_count += 1

        if (
            self.experience_count % self.update_frequency == 0
            and len(self.replay_buffer) >= self.min_buffer_size
        ):
            self.learn()

    def learn(self) -> float:
        """Run one online mini-batch update with Prioritized Experience Replay.

        Returns:
            Cross-entropy loss value, or 0.0 if the buffer is too small.
        """
        if len(self.replay_buffer) < self.batch_size:
            return 0.0

        states, actions, rewards, next_states, indices, is_weights = \
            self.replay_buffer.sample(self.batch_size)

        states      = states.to(self.device)
        actions     = actions.to(self.device)
        rewards     = rewards.to(self.device)
        is_weights  = is_weights.to(self.device)

        # ── Reward-weighted cross-entropy ─────────────────────────────────────
        self.model.train()
        logits = self.model(states)                            # (B, output_size)

        per_sample_loss = nn.functional.cross_entropy(
            logits, actions, reduction="none"
        )                                                      # (B,)

        # Shift rewards to [0, 1]: −1→0, 0→0.5, +1→1
        reward_weights = (rewards + 1.0) / 2.0
        loss = (per_sample_loss * reward_weights * is_weights).mean()

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
        self.optimizer.step()

        loss_val = float(loss.item())
        self.scheduler.step(loss_val)
        self.last_loss = loss_val
        self.loss_history.append(loss_val)

        # Update priorities with TD errors
        with torch.no_grad():
            td_errors = per_sample_loss.detach().cpu()
        self.replay_buffer.update_priorities(indices, td_errors)

        self.learn_step += 1

        # ── Logging ───────────────────────────────────────────────────────────
        avg_reward = sum(self.reward_window) / max(len(self.reward_window), 1)
        delta = avg_reward - self._prev_avg_reward

        if abs(delta) > 0.01:
            direction = "↑ smarter" if delta > 0 else "↓ regressed"
            logger.info(
                "Brain %s: avg_reward %.4f→%.4f (Δ%.4f)  loss=%.6f  step=%d",
                direction, self._prev_avg_reward, avg_reward, delta,
                loss_val, self.learn_step,
            )
        else:
            logger.info(
                "Brain learn step=%d  loss=%.6f  avg_reward=%.4f  buffer=%d",
                self.learn_step, loss_val, avg_reward, len(self.replay_buffer),
            )

        self._prev_avg_reward = avg_reward

        if self.learn_step % self.autosave_every == 0:
            self.save()

        return loss_val

    def save(self) -> None:
        """Persist model weights and training state to disk."""
        checkpoint = {
            "model_state_dict":     self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "learn_step":           self.learn_step,
            "experience_count":     self.experience_count,
        }
        torch.save(checkpoint, self._model_path)
        logger.info("Brain saved → %s  (step=%d)", self._model_path, self.learn_step)

    def load(self) -> None:
        """Load model from disk; no-op if no checkpoint exists."""
        if not self._model_path.exists():
            logger.info("No brain checkpoint at %s — fresh start.", self._model_path)
            return
        try:
            ckpt = torch.load(self._model_path, map_location=self.device, weights_only=True)
            self.model.load_state_dict(ckpt["model_state_dict"])
            self.optimizer.load_state_dict(ckpt["optimizer_state_dict"])
            self.learn_step       = ckpt.get("learn_step",       0)
            self.experience_count = ckpt.get("experience_count", 0)
            logger.info(
                "Brain loaded ← %s  (step=%d  experiences=%d)",
                self._model_path, self.learn_step, self.experience_count,
            )
        except Exception as exc:
            logger.error("Brain load failed: %s — fresh start.", exc)

    def force_offline_learn(self) -> int:
        """Force-collect offline experiences and run a learn step.

        Returns:
            Number of experiences collected.
        """
        n = self.collector.offline.collect()
        for state, action, reward, next_state in n:
            self._push_raw(state, action, reward, next_state)
        if len(self.replay_buffer) >= self.batch_size:
            self.learn()
        logger.info("force_offline_learn: %d experiences collected.", len(n))
        return len(n)

    def stats(self) -> Dict[str, Any]:
        """Return a snapshot dict of all brain stats (used by the UI)."""
        avg_reward = (
            sum(self.reward_window) / len(self.reward_window)
            if self.reward_window else 0.0
        )
        return {
            "learn_step":       self.learn_step,
            "experience_count": self.experience_count,
            "buffer_size":      len(self.replay_buffer),
            "buffer_capacity":  self.replay_buffer.capacity,
            "last_loss":        self.last_loss,
            "last_reward":      self.last_reward,
            "avg_reward":       avg_reward,
            "loss_history":     list(self.loss_history),
            "device":           str(self.device),
            "model_path":       str(self._model_path),
            "is_online":        self.collector.is_online,
            "bg_running":       self._bg_thread is not None and self._bg_thread.is_alive(),
            "lr":               self.optimizer.param_groups[0]["lr"],
        }

    # ── Background learning loop ──────────────────────────────────────────────

    def _start_background(self, bcfg: Dict[str, Any]) -> None:
        self._bg_thread = threading.Thread(
            target=self._bg_loop,
            kwargs={
                "collect_interval": bcfg.get("collect_interval", 120),
                "learn_interval":   bcfg.get("learn_interval",   30),
                "max_collect":      bcfg.get("max_collect_items", 30),
            },
            daemon=True,
            name="brain-bg",
        )
        self._bg_thread.start()
        logger.info("Background learning loop started.")

    def _bg_loop(
        self,
        collect_interval: int,
        learn_interval:   int,
        max_collect:      int,
    ) -> None:
        """Background thread: collect + learn on schedule."""
        last_collect = 0.0
        last_learn   = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()

            if now - last_collect >= collect_interval:
                try:
                    self.collector.collect_and_push(max_collect)
                except Exception as exc:
                    logger.warning("Background collect error: %s", exc)
                last_collect = now

            if now - last_learn >= learn_interval:
                try:
                    if len(self.replay_buffer) >= self.batch_size:
                        self.learn()
                except Exception as exc:
                    logger.warning("Background learn error: %s", exc)
                last_learn = now

            time.sleep(5)

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._bg_thread and self._bg_thread.is_alive():
            self._bg_thread.join(timeout=10)
        logger.info("Brain stopped.")


# ═════════════════════════════════════════════════════════════════════════════
# Module-level singleton
# ═════════════════════════════════════════════════════════════════════════════

_brain_instance: Optional[Brain] = None
_brain_lock = threading.Lock()


def get_brain(config_path: Optional[str] = None) -> Brain:
    """Return the global Brain singleton (create on first call).

    This ensures every agent shares the same model and replay buffer.
    """
    global _brain_instance
    if _brain_instance is None:
        with _brain_lock:
            if _brain_instance is None:
                _brain_instance = Brain(config_path=config_path)
    return _brain_instance
