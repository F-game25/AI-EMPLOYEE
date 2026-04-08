"""train.py — Initial training script for the NeuralNetworkAgent.

Run this once to warm-up the replay buffer with synthetic experiences and
perform the first few hundred learning steps before deploying the agent.

Usage:
    python -m agents.neural_network.train          # from runtime/
    python runtime/agents/neural_network/train.py  # from repo root
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import torch

# Allow running from the repo root or from runtime/
_HERE = Path(__file__).resolve()
for _candidate in [_HERE.parents[2], _HERE.parents[3]]:
    if (_candidate / "agents").exists() or (_candidate / "runtime" / "agents").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))

from agents.neural_network.agent import NeuralNetworkAgent  # noqa: E402


def synthetic_state(input_size: int) -> torch.Tensor:
    """Generate a random state vector sampled from a standard normal distribution."""
    return torch.randn(input_size)


def run_training(num_episodes: int = 500, config_path: str | None = None) -> None:
    agent = NeuralNetworkAgent(config_path=config_path)
    input_size = agent.cfg["model"]["input_size"]
    output_size = agent.cfg["model"]["output_size"]

    print(f"\n{'=' * 60}")
    print(f"  AI Employee — Neural Network Initial Training")
    print(f"  Episodes : {num_episodes}")
    print(f"  Device   : {agent.device}")
    print(f"{'=' * 60}\n")

    for episode in range(1, num_episodes + 1):
        state = synthetic_state(input_size)

        # Get the agent's predicted action
        action, confidence = agent.get_action(state)

        # Simulate a reward: random mix weighted towards success
        reward_choices = [1.0, 1.0, 0.5, 0.0, -1.0]
        reward = random.choice(reward_choices)

        next_state = synthetic_state(input_size)

        agent.store_experience(state, action, reward, next_state)

        if episode % 50 == 0:
            s = agent.stats()
            print(
                f"  ep={episode:4d}  buffer={s['buffer_size']:5d}"
                f"  learn_step={s['learn_step']:4d}"
                f"  loss={s['last_loss']:.6f}"
                f"  avg_reward={s['avg_reward']:.4f}"
            )

    # Final save
    agent.save()
    s = agent.stats()
    print(f"\n  Training complete.")
    print(f"  Learn steps  : {s['learn_step']}")
    print(f"  Avg reward   : {s['avg_reward']:.4f}")
    print(f"  Model saved  : {s['model_path']}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initial training for AI Employee NN.")
    parser.add_argument("--episodes", type=int, default=500, help="Number of synthetic training episodes.")
    parser.add_argument("--config", type=str, default=None, help="Path to nn_config.yaml.")
    args = parser.parse_args()
    run_training(num_episodes=args.episodes, config_path=args.config)
