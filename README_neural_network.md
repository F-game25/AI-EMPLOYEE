# Neural Network Agent — Integration Guide

## Overview

`runtime/agents/neural_network/` contains a self-learning PyTorch decision agent for AI Employee.

### File Map

| File | Purpose |
|------|---------|
| `model.py` | `AIEmployeeNet` — fully-connected PyTorch `nn.Module` |
| `replay_buffer.py` | Thread-safe experience replay buffer |
| `agent.py` | `NeuralNetworkAgent` — combines model + buffer + online learning |
| `train.py` | Initial warm-up training with synthetic data |
| `inference_example.py` | Shows how the main AI calls the NN brain |
| `runtime/ui/neural_network_tab.py` | Streamlit live monitor tab |
| `runtime/config/nn_config.yaml` | All hyperparameters and UI settings |
| `runtime/models/ai_employee_nn.pth` | Saved checkpoint (auto-created) |

---

## Quick Start

### 1. Install dependencies
```bash
pip install torch pyyaml streamlit pandas
```

### 2. Warm-up training (optional but recommended)
```bash
# From repo root:
python runtime/agents/neural_network/train.py --episodes 500
```

### 3. Run the live Streamlit UI
```bash
streamlit run runtime/ui/neural_network_tab.py
```

### 4. Run the inference example
```bash
python runtime/agents/neural_network/inference_example.py
```

---

## How the Main AI Uses the Neural Network Brain

```python
# In your main agent / orchestrator:
from agents.neural_network.agent import NeuralNetworkAgent
import torch

nn_brain = NeuralNetworkAgent()   # loads config + checkpoint automatically

# --- Decision loop ---
def make_decision(issue_data: dict) -> str:
    # 1. Convert issue data to a feature vector
    features = extract_features(issue_data)          # returns list[float], length == input_size
    state = torch.tensor(features, dtype=torch.float32)

    # 2. Ask the brain
    action, confidence = nn_brain.get_action(state)  # action=int, confidence=float

    # 3. Execute the action
    result = execute_action(action)

    # 4. Compute reward from outcome
    reward = +1.0 if result.success else -1.0

    # 5. Store experience — learning is triggered automatically
    next_state = torch.tensor(extract_features(result.new_state), dtype=torch.float32)
    nn_brain.store_experience(state, action, reward, next_state)

    return ACTION_LABELS[action]
```

---

## Configuration (`runtime/config/nn_config.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `model.input_size` | 64 | Feature vector length |
| `model.output_size` | 8 | Number of possible actions |
| `model.hidden_sizes` | [128, 64] | Hidden layer widths |
| `training.learning_rate` | 0.0003 | Adam LR |
| `training.batch_size` | 32 | Mini-batch size |
| `training.update_frequency` | 10 | Learn every N experiences |
| `training.replay_buffer_size` | 10000 | Max stored experiences |
| `training.min_buffer_size` | 64 | Minimum before first learn |
| `ui.update_interval` | 3 | Streamlit refresh (seconds) |
| `ui.reward_window` | 50 | Rolling avg reward window |

---

## How Online Learning Works

1. **`store_experience(s, a, r, s')`** pushes to the replay buffer.
2. Every `update_frequency` calls (default 10) **`learn()`** is invoked automatically.
3. `learn()` samples a random mini-batch and computes a **reward-weighted cross-entropy loss**:
   - reward = +1 → full reinforcement
   - reward = 0  → half weight
   - reward = −1 → penalised (weight = 0)
4. Gradients are clipped to `max_grad_norm` (catastrophic forgetting prevention).
5. Experience replay ensures the model does not overfit recent data.
6. Model is auto-saved every 100 learn steps.

---

## Embedding the Tab in an Existing Streamlit App

```python
# app.py
import streamlit as st
from ui.neural_network_tab import render_tab

tab_main, tab_nn = st.tabs(["Main", "🧠 Neural Network"])
with tab_nn:
    render_tab()
```
