"""Unit tests for the neural_network agent package.

Covers:
  - ReplayBuffer: push, sample, clear, capacity, thread safety
  - AIEmployeeNet: forward pass shape, predict output, weight init
  - NeuralNetworkAgent: __init__, get_action, store_experience, learn, save/load, stats
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest
import torch

# Ensure runtime/agents is on sys.path (conftest.py may already do this)
_AGENTS_DIR = Path(__file__).parent.parent / "runtime" / "agents"
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from neural_network.replay_buffer import ReplayBuffer  # noqa: E402
from neural_network.model import AIEmployeeNet  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

INPUT_SIZE = 16
OUTPUT_SIZE = 4
HIDDEN = [32, 16]


def make_state(input_size: int = INPUT_SIZE) -> torch.Tensor:
    return torch.randn(input_size)


# ═════════════════════════════════════════════════════════════════════════════
# ReplayBuffer
# ═════════════════════════════════════════════════════════════════════════════

class TestReplayBuffer:
    def test_push_and_len(self):
        buf = ReplayBuffer(capacity=100)
        assert len(buf) == 0
        buf.push(make_state(), 0, 1.0, make_state())
        assert len(buf) == 1

    def test_capacity_evicts_oldest(self):
        buf = ReplayBuffer(capacity=5)
        for _ in range(10):
            buf.push(make_state(), 0, 1.0, make_state())
        assert len(buf) == 5

    def test_sample_returns_correct_shapes(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(20):
            buf.push(make_state(), 0, 1.0, make_state())
        states, actions, rewards, next_states = buf.sample(8)
        # push() stores 1-D tensors; torch.stack yields (B, input_size)
        assert states.shape == (8, INPUT_SIZE)
        assert actions.shape == (8,)
        assert rewards.shape == (8,)
        assert next_states.shape == (8, INPUT_SIZE)

    def test_sample_raises_when_too_small(self):
        buf = ReplayBuffer(capacity=100)
        buf.push(make_state(), 0, 1.0, make_state())
        with pytest.raises(ValueError):
            buf.sample(10)

    def test_clear(self):
        buf = ReplayBuffer(capacity=100)
        for _ in range(10):
            buf.push(make_state(), 0, 1.0, make_state())
        buf.clear()
        assert len(buf) == 0

    def test_capacity_property(self):
        buf = ReplayBuffer(capacity=42)
        assert buf.capacity == 42

    def test_thread_safety(self):
        """Concurrent pushes must not corrupt the buffer."""
        buf = ReplayBuffer(capacity=1000)
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

        assert errors == [], f"Thread errors: {errors}"
        assert len(buf) == 500


# ═════════════════════════════════════════════════════════════════════════════
# AIEmployeeNet
# ═════════════════════════════════════════════════════════════════════════════

class TestAIEmployeeNet:
    def test_forward_shape(self):
        net = AIEmployeeNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        x = torch.randn(4, INPUT_SIZE)
        out = net(x)
        assert out.shape == (4, OUTPUT_SIZE)

    def test_predict_returns_valid_action_and_confidence(self):
        net = AIEmployeeNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        x = torch.randn(1, INPUT_SIZE)
        action, conf = net.predict(x)
        assert action.shape == (1,)
        assert conf.shape == (1,)
        assert 0 <= int(action[0].item()) < OUTPUT_SIZE
        assert 0.0 <= float(conf[0].item()) <= 1.0

    def test_predict_preserves_train_mode(self):
        net = AIEmployeeNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        net.train()
        net.predict(torch.randn(1, INPUT_SIZE))
        assert net.training  # should be restored

    def test_predict_preserves_eval_mode(self):
        net = AIEmployeeNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        net.eval()
        net.predict(torch.randn(1, INPUT_SIZE))
        assert not net.training  # should remain eval

    def test_single_sample_forward(self):
        """BatchNorm requires >1 sample in training mode; eval mode should work for 1."""
        net = AIEmployeeNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE)
        net.eval()
        out = net(torch.randn(1, INPUT_SIZE))
        assert out.shape == (1, OUTPUT_SIZE)


# ═════════════════════════════════════════════════════════════════════════════
# NeuralNetworkAgent (minimal — avoids heavy I/O by patching model_path)
# ═════════════════════════════════════════════════════════════════════════════

class TestNeuralNetworkAgent:
    """Tests that work without a real nn_config.yaml by overriding defaults."""

    @pytest.fixture()
    def agent(self, tmp_path, monkeypatch):
        """Create a lightweight NeuralNetworkAgent pointing at tmp_path."""
        # Monkey-patch the _DEFAULTS so sizes are tiny
        import neural_network.agent as nn_mod
        monkeypatch.setattr(nn_mod, "_DEFAULTS", {
            "model": {
                "model_path":   str(tmp_path / "test_model.pth"),
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
                "gamma":              0.99,
                "min_buffer_size":    8,
                "max_grad_norm":      1.0,
            },
            "device": "cpu",
            "ui": {"reward_window": 10},
        })
        from neural_network.agent import NeuralNetworkAgent
        # Force re-read defaults by passing a non-existent config path
        a = NeuralNetworkAgent(config_path=str(tmp_path / "no_config.yaml"))
        return a

    def test_get_action_returns_valid_index_and_confidence(self, agent):
        state = make_state(INPUT_SIZE)
        action, confidence = agent.get_action(state)
        assert 0 <= action < OUTPUT_SIZE
        assert 0.0 <= confidence <= 1.0

    def test_get_action_accepts_batch(self, agent):
        state = torch.randn(2, INPUT_SIZE)
        action, confidence = agent.get_action(state)
        # Returns first element
        assert 0 <= action < OUTPUT_SIZE

    def test_store_experience_increments_count(self, agent):
        s = make_state(INPUT_SIZE)
        agent.store_experience(s, 0, 1.0, make_state(INPUT_SIZE))
        assert agent.experience_count == 1

    def test_learn_runs_and_returns_loss(self, agent):
        for _ in range(10):
            s = make_state(INPUT_SIZE)
            agent.store_experience(s, 0, 1.0, make_state(INPUT_SIZE))
        loss = agent.learn()
        assert isinstance(loss, float)
        assert loss >= 0.0

    def test_learn_skips_when_buffer_too_small(self, agent):
        # Fresh agent with empty buffer — learn should return 0.0
        loss = agent.learn()
        assert loss == 0.0

    def test_save_and_load(self, agent, tmp_path):
        # Do a learn step so we have meaningful weights
        for _ in range(10):
            agent.store_experience(make_state(INPUT_SIZE), 0, 1.0, make_state(INPUT_SIZE))
        agent.learn()
        agent.save()

        # Check file exists
        assert agent._model_path.exists()

        # Create fresh agent and load
        from neural_network.agent import NeuralNetworkAgent
        import neural_network.agent as nn_mod
        agent2 = NeuralNetworkAgent.__new__(NeuralNetworkAgent)
        agent2.cfg = agent.cfg
        import torch.optim as optim
        from neural_network.model import AIEmployeeNet
        from neural_network.replay_buffer import ReplayBuffer
        from collections import deque
        agent2.device = torch.device("cpu")
        agent2.model = AIEmployeeNet(INPUT_SIZE, HIDDEN, OUTPUT_SIZE, dropout=0.0).to("cpu")
        agent2.optimizer = optim.Adam(agent2.model.parameters(), lr=1e-3)
        agent2.loss_fn = __import__("torch.nn", fromlist=["CrossEntropyLoss"]).CrossEntropyLoss()
        agent2.replay_buffer = ReplayBuffer(200)
        agent2.batch_size = 8
        agent2.update_frequency = 5
        agent2.min_buffer_size = 8
        agent2.max_grad_norm = 1.0
        agent2.gamma = 0.99
        agent2.experience_count = 0
        agent2.learn_step = 0
        agent2.reward_window = deque(maxlen=10)
        agent2.last_loss = 0.0
        agent2.last_reward = 0.0
        agent2._model_path = agent._model_path
        agent2.load()
        assert agent2.learn_step == agent.learn_step

    def test_stats_keys(self, agent):
        s = agent.stats()
        for key in ("learn_step", "experience_count", "buffer_size", "last_loss", "avg_reward", "device"):
            assert key in s

    def test_reward_window_average(self, agent):
        for _ in range(5):
            agent.store_experience(make_state(INPUT_SIZE), 0, 1.0, make_state(INPUT_SIZE))
        assert agent.stats()["avg_reward"] == pytest.approx(1.0)

    def test_automatic_learn_trigger(self, agent):
        """learn() should be called automatically after update_frequency experiences."""
        initial_learn_step = agent.learn_step
        # Need min_buffer_size + update_frequency experiences to guarantee a learn
        total = agent.min_buffer_size + agent.update_frequency
        for _ in range(total):
            agent.store_experience(make_state(INPUT_SIZE), 0, 1.0, make_state(INPUT_SIZE))
        assert agent.learn_step > initial_learn_step
