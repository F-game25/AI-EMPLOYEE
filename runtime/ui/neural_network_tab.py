"""neural_network_tab.py — Streamlit live tab for the Neural Network agent.

Launch standalone:
    streamlit run runtime/ui/neural_network_tab.py

Or embed in the main Streamlit app (app.py):
    from ui.neural_network_tab import render_tab
    with tab_nn:
        render_tab()

The tab shows real-time stats, a live loss chart, and control buttons.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd  # noqa: E402 — used in chart rendering
import torch

# ── Path bootstrap (works both standalone and embedded) ──────────────────────
_HERE = Path(__file__).resolve()
_RUNTIME = _HERE.parents[1]           # runtime/
_REPO_ROOT = _HERE.parents[2]         # repo root

for _p in [str(_RUNTIME / "agents"), str(_RUNTIME), str(_REPO_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st  # noqa: E402

from agents.neural_network.agent import NeuralNetworkAgent  # noqa: E402

# ── Singleton agent (shared across Streamlit reruns via session_state) ────────


def _get_agent() -> NeuralNetworkAgent:
    if "nn_agent" not in st.session_state:
        st.session_state["nn_agent"] = NeuralNetworkAgent()
    return st.session_state["nn_agent"]


def _init_history() -> None:
    if "nn_loss_history" not in st.session_state:
        st.session_state["nn_loss_history"] = []
    if "nn_reward_history" not in st.session_state:
        st.session_state["nn_reward_history"] = []
    if "nn_last_action" not in st.session_state:
        st.session_state["nn_last_action"] = None
    if "nn_last_confidence" not in st.session_state:
        st.session_state["nn_last_confidence"] = None
    if "nn_last_state" not in st.session_state:
        st.session_state["nn_last_state"] = None


# ═════════════════════════════════════════════════════════════════════════════
def render_tab() -> None:
    """Render the Neural Network live tab inside a Streamlit app."""
    _init_history()
    agent = _get_agent()
    stats = agent.stats()
    cfg = agent.cfg

    st.header("🧠 Neural Network Agent — Live Monitor")
    st.caption(
        "Self-learning decision brain of AI Employee. "
        "Updates every few seconds with live loss, rewards, and model state."
    )

    # ── Top-level metric row ──────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Learn Steps", f"{stats['learn_step']:,}")
    c2.metric("Experiences", f"{stats['experience_count']:,}")
    c3.metric("Buffer", f"{stats['buffer_size']:,} / {stats['buffer_capacity']:,}")
    c4.metric("Device", stats["device"].upper())

    st.divider()

    # ── Last action & confidence ──────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Last Action")
        if st.session_state["nn_last_action"] is not None:
            st.write(f"**Action index:** `{st.session_state['nn_last_action']}`")
            st.write(f"**Confidence:** `{st.session_state['nn_last_confidence']:.1%}`")
        else:
            st.info("No action taken yet.")

        st.subheader("Last Reward & Outcome")
        st.write(f"**Last reward:** `{stats['last_reward']:.2f}`")
        st.write(f"**Avg reward (last {cfg['ui']['reward_window']}):** `{stats['avg_reward']:.4f}`")

    with col_right:
        st.subheader("Current State (last input)")
        if st.session_state["nn_last_state"] is not None:
            s = st.session_state["nn_last_state"]
            preview = s.squeeze()[:8].tolist()
            st.code(f"[{', '.join(f'{v:.3f}' for v in preview)}, ...]  (showing first 8 of {s.numel()})")
        else:
            st.info("No state captured yet.")

    st.divider()

    # ── Live loss chart ───────────────────────────────────────────────────────
    st.subheader("📉 Live Loss Chart")
    loss_hist = st.session_state["nn_loss_history"]
    if loss_hist:
        df = pd.DataFrame({"Loss": loss_hist})
        st.line_chart(df, use_container_width=True)
    else:
        st.info("Loss chart will appear once learning starts.")

    st.subheader("📈 Average Reward History")
    rew_hist = st.session_state["nn_reward_history"]
    if rew_hist:
        df_r = pd.DataFrame({"Avg Reward": rew_hist})
        st.line_chart(df_r, use_container_width=True)
    else:
        st.info("Reward history will appear after the first learn step.")

    st.divider()

    # ── Model stats ───────────────────────────────────────────────────────────
    st.subheader("⚙️ Model Stats")
    ms_col1, ms_col2 = st.columns(2)
    ms_col1.write(f"**Model path:** `{stats['model_path']}`")
    ms_col1.write(f"**Last loss:** `{stats['last_loss']:.6f}`")
    ms_col2.write(f"**Input size:** `{cfg['model']['input_size']}`")
    ms_col2.write(f"**Output size:** `{cfg['model']['output_size']}`")
    ms_col2.write(f"**Hidden layers:** `{cfg['model']['hidden_sizes']}`")
    ms_col2.write(f"**Learning rate:** `{cfg['training']['learning_rate']}`")

    st.divider()

    # ── Control buttons ───────────────────────────────────────────────────────
    st.subheader("🕹️ Controls")
    btn1, btn2, btn3, btn4 = st.columns(4)

    with btn1:
        if st.button("🎓 Manual Learn"):
            loss = agent.learn()
            _update_history(agent, loss)
            st.success(f"Learn step done — loss: {loss:.6f}")

    with btn2:
        if st.button("🗑️ Clear Buffer"):
            agent.replay_buffer.clear()
            st.warning("Replay buffer cleared.")

    with btn3:
        if st.button("💾 Save Model"):
            agent.save()
            st.success("Model saved.")

    with btn4:
        if st.button("🔄 Refresh"):
            _update_history(agent, stats["last_loss"])
            st.rerun()

    # ── Demo: run a synthetic inference to show the tab is alive ─────────────
    st.divider()
    st.subheader("🧪 Demo — Synthetic Inference")
    if st.button("Run Synthetic Inference"):
        state = torch.randn(cfg["model"]["input_size"])
        action, confidence = agent.get_action(state)
        st.session_state["nn_last_action"] = action
        st.session_state["nn_last_confidence"] = confidence
        st.session_state["nn_last_state"] = state.unsqueeze(0)  # (1, input_size) for display only
        reward = 1.0
        next_state = torch.randn(cfg["model"]["input_size"])
        agent.store_experience(state, action, reward, next_state)
        _update_history(agent, agent.stats()["last_loss"])
        st.success(f"Action={action}  Confidence={confidence:.1%}  Reward=+1.0")
        st.rerun()

    # ── Auto-refresh (opt-in via toggle) ─────────────────────────────────────
    st.divider()
    update_interval = cfg["ui"].get("update_interval", 3)
    if cfg["ui"].get("show_graphs", True):
        auto_refresh = st.toggle(
            f"⏱️ Auto-refresh every {update_interval}s",
            value=False,
            key="nn_auto_refresh",
            help="Enable continuous auto-refresh of charts and stats.",
        )
        if auto_refresh:
            import time
            time.sleep(update_interval)
            _update_history(agent, stats["last_loss"])
            st.rerun()


def _update_history(agent: NeuralNetworkAgent, loss: float) -> None:
    """Append current loss/avg_reward to session history lists."""
    s = agent.stats()
    st.session_state["nn_loss_history"].append(loss)
    st.session_state["nn_reward_history"].append(s["avg_reward"])
    # Cap at 500 data points to avoid memory growth
    for key in ("nn_loss_history", "nn_reward_history"):
        if len(st.session_state[key]) > 500:
            st.session_state[key] = st.session_state[key][-500:]


# ═════════════════════════════════════════════════════════════════════════════
# Standalone entry point
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    st.set_page_config(
        page_title="AI Employee — Neural Network",
        page_icon="🧠",
        layout="wide",
    )
    render_tab()
