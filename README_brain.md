# Central Neural Brain — Integration Guide

## Overview

`runtime/brain/` is the **central intelligence** of AI Employee.
Every agent, every module, every decision routes through this single Brain.

```
runtime/brain/
├── __init__.py              # package entry point
├── model.py                 # BrainNet — PyTorch nn.Module
├── replay_buffer.py         # Prioritized Experience Replay (PER)
├── experience_collector.py  # Smart online/offline experience collector
└── brain.py                 # Brain — central singleton with background loop
runtime/ui/
└── neural_brain_tab.py      # Streamlit live monitor tab
runtime/config/
└── nn_config.yaml           # All hyperparameters & settings
runtime/models/
└── brain.pth                # Auto-created checkpoint (git-ignored)
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install torch pyyaml streamlit pandas
```

### 2. Launch the live UI
```bash
PYTHONPATH=runtime streamlit run runtime/ui/neural_brain_tab.py
```

### 3. Run tests
```bash
python -m pytest tests/test_brain.py -v
```

---

## How Every Agent Uses the Brain

```python
# ── At the top of any agent file ────────────────────────────────────────────
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))  # ensure runtime/ is on path

from brain.brain import get_brain
import torch

brain = get_brain()   # returns the global singleton — shared across all agents
```

### Decision loop
```python
def make_decision(features: list[float]) -> str:
    state = torch.tensor(features, dtype=torch.float32)

    # 1. Ask the brain
    action, confidence = brain.get_action(state)   # action=int, confidence=float

    # 2. Execute
    result = execute_action(action)

    # 3. Compute reward
    reward = 1.0 if result.success else -1.0

    # 4. Store experience — learning triggers automatically
    next_state = torch.tensor(extract_features(result.new_state), dtype=torch.float32)
    brain.store_experience(state, action, reward, next_state)

    return ACTION_LABELS[action]
```

---

## auto-updater Integration Example

```python
# runtime/agents/auto-updater/auto_updater.py  (addition)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[3]))  # repo root → runtime/

from brain.brain import get_brain
import torch

_brain = get_brain()

def _build_updater_state(changed_files: list, commit_sha: str) -> torch.Tensor:
    """Convert updater context to a feature vector."""
    features = [
        float(len(changed_files)) / 100.0,          # normalised file count
        float(len(commit_sha)) / 40.0,               # sha length (always ~40)
        1.0,                                          # internet available flag
    ]
    features += [0.0] * (64 - len(features))         # pad to input_size
    return torch.tensor(features, dtype=torch.float32)

# In the update loop, after deciding whether to apply an update:
state = _build_updater_state(changed_files, sha)
action, confidence = _brain.get_action(state)        # 0=apply, 1=skip, ...
# ... execute the update ...
reward = 1.0 if update_succeeded else -1.0
next_state = _build_updater_state([], sha)
_brain.store_experience(state, action, reward, next_state)
```

---

## Online vs Offline Learning

| Mode | Trigger | Data Source |
|------|---------|-------------|
| **Online** | Internet available | GitHub Issues, PRs, commits |
| **Offline** | No internet | Local JSONL logs, JSON state files, self-simulation |

The background thread checks for internet every `collect_interval` seconds and
automatically picks the right source. You can also force offline learning from
the UI or programmatically:

```python
brain.force_offline_learn()   # collect from local files + simulate
```

---

## Architecture: Prioritized Experience Replay

Each experience `(state, action, reward, next_state)` is stored with a priority
proportional to its TD error. High-error experiences are sampled more often,
accelerating learning on the most surprising outcomes.

```
Priority ∝ (|TD_error| + ε)^α
```

Importance-sampling weights correct for the sampling bias:
```
w_i = ((P(i) / min_P)^(-β))  normalised to max=1
```

Both `α` and `β` are configurable in `nn_config.yaml`.

---

## Configuration (`runtime/config/nn_config.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `model.input_size` | 64 | Feature vector length |
| `model.output_size` | 8 | Number of possible actions |
| `model.hidden_sizes` | [256,128,64] | Hidden layer widths |
| `training.learning_rate` | 0.0002 | Adam LR |
| `training.batch_size` | 32 | Mini-batch size |
| `training.update_frequency` | 10 | Auto-learn every N experiences |
| `training.per_alpha` | 0.6 | PER priority exponent |
| `training.per_beta` | 0.4 | PER IS-weight exponent |
| `training.autosave_every` | 100 | Auto-save every N learn steps |
| `background.enabled` | true | Run background learning loop |
| `background.collect_interval` | 120 | Seconds between collection runs |
| `background.learn_interval` | 30 | Seconds between background learns |

---

## Embedding the Tab in an Existing Streamlit App

```python
# app.py
import streamlit as st
from ui.neural_brain_tab import render_brain_tab

tabs = st.tabs(["Main Dashboard", "...", "🧠 Neural Brain"])
with tabs[-1]:
    render_brain_tab()
```
