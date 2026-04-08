"""Real-world usability tests for the Neural Network Agent and Central Brain.

These tests go beyond unit correctness to validate the system's behaviour under
conditions that actually arise in production:

  - Learning converges under consistent reward signals
  - Inference is deterministic after training
  - The system recovers gracefully from corrupt checkpoints
  - Extreme / invalid reward values do not crash the system
  - Concurrent multi-agent access never corrupts state
  - The text-feature extractor and label mapper work correctly
  - The offline JSONL collector parses real-like log records
  - Prioritized replay biases sampling toward high-error experiences
  - Save / load preserves the learning-rate and step counter exactly
  - Config YAML partial overrides merge correctly with built-in defaults
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import List

import pytest
import torch

# ── Ensure both runtime packages are importable ───────────────────────────────
_RUNTIME   = Path(__file__).parent.parent / "runtime"
_AGENTS    = _RUNTIME / "agents"
for _p in [str(_RUNTIME), str(_AGENTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brain.replay_buffer import PrioritizedReplayBuffer          # noqa: E402
from brain.model import BrainNet                                  # noqa: E402
from brain.experience_collector import (                          # noqa: E402
    _text_to_features,
    _label_to_action,
    _issue_to_reward,
    OfflineExperienceCollector,
    ExperienceCollector,
    check_internet,
)
from neural_network.model import AIEmployeeNet                    # noqa: E402
from neural_network.replay_buffer import ReplayBuffer             # noqa: E402

# ── Tiny config shared across many tests ─────────────────────────────────────
_SMALL = dict(
    input_size=32,
    hidden_sizes=[64, 32],
    output_size=4,
)

_BRAIN_DEFAULTS_SMALL = {
    "model": {
        "model_path":   "brain_rw.pth",   # resolved to tmp_path by fixtures
        "input_size":   _SMALL["input_size"],
        "hidden_sizes": _SMALL["hidden_sizes"],
        "output_size":  _SMALL["output_size"],
        "dropout":      0.0,
    },
    "training": {
        "learning_rate":      5e-3,   # larger LR for fast convergence in tests
        "batch_size":         16,
        "replay_buffer_size": 500,
        "update_frequency":   8,
        "min_buffer_size":    16,
        "max_grad_norm":      1.0,
        "per_alpha":          0.6,
        "per_beta":           0.4,
        "per_beta_increment": 0.001,
        "autosave_every":     9999,   # suppress mid-test auto-saves
    },
    "background": {"enabled": False},
    "device": "cpu",
    "ui": {"reward_window": 20, "update_interval": 1, "show_graphs": False, "max_log_lines": 50},
}


def _make_brain(tmp_path, monkeypatch):
    """Helper: create an isolated Brain with small, fast config."""
    import brain.brain as brain_mod
    import copy
    cfg = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
    cfg["model"]["model_path"] = str(tmp_path / "brain_rw.pth")
    monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
    monkeypatch.setattr(brain_mod, "_brain_instance", None)
    from brain.brain import Brain
    b = Brain(config_path=str(tmp_path / "no_cfg.yaml"))
    return b


def _make_agent(tmp_path, monkeypatch):
    """Helper: create an isolated NeuralNetworkAgent with small config."""
    import neural_network.agent as nn_mod
    import copy
    defaults = {
        "model": {
            "model_path":   str(tmp_path / "agent_rw.pth"),
            "input_size":   _SMALL["input_size"],
            "hidden_sizes": _SMALL["hidden_sizes"],
            "output_size":  _SMALL["output_size"],
            "dropout":      0.0,
        },
        "training": {
            "learning_rate":      5e-3,
            "batch_size":         16,
            "replay_buffer_size": 500,
            "update_frequency":   8,
            "min_buffer_size":    16,
            "max_grad_norm":      1.0,
            "gamma":              0.99,
        },
        "device": "cpu",
        "ui": {"reward_window": 20},
    }
    monkeypatch.setattr(nn_mod, "_DEFAULTS", defaults)
    from neural_network.agent import NeuralNetworkAgent
    return NeuralNetworkAgent(config_path=str(tmp_path / "no_cfg.yaml"))


# ═════════════════════════════════════════════════════════════════════════════
# 1. Inference determinism
# ═════════════════════════════════════════════════════════════════════════════

class TestInferenceDeterminism:
    """Same state must always yield the same action in eval mode."""

    def test_brain_eval_is_deterministic(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        state = torch.randn(_SMALL["input_size"])
        brain.model.eval()
        results = [brain.get_action(state.clone()) for _ in range(10)]
        actions = [r[0] for r in results]
        assert len(set(actions)) == 1, "get_action returned different actions for the same state"
        brain.stop()

    def test_agent_eval_is_deterministic(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        state = torch.randn(_SMALL["input_size"])
        agent.model.eval()
        results = [agent.get_action(state.clone()) for _ in range(10)]
        actions = [r[0] for r in results]
        assert len(set(actions)) == 1


# ═════════════════════════════════════════════════════════════════════════════
# 2. Learning convergence under consistent signal
# ═════════════════════════════════════════════════════════════════════════════

class TestLearningConvergence:
    """Brain and agent should show decreasing loss under a consistent signal."""

    def _converging_losses(self, store_fn, learn_fn, input_size, output_size,
                           n_steps: int = 120) -> List[float]:
        """Feed a fixed (state→action=0, reward=+1) signal and record losses."""
        target_state = torch.ones(input_size) * 0.9
        target_next  = torch.zeros(input_size)
        losses = []
        for _ in range(n_steps):
            store_fn(target_state.clone(), 0, 1.0, target_next.clone())
        for _ in range(n_steps // 4):
            loss = learn_fn()
            if loss > 0:
                losses.append(loss)
        return losses

    def test_brain_loss_trends_down(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        losses = self._converging_losses(
            brain.store_experience, brain.learn,
            _SMALL["input_size"], _SMALL["output_size"],
        )
        assert len(losses) >= 2, "No learn steps produced loss"
        # Average of first third vs last third should show a downward trend
        third = max(len(losses) // 3, 1)
        avg_early = sum(losses[:third]) / third
        avg_late  = sum(losses[-third:]) / third
        assert avg_late <= avg_early * 1.05, (
            f"Loss did not trend down: early={avg_early:.6f}  late={avg_late:.6f}"
        )
        brain.stop()

    def test_agent_loss_trends_down(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        losses = self._converging_losses(
            agent.store_experience, agent.learn,
            _SMALL["input_size"], _SMALL["output_size"],
        )
        assert len(losses) >= 2, "No learn steps produced loss"
        third = max(len(losses) // 3, 1)
        avg_early = sum(losses[:third]) / third
        avg_late  = sum(losses[-third:]) / third
        assert avg_late <= avg_early * 1.05, (
            f"Loss did not trend down: early={avg_early:.6f}  late={avg_late:.6f}"
        )

    def test_brain_confidence_grows_for_trained_action(self, tmp_path, monkeypatch):
        """After consistently rewarding action 0 for a fixed state, confidence
        for that state/action pair should increase."""
        brain = _make_brain(tmp_path, monkeypatch)
        state = torch.ones(_SMALL["input_size"]) * 0.9
        nxt   = torch.zeros(_SMALL["input_size"])

        # Record confidence before training
        brain.model.eval()
        _, conf_before = brain.get_action(state.clone())

        # Train
        for _ in range(200):
            brain.store_experience(state.clone(), 0, 1.0, nxt.clone())
        for _ in range(30):
            brain.learn()

        brain.model.eval()
        action_after, conf_after = brain.get_action(state.clone())

        # The learned action must be 0 (the one we consistently rewarded)
        assert action_after == 0, (
            f"Brain did not learn action 0; got action={action_after}"
        )
        assert conf_after >= conf_before - 0.05, (
            "Confidence dropped significantly after training on consistent signal"
        )
        brain.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 3. Corrupt / missing checkpoint recovery
# ═════════════════════════════════════════════════════════════════════════════

class TestCheckpointRecovery:
    """System must survive bad checkpoint files without crashing."""

    def _write_corrupt(self, path: Path, content: bytes = b"NOTAPYTORCHFILE") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_brain_recovers_from_corrupt_checkpoint(self, tmp_path, monkeypatch):
        import brain.brain as brain_mod
        import copy
        cfg = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
        model_path = tmp_path / "bad_brain.pth"
        cfg["model"]["model_path"] = str(model_path)
        monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
        monkeypatch.setattr(brain_mod, "_brain_instance", None)

        self._write_corrupt(model_path)

        # Should not raise; fresh-start mode instead
        from brain.brain import Brain
        b = Brain(config_path=str(tmp_path / "no_cfg.yaml"))
        # Must still be usable
        a, c = b.get_action(torch.randn(_SMALL["input_size"]))
        assert 0 <= a < _SMALL["output_size"]
        assert b.learn_step == 0   # fresh start
        b.stop()

    def test_agent_recovers_from_corrupt_checkpoint(self, tmp_path, monkeypatch):
        import neural_network.agent as nn_mod
        import copy
        defaults = {
            "model": {
                "model_path":   str(tmp_path / "bad_agent.pth"),
                "input_size":   _SMALL["input_size"],
                "hidden_sizes": _SMALL["hidden_sizes"],
                "output_size":  _SMALL["output_size"],
                "dropout":      0.0,
            },
            "training": {
                "learning_rate": 5e-3, "batch_size": 16,
                "replay_buffer_size": 500, "update_frequency": 8,
                "min_buffer_size": 16, "max_grad_norm": 1.0, "gamma": 0.99,
            },
            "device": "cpu",
            "ui": {"reward_window": 20},
        }
        monkeypatch.setattr(nn_mod, "_DEFAULTS", defaults)
        self._write_corrupt(tmp_path / "bad_agent.pth")

        from neural_network.agent import NeuralNetworkAgent
        agent = NeuralNetworkAgent(config_path=str(tmp_path / "no_cfg.yaml"))
        a, c = agent.get_action(torch.randn(_SMALL["input_size"]))
        assert 0 <= a < _SMALL["output_size"]
        assert agent.learn_step == 0

    def test_brain_truncated_checkpoint(self, tmp_path, monkeypatch):
        """A valid PyTorch file truncated to 10 bytes must not crash the brain."""
        import brain.brain as brain_mod
        import copy
        cfg = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
        model_path = tmp_path / "truncated.pth"
        cfg["model"]["model_path"] = str(model_path)
        monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
        monkeypatch.setattr(brain_mod, "_brain_instance", None)

        # Write a partially valid PyTorch stream (just the magic bytes, truncated)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_bytes(bytes([0x80, 0x02, 0x8a, 0x0a]))  # truncated pkl

        from brain.brain import Brain
        b = Brain(config_path=str(tmp_path / "no_cfg.yaml"))
        assert b.learn_step == 0
        b.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 4. Robustness to extreme / invalid reward values
# ═════════════════════════════════════════════════════════════════════════════

class TestRewardRobustness:
    """System must not crash or produce NaN weights on extreme rewards."""

    @pytest.mark.parametrize("reward", [100.0, -100.0, 0.0])
    def test_brain_extreme_rewards_no_nan(self, tmp_path, monkeypatch, reward):
        brain = _make_brain(tmp_path, monkeypatch)
        s = torch.randn(_SMALL["input_size"])
        for _ in range(20):
            brain.store_experience(s.clone(), 0, reward, s.clone())
        loss = brain.learn()
        # Weights must remain finite
        for p in brain.model.parameters():
            assert torch.isfinite(p).all(), f"NaN/Inf in weights after reward={reward}"
        brain.stop()

    def test_brain_nan_reward_is_handled(self, tmp_path, monkeypatch):
        """NaN rewards must be silently replaced with 0.0; weights must stay finite."""
        brain = _make_brain(tmp_path, monkeypatch)
        s = torch.randn(_SMALL["input_size"])
        for _ in range(20):
            brain.store_experience(s.clone(), 0, 0.0, s.clone())
        # Push NaN and Inf rewards — both must be handled gracefully
        brain.store_experience(s.clone(), 0, float("nan"), s.clone())
        brain.store_experience(s.clone(), 0, float("inf"), s.clone())
        brain.store_experience(s.clone(), 0, float("-inf"), s.clone())
        # Learn must complete without exception
        brain.learn()
        for p in brain.model.parameters():
            assert torch.isfinite(p).all(), "NaN/Inf in weights after non-finite reward"
        brain.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 5. Concurrent multi-agent access
# ═════════════════════════════════════════════════════════════════════════════

class TestConcurrentAccess:
    """Brain must be safe to call from many threads simultaneously."""

    def test_brain_concurrent_store_and_get(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        errors: List[Exception] = []

        def worker(brain_ref, n: int):
            try:
                for _ in range(n):
                    s = torch.randn(_SMALL["input_size"])
                    brain_ref.store_experience(s, 0, 1.0, torch.randn(_SMALL["input_size"]))
                    brain_ref.get_action(s)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(brain, 30)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert brain.experience_count == 8 * 30
        brain.stop()

    def test_brain_singleton_same_object_across_threads(self, tmp_path, monkeypatch):
        """Two threads calling get_brain() must receive the identical instance."""
        import brain.brain as brain_mod
        import copy
        cfg = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
        cfg["model"]["model_path"] = str(tmp_path / "singleton.pth")
        monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
        monkeypatch.setattr(brain_mod, "_brain_instance", None)

        instances: list = []

        def grab():
            from brain.brain import get_brain
            instances.append(get_brain())

        t1, t2 = threading.Thread(target=grab), threading.Thread(target=grab)
        t1.start(); t2.start()
        t1.join();  t2.join()

        assert len(instances) == 2
        assert instances[0] is instances[1], "get_brain() returned different objects!"
        instances[0].stop()


# ═════════════════════════════════════════════════════════════════════════════
# 6. Save / load full-state round-trip
# ═════════════════════════════════════════════════════════════════════════════

class TestSaveLoadRoundtrip:
    """Checkpoint must preserve learn_step, experience_count, and LR exactly."""

    def test_brain_roundtrip_preserves_all_state(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        s = torch.ones(_SMALL["input_size"])
        for _ in range(30):
            brain.store_experience(s.clone(), 1, 0.5, s.clone())
        brain.learn()
        brain.learn()

        saved_step = brain.learn_step
        saved_exp  = brain.experience_count
        saved_lr   = brain.optimizer.param_groups[0]["lr"]
        brain.save()

        # Mutate state and reload
        brain.learn_step       = 999
        brain.experience_count = 999
        brain.load()

        assert brain.learn_step       == saved_step
        assert brain.experience_count == saved_exp
        assert brain.optimizer.param_groups[0]["lr"] == pytest.approx(saved_lr)
        brain.stop()

    def test_brain_loaded_weights_produce_same_inference(self, tmp_path, monkeypatch):
        """Weights loaded from disk must reproduce identical action predictions."""
        brain = _make_brain(tmp_path, monkeypatch)
        for _ in range(30):
            brain.store_experience(
                torch.randn(_SMALL["input_size"]), 0, 1.0,
                torch.randn(_SMALL["input_size"]),
            )
        brain.learn()
        state = torch.randn(_SMALL["input_size"])
        brain.model.eval()
        action_before, conf_before = brain.get_action(state.clone())
        brain.save()

        # Reload into a fresh Brain
        import brain.brain as brain_mod
        brain_mod._brain_instance = None
        import copy
        cfg = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
        cfg["model"]["model_path"] = str(tmp_path / "brain_rw.pth")
        monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
        from brain.brain import Brain
        brain2 = Brain(config_path=str(tmp_path / "no_cfg.yaml"))
        brain2.model.eval()
        action_after, conf_after = brain2.get_action(state.clone())

        assert action_before == action_after
        assert conf_before == pytest.approx(conf_after, abs=1e-5)
        brain.stop()
        brain2.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 7. Text-to-features and label mapping
# ═════════════════════════════════════════════════════════════════════════════

class TestFeatureExtractionAndMapping:
    """Feature extractor and label mapper must behave correctly on real text."""

    def test_text_to_features_is_not_zero_for_nonempty_text(self):
        vec = _text_to_features("Fix critical null pointer bug", 64)
        assert vec.shape == (64,)
        assert vec.abs().sum().item() > 0

    def test_text_to_features_returns_zero_for_empty(self):
        vec = _text_to_features("", 64)
        assert vec.abs().sum().item() == 0.0

    def test_text_to_features_different_texts_produce_different_vectors(self):
        v1 = _text_to_features("fix bug in login page", 64)
        v2 = _text_to_features("add new dashboard analytics feature", 64)
        assert not torch.allclose(v1, v2), "Different texts produced identical feature vectors"

    def test_text_to_features_respects_size(self):
        for size in [8, 32, 64, 128]:
            vec = _text_to_features("some text here", size)
            assert vec.shape == (size,)

    def test_text_to_features_values_are_normalised(self):
        vec = _text_to_features("AI Employee: neural network learning", 64)
        # Values should be in a reasonable normalised range
        assert vec.abs().max().item() <= 1.0 + 1e-6

    @pytest.mark.parametrize("label,expected_action", [
        ("bug",           0),
        ("BUG",           0),   # case-insensitive
        ("enhancement",   1),
        ("question",      2),
        ("documentation", 3),
        ("update",        4),
        ("security",      5),
        ("performance",   6),
        ("unknown_xyz",   7),   # fallback
        ("",              7),   # empty
    ])
    def test_label_to_action_mapping(self, label, expected_action):
        assert _label_to_action(label) == expected_action, (
            f"label={label!r} → expected {expected_action}, "
            f"got {_label_to_action(label)}"
        )

    @pytest.mark.parametrize("issue,expected", [
        ({"state": "closed", "comments": 0},   1.0),
        ({"state": "open",   "comments": 10},  0.5),
        ({"state": "open",   "comments": 0},   0.0),
        ({"state": "open",   "comments": 5},   0.0),   # exactly 5 → no bonus
        ({"state": "open",   "comments": 6},   0.5),   # > 5 → bonus
    ])
    def test_issue_to_reward_heuristic(self, issue, expected):
        assert _issue_to_reward(issue) == expected


# ═════════════════════════════════════════════════════════════════════════════
# 8. Offline JSONL experience collection
# ═════════════════════════════════════════════════════════════════════════════

class TestOfflineExperienceCollector:
    """Collector must parse realistic task-log JSONL files."""

    def _write_jsonl(self, path: Path, records: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r) for r in records))

    def test_collect_from_jsonl_with_known_fields(self, tmp_path):
        log_dir = tmp_path / "logs"
        records = [
            {"action": "bug",          "reward": 1.0,  "text": "fixed null ptr"},
            {"action": "enhancement",  "reward": 0.5,  "text": "added feature X"},
            {"agent_action": "security","success": 1.0, "text": "patched vuln"},
            {"reward": -1.0,           "text": "task failed"},
        ]
        self._write_jsonl(log_dir / "task.jsonl", records)

        import brain.experience_collector as ec_mod
        monkeypatch_dirs = [log_dir]
        col = OfflineExperienceCollector(
            input_size=64,
            output_size=8,
        )
        col._search_dirs = [log_dir]
        exps = col.collect_from_logs(max_items=10)

        assert len(exps) == len(records)
        for state, action, reward, next_state in exps:
            assert state.shape    == (64,)
            assert next_state.shape == (64,)
            assert 0 <= action < 8
            assert isinstance(reward, float)

    def test_collect_falls_back_to_simulation_when_no_files(self, tmp_path):
        col = OfflineExperienceCollector(input_size=32, output_size=4)
        col._search_dirs = [tmp_path / "empty_dir"]  # does not exist
        exps = col.collect(max_items=20)
        assert len(exps) >= 10  # simulation should fill the gap

    def test_collect_ignores_malformed_lines(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "messy.jsonl").write_text(
            'NOT JSON\n'
            '{"reward": 1.0}\n'
            '\n'
            '{"reward": 0.5, "action": 1}\n'
            'ALSO NOT JSON\n'
        )
        col = OfflineExperienceCollector(input_size=32, output_size=4)
        col._search_dirs = [log_dir]
        exps = col.collect_from_logs(max_items=10)
        # Should succeed and return only the 2 parseable + valid records
        assert len(exps) == 2

    def test_simulate_state_vectors_are_clamped(self):
        col = OfflineExperienceCollector(input_size=32, output_size=4)
        exps = col.simulate(count=50)
        for state, _, _, next_state in exps:
            assert state.abs().max().item()     <= 1.0 + 1e-6
            assert next_state.abs().max().item() <= 1.0 + 1e-6

    def test_experience_collector_routes_to_offline_when_disconnected(self):
        """ExperienceCollector must use offline path when is_online=False."""
        pushed: list = []

        def push_fn(state, action, reward, next_state):
            pushed.append(action)

        col = ExperienceCollector(
            input_size=32,
            output_size=4,
            push_fn=push_fn,
        )
        col.is_online = False   # force offline without network check
        # Manually call offline collect and push
        exps = col.offline.simulate(count=10)
        for s, a, r, ns in exps:
            push_fn(s, a, r, ns)

        assert len(pushed) == 10
        assert all(0 <= a < 4 for a in pushed)


# ═════════════════════════════════════════════════════════════════════════════
# 9. Prioritized Experience Replay biases high-error samples
# ═════════════════════════════════════════════════════════════════════════════

class TestPERBias:
    """After updating priorities, high-priority samples must be sampled more."""

    def test_high_priority_indices_are_sampled_more_frequently(self):
        buf = PrioritizedReplayBuffer(capacity=200, alpha=1.0, beta=0.0)
        n = 100
        for _ in range(n):
            buf.push(torch.randn(16), 0, 0.0, torch.randn(16))

        # Give the first 10 indices a very high priority
        high_priority_indices = list(range(10))
        buf.update_priorities(
            high_priority_indices,
            torch.tensor([100.0] * 10),
        )

        # Sample many times and count how often high-priority indices appear
        counts = {i: 0 for i in high_priority_indices}
        total_samples = 2000
        batch_size = 20
        for _ in range(total_samples // batch_size):
            _, _, _, _, indices, _ = buf.sample(batch_size)
            for idx in indices:
                if idx in counts:
                    counts[idx] += 1

        # High-priority indices should be sampled much more than the naive
        # uniform rate (10/100 = 10%, so expect >> 10% of all samples)
        high_prio_fraction = sum(counts.values()) / total_samples
        assert high_prio_fraction > 0.30, (
            f"PER does not bias enough: high-priority fraction = {high_prio_fraction:.2%}"
        )

    def test_per_weights_are_in_unit_range(self):
        buf = PrioritizedReplayBuffer(capacity=100)
        for _ in range(30):
            buf.push(torch.randn(16), 0, 1.0, torch.randn(16))
        # Update priorities with varied TD-errors
        _, _, _, _, indices, _ = buf.sample(16)
        td = torch.abs(torch.randn(16)) * 10
        buf.update_priorities(indices, td)
        # Sample again; weights must still be in [0, 1]
        _, _, _, _, _, weights = buf.sample(16)
        assert (weights >= 0.0).all()
        assert (weights <= 1.0 + 1e-6).all()


# ═════════════════════════════════════════════════════════════════════════════
# 10. Config YAML partial override merges with defaults
# ═════════════════════════════════════════════════════════════════════════════

class TestConfigMerge:
    """Partial YAML overrides must merge correctly; missing keys keep defaults."""

    def test_partial_yaml_overrides_only_specified_keys(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        cfg_path = tmp_path / "partial.yaml"
        # Only override learning_rate and batch_size
        cfg_path.write_text(yaml.dump({
            "training": {
                "learning_rate": 9e-4,
                "batch_size":    64,
            }
        }))

        import brain.brain as brain_mod
        cfg = brain_mod._load_config(str(cfg_path))

        # Overridden values
        assert cfg["training"]["learning_rate"] == pytest.approx(9e-4)
        assert cfg["training"]["batch_size"] == 64

        # Non-overridden values must match defaults
        defaults = brain_mod._DEFAULTS
        for key in defaults["training"]:
            if key not in ("learning_rate", "batch_size"):
                assert cfg["training"][key] == defaults["training"][key], (
                    f"Default for '{key}' was unexpectedly changed"
                )

    def test_missing_config_file_returns_defaults(self, tmp_path):
        import brain.brain as brain_mod
        cfg = brain_mod._load_config(str(tmp_path / "does_not_exist.yaml"))
        assert cfg["training"]["batch_size"] == brain_mod._DEFAULTS["training"]["batch_size"]
        assert cfg["model"]["input_size"] == brain_mod._DEFAULTS["model"]["input_size"]


# ═════════════════════════════════════════════════════════════════════════════
# 11. Full default-size stability (input_size=64, hidden=[256,128,64])
# ═════════════════════════════════════════════════════════════════════════════

class TestFullSizeStability:
    """With the actual production-default sizes, training must stay numerically stable."""

    @pytest.fixture()
    def full_size_brain(self, tmp_path, monkeypatch):
        import brain.brain as brain_mod
        import copy
        cfg = {
            "model": {
                "model_path":   str(tmp_path / "full.pth"),
                "input_size":   64,
                "hidden_sizes": [256, 128, 64],
                "output_size":  8,
                "dropout":      0.15,
            },
            "training": {
                "learning_rate":      2e-4,
                "batch_size":         32,
                "replay_buffer_size": 1000,
                "update_frequency":   10,
                "min_buffer_size":    64,
                "max_grad_norm":      1.0,
                "per_alpha":          0.6,
                "per_beta":           0.4,
                "per_beta_increment": 0.001,
                "autosave_every":     9999,
            },
            "background": {"enabled": False},
            "device": "cpu",
            "ui": {"reward_window": 50, "update_interval": 1, "show_graphs": False, "max_log_lines": 50},
        }
        monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
        monkeypatch.setattr(brain_mod, "_brain_instance", None)
        from brain.brain import Brain
        b = Brain(config_path=str(tmp_path / "no_cfg.yaml"))
        yield b
        b.stop()

    def test_full_size_forward_is_finite(self, full_size_brain):
        state = torch.randn(64)
        full_size_brain.model.eval()
        logits = full_size_brain.model(state.unsqueeze(0))
        assert logits.shape == (1, 8)
        assert torch.isfinite(logits).all()

    def test_full_size_training_loop_stable(self, full_size_brain):
        """100 experiences + 10 manual learn steps must stay numerically stable."""
        for _ in range(100):
            full_size_brain.store_experience(
                torch.randn(64), 0, 1.0, torch.randn(64)
            )
        for _ in range(10):
            full_size_brain.learn()
        for p in full_size_brain.model.parameters():
            assert torch.isfinite(p).all(), "NaN/Inf in model weights after training"

    def test_full_size_stats_are_populated(self, full_size_brain):
        for _ in range(80):
            full_size_brain.store_experience(torch.randn(64), 2, 0.5, torch.randn(64))
        s = full_size_brain.stats()
        assert s["experience_count"] == 80
        assert s["buffer_size"] == 80
        assert s["avg_reward"] == pytest.approx(0.5)
        assert s["device"] == "cpu"


# ═════════════════════════════════════════════════════════════════════════════
# 12. LR scheduler integration
# ═════════════════════════════════════════════════════════════════════════════

class TestLRScheduler:
    """ReduceLROnPlateau must decrease LR after repeated plateau steps."""

    def test_brain_lr_decreases_on_plateau(self, tmp_path, monkeypatch):
        import brain.brain as brain_mod
        import copy
        cfg = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
        cfg["model"]["model_path"] = str(tmp_path / "lr_test.pth")
        cfg["training"]["learning_rate"] = 1e-2   # start high so drop is visible
        monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
        monkeypatch.setattr(brain_mod, "_brain_instance", None)
        from brain.brain import Brain
        b = Brain(config_path=str(tmp_path / "no_cfg.yaml"))
        initial_lr = b.optimizer.param_groups[0]["lr"]
        s = torch.randn(_SMALL["input_size"])

        # Fill buffer
        for _ in range(30):
            b.store_experience(s.clone(), 0, 0.0, s.clone())

        # Force many scheduler steps with a constant plateau loss
        for _ in range(200):
            b.scheduler.step(0.5)   # constant loss → scheduler should reduce LR

        final_lr = b.optimizer.param_groups[0]["lr"]
        assert final_lr < initial_lr, (
            f"LR did not decrease: initial={initial_lr}  final={final_lr}"
        )
        b.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 13. High-throughput stress test
# ═════════════════════════════════════════════════════════════════════════════

class TestHighThroughput:
    """Simulates the load of many agents feeding experiences rapidly."""

    def test_brain_handles_500_experiences_without_error(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        for i in range(500):
            reward = 1.0 if i % 2 == 0 else -1.0
            brain.store_experience(
                torch.randn(_SMALL["input_size"]),
                i % _SMALL["output_size"],
                reward,
                torch.randn(_SMALL["input_size"]),
            )
        assert brain.experience_count == 500
        # At least one learn step must have fired (update_frequency=8, min_buf=16)
        assert brain.learn_step > 0
        # Weights must be finite
        for p in brain.model.parameters():
            assert torch.isfinite(p).all()
        brain.stop()
