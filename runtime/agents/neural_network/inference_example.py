"""inference_example.py — Demonstrates how to use NeuralNetworkAgent.

Shows how the main AI can call the neural network brain for a decision,
provide feedback, and how the agent improves over time.

Usage:
    python -m agents.neural_network.inference_example  # from runtime/
    python runtime/agents/neural_network/inference_example.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import torch

# Allow running from repo root or from runtime/
_HERE = Path(__file__).resolve()
for _candidate in [_HERE.parents[2], _HERE.parents[3]]:
    if (_candidate / "agents").exists() or (_candidate / "runtime" / "agents").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))

from agents.neural_network.agent import NeuralNetworkAgent  # noqa: E402

# ── Action labels (configure to match your project's action space) ────────────
ACTION_LABELS = [
    "execute_update",
    "flag_bug",
    "request_review",
    "skip",
    "escalate",
    "log_only",
    "retry",
    "notify_user",
]


def build_state_from_issue(issue_data: dict) -> torch.Tensor:
    """Convert raw issue data into a fixed-size float feature vector.

    This is a minimal illustrative encoder.  Replace with real feature
    engineering in production.
    """
    features = [
        float(issue_data.get("severity", 0)) / 10.0,
        float(issue_data.get("age_hours", 0)) / 720.0,
        float(issue_data.get("num_comments", 0)) / 100.0,
        float(issue_data.get("confidence_score", 0.5)),
        float(issue_data.get("is_regression", 0)),
        float(issue_data.get("has_reproduction", 0)),
    ]
    # Pad to input_size (64) with zeros
    features += [0.0] * (64 - len(features))
    return torch.tensor(features, dtype=torch.float32)


def main() -> None:
    print("\n" + "=" * 60)
    print("  AI Employee — Neural Network Inference Example")
    print("=" * 60 + "\n")

    agent = NeuralNetworkAgent()

    # ── Example 1: classify an incoming issue ─────────────────────────────────
    issue = {
        "severity": 8,
        "age_hours": 2,
        "num_comments": 3,
        "confidence_score": 0.9,
        "is_regression": 1,
        "has_reproduction": 1,
    }

    state = build_state_from_issue(issue)
    action, confidence = agent.get_action(state)
    label = ACTION_LABELS[action] if action < len(ACTION_LABELS) else f"action_{action}"

    print(f"  Issue   : severity={issue['severity']}  regression={issue['is_regression']}")
    print(f"  Action  : [{action}] {label}")
    print(f"  Confidence: {confidence:.1%}\n")

    # ── Example 2: provide feedback and trigger learning ──────────────────────
    # Simulate: the action was 'flag_bug' and it turned out to be correct → +1
    reward = 1.0
    next_issue = {**issue, "severity": 5, "age_hours": 3}
    next_state = build_state_from_issue(next_issue)

    agent.store_experience(state, action, reward, next_state)
    print(f"  Experience stored.  reward={reward}")

    # ── Example 3: how main AI integrates the brain ────────────────────────────
    print("\n  --- Integration snippet for main_agent.py ---")
    print(
        """
    # At the top of your main agent:
    from agents.neural_network.agent import NeuralNetworkAgent
    nn_brain = NeuralNetworkAgent()

    # In your decision loop:
    state_vec = build_state_from_issue(issue)
    action, confidence = nn_brain.get_action(state_vec)
    execute_action(action)

    # After the outcome is known:
    nn_brain.store_experience(state_vec, action, reward, next_state_vec)
    """
    )

    stats = agent.stats()
    print(f"  Agent stats: {stats}\n")


if __name__ == "__main__":
    main()
