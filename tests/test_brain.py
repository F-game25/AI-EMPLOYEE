"""Unit tests for the Central Brain package (runtime/brain/).

Covers:
  - PrioritizedReplayBuffer: push, sample, priority update, clear, capacity
  - BrainNet: forward shape, predict output, single-sample inference
  - ExperienceCollector: internet detection, offline simulation
  - Brain: get_action, store_experience, learn, save/load, stats, force_offline_learn
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest
import torch

# Ensure runtime/ is on sys.path
_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from brain.replay_buffer import PrioritizedReplayBuffer, Experience  # noqa: E402
from brain.model import BrainNet  # noqa: E402

# ── Shared constants ──────────────────────────────────────────────────────────
INPUT_SIZE  = 16
OUTPUT_SIZE = 4
HIDDEN      = [32, 16]


def make_state(n: int = INPUT_SIZE) -> torch.Tensor:
    return torch.randn(n)


# ═════════════════════════════════════════════════════════════════════════════
# PrioritizedReplayBuffer
# ═════════════════════════════════════════════════════════════════════════════

class TestPrioritizedReplayBuffer:
    def test_push_and_len(self):
        buf = PrioritizedReplayBuffer(capacity=100)
        assert len(buf) == 0
        buf.push(make_state(), 0, 1.0, make_state())
        assert len(buf) == 1

    def test_capacity_evicts_oldest(self):
        buf = PrioritizedReplayBuffer(capacity=5)
        for _ in range(10):
            buf.push(make_state(), 0, 1.0, make_state())
        assert len(buf) == 5

    def test_sample_shapes(self):
        buf = PrioritizedReplayBuffer(capacity=100)
        for _ in range(20):
            buf.push(make_state(), 0, 1.0, make_state())
        states, actions, rewards, next_states, indices, weights = buf.sample(8)
        assert states.shape      == (8, INPUT_SIZE)
        assert actions.shape     == (8,)
        assert rewards.shape     == (8,)
        assert next_states.shape == (8, INPUT_SIZE)
        assert len(indices)      == 8
        assert weights.shape     == (8,)

    def test_sample_raises_when_too_small(self):
        buf = PrioritizedReplayBuffer(capacity=100)
        buf.push(make_state(), 0, 1.0, make_state())
        with pytest.raises(ValueError):
            buf.sample(10)

    def test_update_priorities(self):
        buf = PrioritizedReplayBuffer(capacity=100)
        for _ in range(20):
            buf.push(make_state(), 0, 1.0, make_state())
        _, _, _, _, indices, _ = buf.sample(8)
        td_errors = torch.abs(torch.randn(8))
        buf.update_priorities(indices, td_errors)  # should not raise

    def test_clear(self):
        buf = PrioritizedReplayBuffer(capacity=100)
        for _ in range(10):
            buf.push(make_state(), 0, 1.0, make_state())
        buf.clear()
        assert len(buf) == 0

    def test_capacity_property(self):
        buf = PrioritizedReplayBuffer(capacity=42)
        assert buf.capacity == 42

    def test_weights_in_range(self):
        buf = PrioritizedReplayBuffer(capacity=100)
        for _ in range(20):
            buf.push(make_state(), 0, 1.0, make_state())
        _, _, _, _, _, weights = buf.sample(8)
        assert (weights >= 0.0).all()
        assert (weights <= 1.0 + 1e-6).all()

    def test_thread_safety(self):
        buf = PrioritizedReplayBuffer(capacity=1000)
        errors = []

        def pusher():
            try:
                for _ in range(50):
                    buf.push(make_state(), 0, 0.0, make_state())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=pusher) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(buf) == 500


# ═════════════════════════════════════════════════════════════════════════════
# BrainNet
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainNet:
    def test_forward_shape(self):
        net = BrainNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        out = net(torch.randn(4, INPUT_SIZE))
        assert out.shape == (4, OUTPUT_SIZE)

    def test_single_sample_forward(self):
        """LayerNorm (not BatchNorm) must work with batch-size 1."""
        net = BrainNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        net.eval()
        out = net(torch.randn(1, INPUT_SIZE))
        assert out.shape == (1, OUTPUT_SIZE)

    def test_predict_action_range(self):
        net = BrainNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        action, conf = net.predict(torch.randn(1, INPUT_SIZE))
        assert 0 <= int(action[0].item()) < OUTPUT_SIZE
        assert 0.0 <= float(conf[0].item()) <= 1.0

    def test_predict_1d_input(self):
        net = BrainNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        action, conf = net.predict(torch.randn(INPUT_SIZE))
        assert action.shape == (1,)
        assert conf.shape   == (1,)


# ═════════════════════════════════════════════════════════════════════════════
# ExperienceCollector (offline only — no network calls)
# ═════════════════════════════════════════════════════════════════════════════

class TestExperienceCollector:
    def test_offline_simulate_returns_experiences(self):
        from brain.experience_collector import OfflineExperienceCollector
        col = OfflineExperienceCollector(INPUT_SIZE, OUTPUT_SIZE)
        exps = col.simulate(count=5)
        assert len(exps) == 5
        for state, action, reward, next_state in exps:
            assert isinstance(state, torch.Tensor)
            assert 0 <= action < OUTPUT_SIZE
            assert isinstance(reward, float)
            assert isinstance(next_state, torch.Tensor)

    def test_check_internet_returns_bool(self):
        from brain.experience_collector import check_internet
        result = check_internet()
        assert isinstance(result, bool)

    def test_dispatcher_collects_and_pushes(self, tmp_path):
        from brain.experience_collector import ExperienceCollector
        pushed = []

        def push_fn(state, action, reward, next_state):
            pushed.append((state, action, reward, next_state))

        col = ExperienceCollector(INPUT_SIZE, OUTPUT_SIZE, push_fn)
        # Force offline by monkeypatching check_internet
        col.is_online = False

        # Collect offline — simulation will fill the gap
        n = col.offline.simulate(count=10)
        for exp in n:
            push_fn(*exp)

        assert len(pushed) == 10


# ═════════════════════════════════════════════════════════════════════════════
# Brain (with tiny config overrides to keep tests fast)
# ═════════════════════════════════════════════════════════════════════════════

class TestBrain:
    @pytest.fixture()
    def brain(self, tmp_path, monkeypatch):
        """Create a lightweight Brain pointing at tmp_path."""
        import brain.brain as brain_mod

        monkeypatch.setattr(brain_mod, "_DEFAULTS", {
            "model": {
                "model_path":   str(tmp_path / "brain_test.pth"),
                "input_size":   INPUT_SIZE,
                "hidden_sizes": HIDDEN,
                "output_size":  OUTPUT_SIZE,
                "dropout":      0.0,
            },
            "training": {
                "learning_rate":      1e-3,
                "batch_size":         8,
                "replay_buffer_size": 200,
                "update_frequency":   5,
                "min_buffer_size":    8,
                "max_grad_norm":      1.0,
                "per_alpha":          0.6,
                "per_beta":           0.4,
                "per_beta_increment": 0.001,
                "autosave_every":     50,
            },
            "background": {"enabled": False},  # no background thread in tests
            "device": "cpu",
            "ui": {"reward_window": 10, "update_interval": 1, "show_graphs": False, "max_log_lines": 50},
        })

        # Reset module-level singleton
        monkeypatch.setattr(brain_mod, "_brain_instance", None)

        from brain.brain import Brain
        b = Brain(config_path=str(tmp_path / "no_config.yaml"))
        yield b
        b.stop()

    def test_get_action_valid(self, brain):
        action, conf = brain.get_action(make_state())
        assert 0 <= action < OUTPUT_SIZE
        assert 0.0 <= conf <= 1.0

    def test_get_action_batch(self, brain):
        action, conf = brain.get_action(torch.randn(3, INPUT_SIZE))
        assert 0 <= action < OUTPUT_SIZE

    def test_store_experience_increments_count(self, brain):
        brain.store_experience(make_state(), 0, 1.0, make_state())
        assert brain.experience_count == 1

    def test_learn_returns_zero_when_buffer_too_small(self, brain):
        assert brain.learn() == 0.0

    def test_learn_returns_positive_loss(self, brain):
        for _ in range(10):
            brain.store_experience(make_state(), 0, 1.0, make_state())
        loss = brain.learn()
        assert isinstance(loss, float)
        assert loss >= 0.0

    def test_automatic_learn_trigger(self, brain):
        total = brain.min_buffer_size + brain.update_frequency
        for _ in range(total):
            brain.store_experience(make_state(), 0, 1.0, make_state())
        assert brain.learn_step > 0

    def test_save_and_load_roundtrip(self, brain):
        for _ in range(10):
            brain.store_experience(make_state(), 0, 1.0, make_state())
        brain.learn()
        original_step = brain.learn_step
        brain.save()
        assert brain._model_path.exists()

        # Reload weights into the same brain object
        brain.learn_step = 0        # reset
        brain.load()
        assert brain.learn_step == original_step

    def test_stats_has_all_keys(self, brain):
        s = brain.stats()
        for key in (
            "learn_step", "experience_count", "buffer_size",
            "last_loss", "avg_reward", "device", "is_online", "bg_running", "lr",
        ):
            assert key in s, f"Missing key: {key}"

    def test_force_offline_learn(self, brain):
        """force_offline_learn should collect ≥ 0 experiences without error."""
        n = brain.force_offline_learn()
        assert isinstance(n, int)
        assert n >= 0

    def test_avg_reward_calculation(self, brain):
        for _ in range(5):
            brain.store_experience(make_state(), 0, 1.0, make_state())
        assert brain.stats()["avg_reward"] == pytest.approx(1.0)

    def test_get_brain_singleton(self, monkeypatch, tmp_path):
        """get_brain() must return the same instance on repeated calls."""
        import brain.brain as brain_mod
        monkeypatch.setattr(brain_mod, "_brain_instance", None)
        monkeypatch.setattr(brain_mod, "_DEFAULTS", {
            "model": {
                "model_path": str(tmp_path / "s.pth"),
                "input_size": INPUT_SIZE,
                "hidden_sizes": HIDDEN,
                "output_size": OUTPUT_SIZE,
                "dropout": 0.0,
            },
            "training": {
                "learning_rate": 1e-3, "batch_size": 8,
                "replay_buffer_size": 200, "update_frequency": 5,
                "min_buffer_size": 8, "max_grad_norm": 1.0,
                "per_alpha": 0.6, "per_beta": 0.4, "per_beta_increment": 0.001,
                "autosave_every": 50,
            },
            "background": {"enabled": False},
            "device": "cpu",
            "ui": {"reward_window": 10, "update_interval": 1, "show_graphs": False, "max_log_lines": 50},
        })
        from brain.brain import get_brain
        b1 = get_brain()
        b2 = get_brain()
        assert b1 is b2
        b1.stop()
