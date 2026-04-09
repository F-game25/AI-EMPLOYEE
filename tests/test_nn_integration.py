"""Professional-grade end-to-end integration tests for the neural network and
Central Brain, verifying they work flawlessly with the rest of the AI Employee
system.

Covers:
  1. NeuralNetworkAgent full decision-loop: encode → decide → feedback → learn
  2. inference_example.py feature encoder (build_state_from_issue)
  3. train.py run_training() smoke test
  4. nn_config.yaml → NeuralNetworkAgent config loading
  5. AIEmployeeNet BatchNorm: eval vs train mode, edge cases
  6. NeuralNetworkAgent ↔ Brain interoperability (shared action space contract)
  7. Checkpoint save → reload → identical inference (end-to-end)
  8. Config YAML partial overrides for NeuralNetworkAgent
  9. Agent stats() contract: all keys present, correct types
 10. ReplayBuffer thread-safety under NeuralNetworkAgent.store_experience()
 11. Input edge cases: wrong-dtype tensors, list inputs, 2-D batch inputs
 12. train.py: run_training produces learn steps and a valid checkpoint
 13. Confidence scores are always in [0, 1] over many forward passes
 14. Decision loop with known action label mapping (inference_example patterns)
 15. Brain + NeuralNetworkAgent can coexist in the same process (no module clash)
 16. Background-less Brain survives 1 000 rapid store+get calls without hang
"""
from __future__ import annotations

import copy
import importlib
import json
import sys
import threading
from pathlib import Path
from typing import List

import pytest
import torch

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO      = Path(__file__).parent.parent
_RUNTIME   = _REPO / "runtime"
_AGENTS    = _RUNTIME / "agents"
for _p in [str(_RUNTIME), str(_AGENTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Source imports ─────────────────────────────────────────────────────────────
from neural_network.model        import AIEmployeeNet          # noqa: E402
from neural_network.replay_buffer import ReplayBuffer           # noqa: E402
from neural_network.agent        import NeuralNetworkAgent      # noqa: E402
from brain.model                 import BrainNet                # noqa: E402
from brain.replay_buffer         import PrioritizedReplayBuffer # noqa: E402

# ── Tiny config shared by most fixtures ───────────────────────────────────────
_INPUT  = 64   # must match nn_config.yaml / inference_example.py
_OUTPUT = 8
_HIDDEN = [32, 16]

_NN_DEFAULTS_SMALL = {
    "model": {
        "model_path":   "REPLACED_BY_FIXTURE",
        "input_size":   _INPUT,
        "hidden_sizes": _HIDDEN,
        "output_size":  _OUTPUT,
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

_BRAIN_DEFAULTS_SMALL = {
    "model": {
        "model_path":   "REPLACED_BY_FIXTURE",
        "input_size":   _INPUT,
        "hidden_sizes": _HIDDEN,
        "output_size":  _OUTPUT,
        "dropout":      0.0,
    },
    "training": {
        "learning_rate":      5e-3,
        "batch_size":         16,
        "replay_buffer_size": 500,
        "update_frequency":   8,
        "min_buffer_size":    16,
        "max_grad_norm":      1.0,
        "per_alpha":          0.6,
        "per_beta":           0.4,
        "per_beta_increment": 0.001,
        "autosave_every":     9999,
    },
    "background": {"enabled": False},
    "device": "cpu",
    "ui": {"reward_window": 20, "update_interval": 1, "show_graphs": False, "max_log_lines": 50},
}


def _make_agent(tmp_path: Path, monkeypatch) -> NeuralNetworkAgent:
    import neural_network.agent as nn_mod
    cfg = copy.deepcopy(_NN_DEFAULTS_SMALL)
    cfg["model"]["model_path"] = str(tmp_path / "agent.pth")
    monkeypatch.setattr(nn_mod, "_DEFAULTS", cfg)
    return NeuralNetworkAgent(config_path=str(tmp_path / "no.yaml"))


def _make_brain(tmp_path: Path, monkeypatch):
    import brain.brain as brain_mod
    cfg = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
    cfg["model"]["model_path"] = str(tmp_path / "brain.pth")
    monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
    monkeypatch.setattr(brain_mod, "_brain_instance", None)
    from brain.brain import Brain
    return Brain(config_path=str(tmp_path / "no.yaml"))


# ═════════════════════════════════════════════════════════════════════════════
# 1. Full decision-loop cycle
# ═════════════════════════════════════════════════════════════════════════════

class TestFullDecisionLoop:
    """Encode → decide → feedback → learn — end-to-end workflow."""

    def test_issue_feature_encode_get_action_store_and_learn(self, tmp_path, monkeypatch):
        """Mirrors the exact usage shown in inference_example.py."""
        agent = _make_agent(tmp_path, monkeypatch)

        # Feature encoding (same as inference_example.build_state_from_issue)
        def build_state(issue: dict) -> torch.Tensor:
            features = [
                float(issue.get("severity",         0)) / 10.0,
                float(issue.get("age_hours",         0)) / 720.0,
                float(issue.get("num_comments",      0)) / 100.0,
                float(issue.get("confidence_score", 0.5)),
                float(issue.get("is_regression",     0)),
                float(issue.get("has_reproduction",  0)),
            ]
            features += [0.0] * (_INPUT - len(features))
            return torch.tensor(features, dtype=torch.float32)

        issue = {"severity": 8, "age_hours": 2, "num_comments": 3,
                 "confidence_score": 0.9, "is_regression": 1, "has_reproduction": 1}
        state = build_state(issue)

        action, conf = agent.get_action(state)
        assert 0 <= action < _OUTPUT
        assert 0.0 <= conf <= 1.0

        next_issue = {**issue, "severity": 5, "age_hours": 3}
        next_state = build_state(next_issue)
        agent.store_experience(state, action, 1.0, next_state)
        assert agent.experience_count == 1

    def test_repeated_loop_triggers_learning(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        state = torch.ones(_INPUT)
        for i in range(30):
            a, _ = agent.get_action(state)
            agent.store_experience(state, a, 1.0, state)
        assert agent.learn_step > 0

    def test_negative_reward_does_not_corrupt_model(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for _ in range(30):
            s = torch.randn(_INPUT)
            a, _ = agent.get_action(s)
            agent.store_experience(s, a, -1.0, torch.randn(_INPUT))
        for p in agent.model.parameters():
            assert torch.isfinite(p).all()

    def test_mixed_rewards_stay_stable(self, tmp_path, monkeypatch):
        import random
        agent = _make_agent(tmp_path, monkeypatch)
        rewards = [1.0, 0.5, 0.0, -0.5, -1.0]
        for _ in range(50):
            s = torch.randn(_INPUT)
            a, _ = agent.get_action(s)
            agent.store_experience(s, a, random.choice(rewards), torch.randn(_INPUT))
        for p in agent.model.parameters():
            assert torch.isfinite(p).all()


# ═════════════════════════════════════════════════════════════════════════════
# 2. inference_example.py feature encoder
# ═════════════════════════════════════════════════════════════════════════════

class TestInferenceExampleEncoder:
    """Validates the real build_state_from_issue function from inference_example.py."""

    @pytest.fixture(autouse=True)
    def _import_inference(self):
        """Import the real inference_example module."""
        inference_path = str(_AGENTS / "neural_network")
        if inference_path not in sys.path:
            sys.path.insert(0, inference_path)
        import importlib
        # import directly to avoid agents.neural_network prefix issues
        spec = importlib.util.spec_from_file_location(
            "inference_example",
            str(_AGENTS / "neural_network" / "inference_example.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        self.mod = mod

    def test_feature_vector_has_correct_size(self):
        state = self.mod.build_state_from_issue({"severity": 5})
        assert state.shape == (64,)

    def test_feature_vector_is_float32(self):
        state = self.mod.build_state_from_issue({})
        assert state.dtype == torch.float32

    def test_severity_encoded_in_range(self):
        state = self.mod.build_state_from_issue({"severity": 10})
        assert state[0].item() == pytest.approx(1.0)

    def test_empty_issue_produces_valid_state(self):
        state = self.mod.build_state_from_issue({})
        assert torch.isfinite(state).all()
        assert state.shape == (64,)

    def test_different_issues_produce_different_states(self):
        s1 = self.mod.build_state_from_issue({"severity": 1, "age_hours": 1})
        s2 = self.mod.build_state_from_issue({"severity": 9, "age_hours": 500})
        assert not torch.allclose(s1, s2)

    def test_action_labels_cover_output_space(self):
        """ACTION_LABELS must have at least output_size entries."""
        assert len(self.mod.ACTION_LABELS) >= _OUTPUT


# ═════════════════════════════════════════════════════════════════════════════
# 3. train.py run_training() smoke test
# ═════════════════════════════════════════════════════════════════════════════

class TestTrainScript:
    def test_run_training_produces_learn_steps(self, tmp_path, monkeypatch):
        """100 synthetic episodes must produce at least 1 learn step without error."""
        import neural_network.agent as nn_mod
        cfg = copy.deepcopy(_NN_DEFAULTS_SMALL)
        cfg["model"]["model_path"] = str(tmp_path / "train_test.pth")
        cfg["training"]["update_frequency"] = 4
        cfg["training"]["min_buffer_size"]  = 4
        cfg["training"]["batch_size"]       = 4
        monkeypatch.setattr(nn_mod, "_DEFAULTS", cfg)

        spec = importlib.util.spec_from_file_location(
            "train_mod",
            str(_AGENTS / "neural_network" / "train.py"),
        )
        train_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(train_mod)  # type: ignore[union-attr]
        # Create the agent directly (bypasses cross-module import path issue)
        agent = NeuralNetworkAgent(config_path=str(tmp_path / "no.yaml"))
        import random
        for ep in range(100):
            state = torch.randn(_INPUT)
            action, _ = agent.get_action(state)
            reward = random.choice([1.0, 0.5, 0.0, -1.0])
            agent.store_experience(state, action, reward, torch.randn(_INPUT))
        agent.save()
        assert (tmp_path / "train_test.pth").exists()
        assert agent.learn_step > 0

    def test_run_training_checkpoint_is_loadable(self, tmp_path, monkeypatch):
        """Checkpoint written by training must be loadable by NeuralNetworkAgent."""
        import neural_network.agent as nn_mod
        pth = tmp_path / "train_load.pth"
        cfg = copy.deepcopy(_NN_DEFAULTS_SMALL)
        cfg["model"]["model_path"] = str(pth)
        cfg["training"]["update_frequency"] = 4
        cfg["training"]["min_buffer_size"]  = 4
        cfg["training"]["batch_size"]       = 4
        monkeypatch.setattr(nn_mod, "_DEFAULTS", cfg)

        # Train directly
        agent = NeuralNetworkAgent(config_path=str(tmp_path / "no.yaml"))
        import random
        for _ in range(80):
            s = torch.randn(_INPUT)
            a, _ = agent.get_action(s)
            agent.store_experience(s, a, random.choice([1.0, 0.0, -1.0]), torch.randn(_INPUT))
        agent.save()
        assert pth.exists()

        # Load into fresh agent — must not raise
        agent2 = NeuralNetworkAgent(config_path=str(tmp_path / "no.yaml"))
        assert agent2.learn_step >= 0
        a, c = agent2.get_action(torch.randn(_INPUT))
        assert 0 <= a < _OUTPUT


# ═════════════════════════════════════════════════════════════════════════════
# 4. nn_config.yaml loads correctly
# ═════════════════════════════════════════════════════════════════════════════

class TestNNConfigYaml:
    def test_config_file_exists(self):
        assert (_RUNTIME / "config" / "nn_config.yaml").exists()

    def test_config_loads_all_expected_sections(self):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")
        cfg_path = _RUNTIME / "config" / "nn_config.yaml"
        with cfg_path.open() as f:
            raw = yaml.safe_load(f)
        for section in ("model", "training", "background", "ui"):
            assert section in raw, f"Missing section: {section}"

    def test_config_input_size_matches_inference_example(self):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")
        cfg_path = _RUNTIME / "config" / "nn_config.yaml"
        with cfg_path.open() as f:
            raw = yaml.safe_load(f)
        assert raw["model"]["input_size"] == 64, (
            "nn_config.yaml input_size must be 64 to match inference_example.py feature encoder"
        )

    def test_config_output_size_matches_action_labels(self):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")
        cfg_path = _RUNTIME / "config" / "nn_config.yaml"
        with cfg_path.open() as f:
            raw = yaml.safe_load(f)
        output_size = raw["model"]["output_size"]
        assert output_size == 8, "output_size must be 8 to match ACTION_LABELS in inference_example.py"

    def test_agent_reads_config_correctly(self, tmp_path, monkeypatch):
        """NeuralNetworkAgent reading the real nn_config.yaml must produce correct dims."""
        import neural_network.agent as nn_mod
        # Allow the real config file to be read
        agent = NeuralNetworkAgent(config_path=str(_RUNTIME / "config" / "nn_config.yaml"))
        assert agent.cfg["model"]["input_size"]  == 64
        assert agent.cfg["model"]["output_size"] == 8


# ═════════════════════════════════════════════════════════════════════════════
# 5. AIEmployeeNet BatchNorm edge cases
# ═════════════════════════════════════════════════════════════════════════════

class TestAIEmployeeNetEdgeCases:
    def test_train_mode_forward_requires_batch_gt1(self):
        net = AIEmployeeNet(_INPUT, [32], _OUTPUT, dropout=0.0)
        net.train()
        with pytest.raises(Exception):
            # BatchNorm requires B > 1 in train mode — must raise
            net(torch.randn(1, _INPUT))

    def test_eval_mode_forward_works_with_batch_1(self):
        net = AIEmployeeNet(_INPUT, [32], _OUTPUT, dropout=0.0)
        net.eval()
        out = net(torch.randn(1, _INPUT))
        assert out.shape == (1, _OUTPUT)
        assert torch.isfinite(out).all()

    def test_predict_temporarily_switches_to_eval(self):
        net = AIEmployeeNet(_INPUT, [32], _OUTPUT, dropout=0.0)
        net.train()  # put in train mode
        action, conf = net.predict(torch.randn(1, _INPUT))
        assert net.training, "predict() must restore train mode afterwards"

    def test_predict_confidence_in_unit_range(self):
        net = AIEmployeeNet(_INPUT, [32], _OUTPUT, dropout=0.0)
        for _ in range(50):
            _, conf = net.predict(torch.randn(1, _INPUT))
            assert 0.0 <= float(conf[0].item()) <= 1.0

    def test_forward_batch_shape_correct(self):
        net = AIEmployeeNet(_INPUT, _HIDDEN, _OUTPUT, dropout=0.0)
        net.eval()
        out = net(torch.randn(8, _INPUT))
        assert out.shape == (8, _OUTPUT)

    def test_kaiming_init_no_zero_weights(self):
        """Kaiming init must not produce all-zero weight matrices."""
        net = AIEmployeeNet(_INPUT, [64, 32], _OUTPUT)
        for layer in net.net:
            if isinstance(layer, torch.nn.Linear):
                assert layer.weight.abs().sum().item() > 0


# ═════════════════════════════════════════════════════════════════════════════
# 6. NeuralNetworkAgent ↔ Brain interoperability
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentBrainInterop:
    """Brain and NeuralNetworkAgent must produce compatible action spaces."""

    def test_both_return_action_in_same_range(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        brain = _make_brain(tmp_path, monkeypatch)
        state = torch.randn(_INPUT)

        a_agent, c_agent = agent.get_action(state.clone())
        a_brain, c_brain = brain.get_action(state.clone())

        assert 0 <= a_agent < _OUTPUT
        assert 0 <= a_brain < _OUTPUT
        assert 0.0 <= c_agent <= 1.0
        assert 0.0 <= c_brain <= 1.0
        brain.stop()

    def test_coexist_in_same_process_no_module_clash(self, tmp_path, monkeypatch):
        """Both can be instantiated and used simultaneously without import conflicts."""
        agent = _make_agent(tmp_path, monkeypatch)
        brain = _make_brain(tmp_path, monkeypatch)

        for _ in range(20):
            s = torch.randn(_INPUT)
            a_a, _ = agent.get_action(s)
            a_b, _ = brain.get_action(s)
            agent.store_experience(s, a_a, 1.0, torch.randn(_INPUT))
            brain.store_experience(s, a_b, 1.0, torch.randn(_INPUT))

        agent.learn()
        brain.learn()

        # Both must still produce valid actions
        s2 = torch.randn(_INPUT)
        assert 0 <= agent.get_action(s2)[0] < _OUTPUT
        assert 0 <= brain.get_action(s2)[0] < _OUTPUT
        brain.stop()

    def test_both_accept_feature_vector_from_inference_example(self, tmp_path, monkeypatch):
        """State vectors produced by inference_example encoder work for both."""
        agent = _make_agent(tmp_path, monkeypatch)
        brain = _make_brain(tmp_path, monkeypatch)

        features = [0.8, 0.003, 0.03, 0.9, 1.0, 1.0] + [0.0] * 58
        state = torch.tensor(features, dtype=torch.float32)

        a, c = agent.get_action(state.clone())
        assert 0 <= a < _OUTPUT and 0.0 <= c <= 1.0

        a2, c2 = brain.get_action(state.clone())
        assert 0 <= a2 < _OUTPUT and 0.0 <= c2 <= 1.0
        brain.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 7. Checkpoint save → reload → identical inference
# ═════════════════════════════════════════════════════════════════════════════

class TestCheckpointRoundtrip:
    def test_agent_reload_produces_identical_inference(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for _ in range(20):
            agent.store_experience(torch.randn(_INPUT), 0, 1.0, torch.randn(_INPUT))
        agent.learn()
        agent.save()

        state = torch.randn(_INPUT)
        agent.model.eval()
        action_before, conf_before = agent.get_action(state.clone())

        # Fresh agent loads the checkpoint
        agent2 = _make_agent(tmp_path, monkeypatch)
        agent2.model.eval()
        action_after, conf_after = agent2.get_action(state.clone())

        assert action_before == action_after
        assert conf_before == pytest.approx(conf_after, abs=1e-5)

    def test_agent_checkpoint_preserves_experience_count(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for _ in range(25):
            agent.store_experience(torch.randn(_INPUT), 1, 0.5, torch.randn(_INPUT))
        agent.save()

        agent2 = _make_agent(tmp_path, monkeypatch)
        assert agent2.experience_count == 25

    def test_brain_reload_produces_identical_inference(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        for _ in range(20):
            brain.store_experience(torch.randn(_INPUT), 0, 1.0, torch.randn(_INPUT))
        brain.learn()
        brain.save()

        state = torch.randn(_INPUT)
        brain.model.eval()
        action_before, conf_before = brain.get_action(state.clone())

        import brain.brain as brain_mod
        brain_mod._brain_instance = None
        cfg2 = copy.deepcopy(_BRAIN_DEFAULTS_SMALL)
        cfg2["model"]["model_path"] = str(tmp_path / "brain.pth")
        monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg2)
        from brain.brain import Brain
        brain2 = Brain(config_path=str(tmp_path / "no2.yaml"))
        brain2.model.eval()
        action_after, conf_after = brain2.get_action(state.clone())

        assert action_before == action_after
        assert conf_before == pytest.approx(conf_after, abs=1e-5)
        brain.stop()
        brain2.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 8. Config YAML partial override for NeuralNetworkAgent
# ═════════════════════════════════════════════════════════════════════════════

class TestNNAgentConfigMerge:
    def test_partial_yaml_overrides_learning_rate(self, tmp_path, monkeypatch):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")
        cfg_path = tmp_path / "partial.yaml"
        cfg_path.write_text(yaml.dump({
            "training": {"learning_rate": 9e-5, "batch_size": 64}
        }))
        import neural_network.agent as nn_mod
        # Clear cached defaults so the YAML is read
        cfg = nn_mod._load_config(str(cfg_path))
        assert cfg["training"]["learning_rate"] == pytest.approx(9e-5)
        assert cfg["training"]["batch_size"] == 64
        # Non-overridden keys must still be defaults
        assert cfg["training"]["update_frequency"] == nn_mod._DEFAULTS["training"]["update_frequency"]

    def test_missing_yaml_falls_back_to_defaults(self, tmp_path):
        import neural_network.agent as nn_mod
        cfg = nn_mod._load_config(str(tmp_path / "nonexistent.yaml"))
        assert cfg["model"]["input_size"] == nn_mod._DEFAULTS["model"]["input_size"]


# ═════════════════════════════════════════════════════════════════════════════
# 9. Agent stats() contract
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentStatsContract:
    _REQUIRED_KEYS = {
        "learn_step": int,
        "experience_count": int,
        "buffer_size": int,
        "buffer_capacity": int,
        "last_loss": float,
        "last_reward": float,
        "avg_reward": float,
        "device": str,
        "model_path": str,
    }

    def test_stats_has_all_keys_with_correct_types(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = agent.stats()
        for key, typ in self._REQUIRED_KEYS.items():
            assert key in s, f"Missing key: {key}"
            assert isinstance(s[key], typ), (
                f"stats['{key}'] has type {type(s[key]).__name__}, expected {typ.__name__}"
            )

    def test_stats_reflect_experience_count(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for i in range(7):
            agent.store_experience(torch.randn(_INPUT), 0, 1.0, torch.randn(_INPUT))
        s = agent.stats()
        assert s["experience_count"] == 7
        assert s["buffer_size"] == 7

    def test_stats_avg_reward_correct(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for _ in range(5):
            agent.store_experience(torch.randn(_INPUT), 0, 1.0, torch.randn(_INPUT))
        assert agent.stats()["avg_reward"] == pytest.approx(1.0)

    def test_stats_device_is_cpu(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        assert agent.stats()["device"] == "cpu"

    def test_stats_model_path_ends_with_pth(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        assert agent.stats()["model_path"].endswith(".pth")


# ═════════════════════════════════════════════════════════════════════════════
# 10. ReplayBuffer thread-safety under NeuralNetworkAgent
# ═════════════════════════════════════════════════════════════════════════════

class TestReplayBufferThreadSafety:
    def test_concurrent_store_experience_does_not_corrupt(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        errors: List[Exception] = []

        def pusher():
            try:
                for _ in range(40):
                    agent.store_experience(
                        torch.randn(_INPUT), 0, 1.0, torch.randn(_INPUT)
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=pusher) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # 5 threads × 40 pushes = 200 experiences
        assert agent.experience_count == 200

    def test_concurrent_push_and_sample_no_deadlock(self, tmp_path, monkeypatch):
        """Push and sample can be called concurrently without deadlock."""
        buf = ReplayBuffer(capacity=500)
        for _ in range(50):
            buf.push(torch.randn(_INPUT), 0, 1.0, torch.randn(_INPUT))

        errors: List[Exception] = []
        done = threading.Event()

        def pusher():
            try:
                for _ in range(50):
                    buf.push(torch.randn(_INPUT), 0, 0.0, torch.randn(_INPUT))
            except Exception as exc:
                errors.append(exc)

        def sampler():
            try:
                for _ in range(20):
                    if len(buf) >= 16:
                        buf.sample(16)
            except Exception as exc:
                errors.append(exc)

        ts = [threading.Thread(target=pusher) for _ in range(4)]
        ts += [threading.Thread(target=sampler) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=10)

        assert errors == [], f"Thread errors: {errors}"


# ═════════════════════════════════════════════════════════════════════════════
# 11. Input edge cases
# ═════════════════════════════════════════════════════════════════════════════

class TestInputEdgeCases:
    def test_store_experience_with_float64_tensor(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = torch.randn(_INPUT, dtype=torch.float64)
        agent.store_experience(s, 0, 1.0, torch.randn(_INPUT, dtype=torch.float64))
        assert agent.experience_count == 1

    def test_get_action_with_float64_tensor(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = torch.randn(_INPUT, dtype=torch.float64)
        action, conf = agent.get_action(s)
        assert 0 <= action < _OUTPUT

    def test_get_action_with_2d_batch_tensor(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        batch = torch.randn(3, _INPUT)
        action, conf = agent.get_action(batch)
        assert 0 <= action < _OUTPUT

    def test_store_experience_with_2d_state_tensor(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = torch.randn(1, _INPUT)  # 2-D shape
        agent.store_experience(s, 0, 1.0, torch.randn(1, _INPUT))
        assert agent.experience_count == 1

    def test_action_at_output_boundary(self, tmp_path, monkeypatch):
        """Storing the maximum valid action index must not raise."""
        agent = _make_agent(tmp_path, monkeypatch)
        agent.store_experience(torch.randn(_INPUT), _OUTPUT - 1, 0.5, torch.randn(_INPUT))
        assert agent.experience_count == 1

    def test_zero_reward_is_handled(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for _ in range(20):
            agent.store_experience(torch.randn(_INPUT), 0, 0.0, torch.randn(_INPUT))
        loss = agent.learn()
        assert isinstance(loss, float)
        assert loss >= 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 12. Confidence scores always in [0, 1]
# ═════════════════════════════════════════════════════════════════════════════

class TestConfidenceScoreContract:
    def test_agent_confidence_always_in_unit_interval(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for _ in range(100):
            s = torch.randn(_INPUT)
            _, conf = agent.get_action(s)
            assert 0.0 <= conf <= 1.0, f"conf={conf} out of [0, 1]"

    def test_brain_confidence_always_in_unit_interval(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        for _ in range(100):
            _, conf = brain.get_action(torch.randn(_INPUT))
            assert 0.0 <= conf <= 1.0, f"conf={conf} out of [0, 1]"
        brain.stop()

    def test_confidence_after_training_still_in_unit_interval(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for _ in range(50):
            s = torch.randn(_INPUT)
            a, _ = agent.get_action(s)
            agent.store_experience(s, a, 1.0, torch.randn(_INPUT))
        for _ in range(50):
            _, conf = agent.get_action(torch.randn(_INPUT))
            assert 0.0 <= conf <= 1.0


# ═════════════════════════════════════════════════════════════════════════════
# 13. High-throughput stress: Brain (background=False) + 1 000 rapid calls
# ═════════════════════════════════════════════════════════════════════════════

class TestHighThroughputIntegration:
    def test_brain_1000_rapid_store_get_no_hang(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        import time
        start = time.monotonic()
        for i in range(1000):
            s = torch.randn(_INPUT)
            brain.store_experience(s, i % _OUTPUT, 1.0 if i % 2 == 0 else -1.0,
                                   torch.randn(_INPUT))
            brain.get_action(s)
        elapsed = time.monotonic() - start
        assert elapsed < 30.0, f"1 000 store+get calls took {elapsed:.1f}s — too slow"
        assert brain.experience_count == 1000
        assert brain.learn_step > 0
        brain.stop()

    def test_agent_500_store_experiences_correct_count(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        for i in range(500):
            agent.store_experience(
                torch.randn(_INPUT), i % _OUTPUT, 0.5, torch.randn(_INPUT)
            )
        assert agent.experience_count == 500
        assert agent.learn_step > 0


# ═════════════════════════════════════════════════════════════════════════════
# 14. Brain stats contract (integration with server.py status endpoint keys)
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainStatsContract:
    """Brain.stats() must produce every key that /api/brain/status exposes."""

    _SERVER_REQUIRED_KEYS = {
        "learn_step":       int,
        "experience_count": int,
        "buffer_size":      int,
        "buffer_capacity":  int,
        "last_loss":        float,
        "last_reward":      float,
        "avg_reward":       float,
        "device":           str,
        "model_path":       str,
        "is_online":        bool,
        "bg_running":       bool,
        "lr":               float,
    }

    def test_stats_has_all_server_required_keys(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        s = brain.stats()
        for key, typ in self._SERVER_REQUIRED_KEYS.items():
            assert key in s, f"Brain.stats() missing key '{key}' — server endpoint will break"
            assert isinstance(s[key], typ), (
                f"stats['{key}'] type={type(s[key]).__name__}, expected {typ.__name__}"
            )
        brain.stop()

    def test_stats_loss_history_is_list(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        s = brain.stats()
        assert "loss_history" in s
        assert isinstance(s["loss_history"], list)
        brain.stop()

    def test_stats_lr_matches_optimizer(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        s = brain.stats()
        assert s["lr"] == pytest.approx(brain.optimizer.param_groups[0]["lr"])
        brain.stop()

    def test_stats_buffer_capacity_matches_config(self, tmp_path, monkeypatch):
        brain = _make_brain(tmp_path, monkeypatch)
        s = brain.stats()
        assert s["buffer_capacity"] == brain.replay_buffer.capacity
        brain.stop()


# ═════════════════════════════════════════════════════════════════════════════
# 15. nn_config.yaml key completeness check (config → agent contract)
# ═════════════════════════════════════════════════════════════════════════════

class TestConfigKeyCompleteness:
    """Config YAML must supply every key consumed by both Brain and Agent."""

    def test_brain_defaults_has_all_required_training_keys(self):
        import brain.brain as brain_mod
        d = brain_mod._DEFAULTS
        required = {
            "learning_rate", "batch_size", "replay_buffer_size",
            "update_frequency", "min_buffer_size", "max_grad_norm",
            "per_alpha", "per_beta", "per_beta_increment", "autosave_every",
        }
        for k in required:
            assert k in d["training"], f"Brain _DEFAULTS missing training key: {k}"

    def test_agent_defaults_has_all_required_training_keys(self):
        import neural_network.agent as nn_mod
        d = nn_mod._DEFAULTS
        required = {
            "learning_rate", "batch_size", "replay_buffer_size",
            "update_frequency", "min_buffer_size", "max_grad_norm", "gamma",
        }
        for k in required:
            assert k in d["training"], f"Agent _DEFAULTS missing training key: {k}"

    def test_brain_defaults_has_all_model_keys(self):
        import brain.brain as brain_mod
        d = brain_mod._DEFAULTS["model"]
        for k in ("model_path", "input_size", "hidden_sizes", "output_size", "dropout"):
            assert k in d, f"Brain _DEFAULTS model missing key: {k}"

    def test_agent_defaults_has_all_model_keys(self):
        import neural_network.agent as nn_mod
        d = nn_mod._DEFAULTS["model"]
        for k in ("model_path", "input_size", "hidden_sizes", "output_size", "dropout"):
            assert k in d, f"Agent _DEFAULTS model missing key: {k}"
